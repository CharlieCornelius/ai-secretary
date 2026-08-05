"""用户画像路由"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.auth import verify_api_key
from app.common.database import get_db
from app.common.logging import get_logger
from app.common.schemas import OkResponse, ProfileResponse, ProfileUpdate
from app.memory.profile import delete_profile, get_or_create_profile, update_memories

logger = get_logger("profile_routes")
router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{user_id}", response_model=OkResponse[ProfileResponse])
async def get_my_profile(
    user_id: str,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """获取用户画像"""
    profile = await get_or_create_profile(db, user_id)
    return OkResponse(data=ProfileResponse(
        user_id=profile.user_id,
        memories=profile.memories or {},
        updated_at=profile.updated_at,
    ))


@router.patch("/{user_id}", response_model=OkResponse[ProfileResponse])
async def patch_profile(
    user_id: str,
    body: ProfileUpdate,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """更新用户画像（外部手动编辑，或 LLM 自动维护）"""
    if body.memories is not None:
        profile = await update_memories(db, user_id, body.memories)
    else:
        profile = await get_or_create_profile(db, user_id)

    return OkResponse(data=ProfileResponse(
        user_id=profile.user_id,
        memories=profile.memories or {},
        updated_at=profile.updated_at,
    ))


@router.delete("/{user_id}")
async def delete_my_profile(
    user_id: str,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """删除用户画像（数据生命周期/隐私）"""
    deleted = await delete_profile(db, user_id)
    return OkResponse(data={"user_id": user_id, "deleted": deleted})