"""LLM 实例工厂 - 统一提供主 LLM 和子任务 LLM（带缓存）"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.common.config import get_config

# 缓存 LLM 实例（配置不变时复用，避免每次调用都新建）
_llm_cache: ChatOpenAI | None = None
_sub_task_llm_cache: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI:
    """获取主 LLM 实例（对话用，带缓存）"""
    global _llm_cache
    if _llm_cache is None:
        config = get_config()
        _llm_cache = ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url or None,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            max_retries=config.llm.max_retries,
        )
    return _llm_cache


def get_sub_task_llm() -> ChatOpenAI:
    """获取子任务 LLM 实例（画像/经验提取用，带缓存）"""
    global _sub_task_llm_cache
    if _sub_task_llm_cache is None:
        config = get_config()
        _sub_task_llm_cache = ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url or None,
            temperature=config.llm.sub_task_temperature,
            max_tokens=config.llm.sub_task_max_tokens,
            max_retries=config.llm.max_retries,
        )
    return _sub_task_llm_cache