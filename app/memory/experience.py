"""经验库 - Chroma 向量库，抽象经验跨用户共享，由 LLM 维护"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

import chromadb

from app.common.config import get_config
from app.common.llm import get_sub_task_llm
from app.common.logging import get_logger

logger = get_logger("experience")

# 经验条目 ID 的 hex 截取长度
EXPERIENCE_ID_HEX_LEN = 8

_client: Optional[chromadb.ClientAPI] = None
_collection = None


def _get_client() -> chromadb.ClientAPI:
    """获取 Chroma 客户端"""
    global _client
    if _client is None:
        config = get_config()
        _client = chromadb.PersistentClient(path=config.chroma.persist_directory)
    return _client


def _create_collection():
    """创建新的经验集合"""
    config = get_config()
    client = _get_client()
    return client.get_or_create_collection(
        name=config.chroma.collection_name,
        metadata={"hnsw:space": config.chroma.hnsw_space},
    )


def _get_collection():
    """获取经验集合（惰性创建，不做主动健康检查）"""
    global _collection
    if _collection is None:
        _collection = _create_collection()
    return _collection


def _reset_chroma() -> None:
    """重置 Chroma 全局缓存（目录被删除或操作异常后调用）"""
    global _client, _collection
    _client = None
    _collection = None
    logger.info("Chroma 缓存已重置")


async def _run_with_reset(op):
    """执行集合操作，异常时重置重建并重试一次（惰性校验，正常路径零额外开销）"""
    try:
        return await op(_get_collection())
    except Exception as e:
        logger.warning("Chroma 操作失败，重置集合后重试", error=str(e))
        _reset_chroma()
        return await op(_get_collection())


async def store_experience(pattern: str, category: str = "general") -> None:
    """存储抽象经验（无用户标识，跨用户共享）"""
    max_entries = get_config().experience.max_entries

    # 检查上限，必要时压缩
    current_count = await _run_with_reset(lambda c: asyncio.to_thread(c.count))
    if current_count >= max_entries:
        await _compress_experiences()

    doc_id = uuid.uuid4().hex[:EXPERIENCE_ID_HEX_LEN]
    await _run_with_reset(lambda c: asyncio.to_thread(
        c.add,
        documents=[pattern],
        metadatas=[{"category": category}],
        ids=[doc_id],
    ))
    trunc = get_config().logging_truncation.pattern_log
    logger.info("经验已存储", pattern=pattern[:trunc], category=category)


async def search_experiences(query: str, n_results: int) -> list[str]:
    """按相关性检索经验"""
    count = await _run_with_reset(lambda c: asyncio.to_thread(c.count))
    if count == 0:
        return []

    results = await _run_with_reset(lambda c: asyncio.to_thread(
        c.query,
        query_texts=[query],
        n_results=min(n_results, count),
    ))

    documents = results.get("documents", [[]])[0]
    return documents


async def list_all_experiences(n_results: int = 50) -> list[str]:
    """列出所有经验（使用 get 而非 query，避免空查询问题）"""
    count = await _run_with_reset(lambda c: asyncio.to_thread(c.count))
    if count == 0:
        return []

    results = await _run_with_reset(lambda c: asyncio.to_thread(c.get, limit=min(n_results, count)))
    documents = results.get("documents", [])
    return documents


async def clear_all_experiences() -> None:
    """清空所有经验"""
    count = await _run_with_reset(lambda c: asyncio.to_thread(c.count))
    if count == 0:
        return
    # 使用 get() 安全获取所有条目，避免空字符串 query 的兼容性问题
    all_results = await _run_with_reset(lambda c: asyncio.to_thread(c.get, limit=count))
    all_ids = all_results.get("ids", [])
    if all_ids:
        await _run_with_reset(lambda c: asyncio.to_thread(c.delete, ids=all_ids))
    logger.info("经验库已清空")


async def _compress_experiences() -> None:
    """经验库超限，调用 LLM 压缩去重"""
    try:
        cfg = get_config().experience
        count = await _run_with_reset(lambda c: asyncio.to_thread(c.count))
        if count == 0:
            return
        # 使用 get() 安全获取所有条目，避免空字符串 query 的兼容性问题
        all_results = await _run_with_reset(lambda c: asyncio.to_thread(c.get, limit=count))
        all_docs = all_results.get("documents", [])

        if len(all_docs) <= cfg.max_entries:
            return

        logger.info("经验库条目超出上限，触发压缩", count=len(all_docs))

        # 调用 LLM 压缩
        llm = get_sub_task_llm()
        prompt = cfg.prompts.compression.format(
            count=len(all_docs),
            experiences_text="\n".join(f"- {d}" for d in all_docs),
            max_entries=cfg.max_entries,
        )
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = response.content or ""

        # 解析编号列表
        compressed = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # 去掉编号前缀 "1. " 或 "- "
            if ". " in line[:4]:
                line = line.split(". ", 1)[1]
            elif line.startswith("- "):
                line = line[2:]
            if len(line) > get_config().experience.filter.min_length:
                compressed.append(line)

        # 清空旧数据，写入压缩后的
        all_ids = all_results.get("ids", [])
        if all_ids:
            await _run_with_reset(lambda c: asyncio.to_thread(c.delete, ids=all_ids))

        new_ids = [uuid.uuid4().hex[:EXPERIENCE_ID_HEX_LEN] for _ in compressed]
        if compressed:
            await _run_with_reset(lambda c: asyncio.to_thread(
                c.add,
                documents=compressed,
                metadatas=[{"category": "abstract_pattern"}] * len(compressed),
                ids=new_ids,
            ))
        logger.info("经验库压缩完成", before=len(all_docs), after=len(compressed))

    except Exception as e:
        logger.warning("经验库压缩失败", error=str(e))
        # 压缩失败则截断到上限
        cfg = get_config().experience
        count = await _run_with_reset(lambda c: asyncio.to_thread(c.count))
        if count == 0:
            return
        all_results = await _run_with_reset(lambda c: asyncio.to_thread(c.get, limit=count))
        all_ids = all_results.get("ids", [])
        if len(all_ids) > cfg.max_entries:
            to_delete = all_ids[cfg.max_entries:]
            await _run_with_reset(lambda c: asyncio.to_thread(c.delete, ids=to_delete))

async def extract_and_store_abstract_experience(
    user_msg: str, ai_reply: str
) -> None:
    """调用 LLM 提取抽象经验并存储"""
    try:
        cfg = get_config().experience
        llm = get_sub_task_llm()
        trunc = cfg.message_truncation
        prompt = cfg.prompts.extraction.format(
            user_msg=user_msg[:trunc],
            ai_reply=ai_reply[:trunc],
        )
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        pattern = (response.content or "").strip()

        # 过滤无效输出（LLM 返回的 markdown 代码块或占位符）
        flt = cfg.filter
        if not pattern or len(pattern) < flt.min_length:
            return
        for kw in flt.invalid_keywords:
            if kw in pattern:
                return
        # 过滤 markdown 代码块、标题等格式
        if pattern.startswith(tuple(flt.markdown_prefixes)):
            return
        # 过滤只包含元数据/JSON 的内容
        if flt.filter_json and pattern.startswith("{") and pattern.endswith("}"):
            return

        # 存储
        await store_experience(pattern, category="abstract_pattern")
        trunc = get_config().logging_truncation.pattern_log
        logger.info("抽象经验已提取", pattern=pattern[:trunc])

    except Exception as e:
        logger.warning("抽象经验提取失败", error=str(e))
