"""用户画像维护 - 由 LLM 自主维护，SQLite 持久化，用户级记忆"""

from __future__ import annotations

import json

from app.common.config import get_config
from app.common.database import get_session_factory
from app.common.llm import get_sub_task_llm
from app.common.logging import get_logger
from app.memory.profile import get_profile, update_memories

logger = get_logger("profile_updater")

# Markdown 代码围栏标记（剥离 LLM 返回的代码块）
CODE_FENCE_JSON = "```json"
CODE_FENCE = "```"


async def update_profile_from_conversation(
    user_id: str, user_msg: str, ai_reply: str
) -> None:
    """分析对话，判断是否需要更新用户画像"""

    try:
        # 1. 获取当前画像
        factory = get_session_factory()
        async with factory() as db:
            profile = await get_profile(db, user_id)

        current_memories = {}
        if profile and profile.memories:
            current_memories = dict(profile.memories)

        # 2. 构建 LLM 提取 prompt
        cfg = get_config().profile
        llm = get_sub_task_llm()

        trunc = cfg.message_truncation
        prompt = cfg.prompts.extraction.format(
            user_msg=user_msg[:trunc],
            ai_reply=ai_reply[:trunc],
        )

        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = response.content or ""

        # 3. 解析提取结果（去掉可能的 markdown 代码块，兼容大小写变体）
        try:
            cleaned = content.strip()
            if cleaned.lower().startswith(CODE_FENCE_JSON):
                cleaned = cleaned[len(CODE_FENCE_JSON):].strip()
            elif cleaned.lower().startswith(CODE_FENCE):
                cleaned = cleaned[len(CODE_FENCE):].strip()
            if cleaned.endswith(CODE_FENCE):
                cleaned = cleaned[:-len(CODE_FENCE)].strip()
            data = json.loads(cleaned)
            new_entries = data.get("entries", [])
        except json.JSONDecodeError:
            trunc = get_config().logging_truncation.error_content
            logger.warning("画像提取返回非 JSON", content=content[:trunc])
            return

        if not new_entries:
            return

        # 4. 合并新条目到画像
        for entry in new_entries:
            key = entry.get("key", "").strip()
            value = entry.get("value", "").strip()

            if key and value:
                current_memories[key] = value

        # 5. 检查上限，必要时压缩
        max_entries = cfg.max_memory_entries
        if len(current_memories) > max_entries:
            current_memories = await _compress_memories(
                current_memories, max_entries
            )

        # 6. 持久化
        async with factory() as db:
            await update_memories(db, user_id, current_memories)
            await db.commit()

        logger.info(
            "用户画像已更新",
            user_id=user_id,
            entries_added=len(new_entries),
            total_entries=len(current_memories),
        )

    except Exception as e:
        logger.warning("画像更新失败", error=str(e), user_id=user_id)


async def _compress_memories(memories: dict, max_entries: int) -> dict:
    """调用 LLM 压缩去重画像条目"""
    try:
        cfg = get_config().profile
        llm = get_sub_task_llm()

        entries_text = "\n".join(
            f"- {k}: {v}" for k, v in memories.items()
        )

        prompt = cfg.prompts.compression.format(
            count=len(memories),
            entries_text=entries_text,
            max_entries=max_entries,
        )

        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = response.content or ""

        # 解析 key: value 格式
        compressed = {}
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if ": " in line:
                parts = line.split(": ", 1)
                key = parts[0].lstrip("- ").strip()
                value = ": ".join(parts[1:]).strip()
                if key and value:
                    compressed[key] = value

        if compressed:
            return compressed
        # LLM 压缩返回空：不截断，保留全部条目待下次重试，避免误丢关键记忆
        logger.warning("画像压缩返回空，保留全部条目不截断", count=len(memories))
        return dict(memories)

    except Exception as e:
        logger.warning("画像压缩失败，保留全部条目不截断", error=str(e))
        return dict(memories)

