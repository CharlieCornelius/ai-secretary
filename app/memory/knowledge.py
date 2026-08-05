"""知识注入 - 合并角色设定+时间+外部RAG+经验+画像+上下文"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from app.common.config import get_config
from app.common.logging import get_logger
from app.memory.context import get_context
from app.memory.experience import search_experiences

logger = get_logger("knowledge")

# persona.yaml 缓存
_persona_cache: Optional[dict] = None
_persona_mtime: float = 0

def _load_persona() -> dict:
    """加载角色设定（带缓存，文件修改后自动刷新；缺失时返回缓存/空 dict 不崩溃）"""
    global _persona_cache, _persona_mtime
    path = Path(__file__).parent.parent.parent / "config" / "persona.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    # 文件缺失或不可读时，复用缓存（若有），否则空 dict，绝不冒泡崩溃整条对话
    if _persona_cache is None or mtime != _persona_mtime:
        try:
            with open(path, "r", encoding="utf-8") as f:
                _persona_cache = yaml.safe_load(f) or {}
            _persona_mtime = mtime
        except OSError:
            logger.warning("persona.yaml 读取失败，使用空角色设定", path=str(path))
            _persona_cache = _persona_cache or {}
            _persona_mtime = mtime
    return _persona_cache

def format_time_context() -> str:
    """格式化当前时间上下文"""
    cfg = get_config().knowledge.time_format
    now = datetime.now()
    weekday = cfg.weekdays[now.weekday()]
    return cfg.format.format(
        date=now.strftime(cfg.date_format),
        weekday=weekday,
        time=now.strftime(cfg.time_format),
    )

def _build_system_prompt(persona: dict) -> str:
    """构建 system prompt
    
    基础角色设定完全由 persona.system_prompt 提供，不做任何硬编码拼接。
    仅动态追加运行时上下文（时间、工具列表等）。
    """
    # 基础 system prompt 来自配置文件
    parts = [persona.get("system_prompt", "").strip()]

    # 动态注入已注册工具能力（运行时变化，无法写死在配置中）
    try:
        from app.plugins.loader import has_tools, get_all_tool_definitions
        if has_tools():
            prefixes = get_config().knowledge.prompt_prefixes
            tool_lines = []
            for definition in get_all_tool_definitions():
                name = definition.get("name", "")
                desc = definition.get("description", name)
                tool_lines.append(prefixes.tool_list_entry.format(name=name, desc=desc))
            if tool_lines:
                parts.append(
                    f"{prefixes.tool_list_header}\n"
                    + "\n".join(tool_lines)
                    + f"\n\n{prefixes.tool_list_footer}"
                )
    except Exception:
        logger.warning("工具列表注入失败", exc_info=True)

    return "\n\n".join(parts)

async def assemble(
    user_id: str,
    session_id: str,
    user_message: str,
    profile: Optional[Any] = None,
) -> tuple[str, list[dict]]:
    """组装知识注入

    返回：(system_prompt, context_messages)

    注入源：
    1. 角色设定 (persona.yaml system_prompt) — 始终注入
    2. 已注册工具列表 — 动态注入
    3. 当前时间 — 始终注入
    4. 用户画像 (SQLite Profile.memories) — 始终注入
    5. 相关经验 (Chroma 检索) — 按相关性检索
    6. 对话上下文 (内存读取) — 最近 N 轮
    
    外部知识由插件工具 (search_knowledge/web_search) 通过 tool_call 提供
    """
    # 1. 角色设定 + 工具列表
    persona = _load_persona()
    system_parts = [_build_system_prompt(persona)]

    # 2. 当前时间
    system_parts.append(format_time_context())

    # 3. 用户画像（你对用户的记忆与认知）
    prefixes = get_config().knowledge.prompt_prefixes
    memories = {}
    if profile and profile.memories:
        memories = dict(profile.memories)
    if memories:
        mem_text = "\n".join(prefixes.memory_entry.format(k=k, v=v) for k, v in memories.items())
        system_parts.append(f"{prefixes.memory_header}\n{mem_text}")

    # 4. 相关经验（Chroma 抽象经验）
    n_results = get_config().knowledge.experience_n_results
    experiences = await search_experiences(user_message, n_results=n_results)
    if experiences:
        exp_text = "\n".join(prefixes.experience_entry.format(exp=exp) for exp in experiences)
        system_parts.append(f"{prefixes.experience_header}\n{exp_text}")

    # 组装 system prompt（过滤空段落）
    sep = get_config().knowledge.prompt_separator
    system_prompt = sep.join(p for p in system_parts if p.strip())

    # 6. 对话上下文（本轮会话历史）
    context_messages = await get_context(session_id)

    return system_prompt, context_messages