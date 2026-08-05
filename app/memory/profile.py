"""用户画像 - SQLite 读写，严格按 user_id 隔离，LLM 自主维护"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logging import get_logger
from app.db.models import Profile

logger = get_logger("profile")


async def get_profile(db: AsyncSession, user_id: str) -> Optional[Profile]:
    """获取用户画像"""
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_profile(db: AsyncSession, user_id: str) -> Profile:
    """获取或创建用户画像"""
    profile = await get_profile(db, user_id)
    if profile is None:
        profile = Profile(
            user_id=user_id,
            memories={},
        )
        db.add(profile)
        await db.flush()
        logger.info("用户画像已创建", user_id=user_id)
    return profile


async def update_memories(
    db: AsyncSession, user_id: str, memories: dict[str, Any]
) -> Profile:
    """更新用户画像（完全替换 memories）"""
    profile = await get_or_create_profile(db, user_id)
    profile.memories = memories
    profile.updated_at = datetime.now()
    await db.flush()
    logger.info("用户画像已更新", user_id=user_id, entries=len(memories))
    return profile


async def delete_profile(db: AsyncSession, user_id: str) -> bool:
    """删除用户画像，返回是否实际删除了记录"""
    profile = await get_profile(db, user_id)
    if profile is None:
        return False
    await db.delete(profile)
    await db.flush()
    logger.info("用户画像已删除", user_id=user_id)
    return True