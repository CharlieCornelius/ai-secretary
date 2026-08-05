"""用户画像查询插件 - 查询群聊中其他参与者的画像信息

LLM 在群聊中看到 [user_id] 前缀后，可调用此工具查询该参与者的详细画像。
也支持通过名字查询（当 LLM 知道参与者名字但不知道 user_id 时）。
"""

from __future__ import annotations

from sqlalchemy import select

from app.common.logging import get_logger
from app.db.models import Profile
from app.memory.profile import get_profile

logger = get_logger("profile_query_plugin")


async def query_profile(db, user_id: str, session_id: str, args: dict) -> str:
    """查询指定用户的画像信息（支持 user_id 或 name 查询）"""
    target_id = args.get("user_id", "").strip()
    target_name = args.get("name", "").strip()

    if not target_id and not target_name:
        return "错误：user_id 和 name 至少提供一个"

    # 优先按 user_id 查询
    if target_id:
        return await _query_by_id(db, target_id)

    # 按 name 查询：遍历所有画像，匹配 memories 中的 name 字段
    return await _query_by_name(db, target_name)


async def _query_by_id(db, target_id: str) -> str:
    """按 user_id 查询画像"""
    try:
        profile = await get_profile(db, target_id)
    except Exception as e:
        logger.warning("画像查询失败", target=target_id, error=str(e))
        return f"查询用户 {target_id} 的画像时出错"

    if not profile or not profile.memories:
        return f"未找到用户 {target_id} 的画像信息（该用户可能尚未建立画像）"

    return _format_profile(target_id, profile.memories)


async def _query_by_name(db, target_name: str) -> str:
    """按名字查询画像：遍历所有画像，匹配 memories 中的 name 字段"""
    try:
        result = await db.execute(select(Profile))
        profiles = list(result.scalars().all())
    except Exception as e:
        logger.warning("画像按名字查询失败", target_name=target_name, error=str(e))
        return f"按名字查询用户 {target_name} 的画像时出错"

    matched = []
    for p in profiles:
        if not p.memories:
            continue
        name_val = str(p.memories.get("name", "")).strip()
        if name_val == target_name:
            matched.append(p)

    if not matched:
        return f"未找到名字为 {target_name} 的用户画像信息"

    if len(matched) > 1:
        # 多个匹配，列出所有匹配的 user_id
        ids = ", ".join(p.user_id for p in matched)
        return f"找到多个名字为 {target_name} 的用户：{ids}，请通过 user_id 进一步指定"

    profile = matched[0]
    return _format_profile(profile.user_id, profile.memories, display_name=target_name)


def _format_profile(user_id: str, memories: dict, display_name: str | None = None) -> str:
    """格式化画像信息"""
    label = display_name or user_id
    lines = [f"【用户 {label}（id: {user_id}）的画像】"]
    for k, v in memories.items():
        lines.append(f"- {k}：{v}")

    return "\n".join(lines)
