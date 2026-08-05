"""RAG 插件 - 调用外部 RAG 服务

配置方式（完全自理，不依赖主程序配置）：
1. 环境变量: RAG_API_URL, RAG_API_KEY
2. 插件目录下的 config.yaml（可选）
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx2
import yaml

logger = None  # 延迟导入，避免主程序日志依赖


def _get_logger():
    global logger
    if logger is None:
        try:
            from app.common.logging import get_logger
            logger = get_logger("rag_plugin")
        except Exception:
            import logging
            logger = logging.getLogger("rag_plugin")
    return logger


def _load_config() -> dict:
    """加载插件自有配置（环境变量优先级高于配置文件）"""
    # 1. 配置文件作为基础（读取全部字段，含 timeout / default_top_k 等）
    config_path = Path(__file__).parent / "config.yaml"
    cfg: dict = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

    # 2. 环境变量覆盖（最高优先级）
    cfg.setdefault("api_url", "")
    cfg.setdefault("api_key", "")
    cfg["api_url"] = os.environ.get("RAG_API_URL", cfg["api_url"])
    cfg["api_key"] = os.environ.get("RAG_API_KEY", cfg["api_key"])

    return cfg


async def search_knowledge(db, user_id: str, session_id: str, args: dict) -> str:
    """从外部 RAG 服务检索知识"""
    log = _get_logger()
    query = args.get("query", "")

    if not query:
        return "错误：查询语句不能为空"

    # 读取自有配置
    cfg = _load_config()
    top_k = args.get("top_k", cfg.get("default_top_k", 3))
    api_url = cfg["api_url"]
    api_key = cfg["api_key"]
    timeout = cfg.get("timeout", 30)

    if not api_url:
        return "错误：RAG 服务未配置（请设置环境变量 RAG_API_URL 或在 plugins/rag/config.yaml 中配置）"

    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx2.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                api_url,
                json={"query": query, "top_k": top_k},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        # 解析返回结果（适配常见 RAG 响应格式）
        results = []
        if isinstance(data, list):
            results = data
        elif isinstance(data, dict):
            results = data.get("results", data.get("data", []))

        if not results:
            return f"未找到与 '{query}' 相关的知识"

        # 格式化结果
        lines = [f"【知识检索结果】查询: {query}\n"]
        for i, item in enumerate(results[:top_k], 1):
            if isinstance(item, str):
                lines.append(f"{i}. {item}")
            elif isinstance(item, dict):
                content = item.get("content", item.get("text", item.get("answer", str(item))))
                source = item.get("source", item.get("document", ""))
                if source:
                    lines.append(f"{i}. {content}\n   来源: {source}")
                else:
                    lines.append(f"{i}. {content}")

        return "\n".join(lines)

    except httpx2.TimeoutException:
        log.warning("RAG 服务超时", query=query)
        return "RAG 服务响应超时，请稍后再试"
    except httpx2.HTTPStatusError as e:
        log.error("RAG 服务 HTTP 错误", status=e.response.status_code, text=e.response.text)
        return f"RAG 服务错误 (HTTP {e.response.status_code})"
    except Exception as e:
        log.error("RAG 检索失败", error=str(e))
        return f"RAG 检索失败: {str(e)}"