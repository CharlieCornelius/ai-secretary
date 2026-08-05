"""AI 经验库路由 - 查询/管理抽象经验"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.common.auth import verify_api_key
from app.common.config import get_config
from app.common.logging import get_logger
from app.common.schemas import OkResponse
from app.memory.experience import clear_all_experiences, list_all_experiences, store_experience

logger = get_logger("experience_routes")
router = APIRouter(prefix="/experiences", tags=["experiences"])


class ExperienceAddBody(BaseModel):
    """添加经验请求"""
    pattern: str
    category: Optional[str] = "manual"


@router.get("", response_model=OkResponse[list[str]])
async def list_experiences(
    n_results: Optional[int] = None,
    _: None = Depends(verify_api_key),
):
    """列出 AI 经验库中的抽象经验"""
    if n_results is None:
        n_results = get_config().api_defaults.experience_n_results
    experiences = await list_all_experiences(n_results=n_results)
    return OkResponse(data=experiences)


@router.post("", response_model=OkResponse[dict])
async def create_experience(
    body: ExperienceAddBody,
    _: None = Depends(verify_api_key),
):
    """手动添加一条经验"""
    await store_experience(body.pattern, category=body.category or "manual")
    return OkResponse(data={"added": True, "pattern": body.pattern})


@router.delete("", response_model=OkResponse[dict])
async def delete_all_experiences(
    _: None = Depends(verify_api_key),
):
    """清空所有经验"""
    await clear_all_experiences()
    return OkResponse(data={"cleared": True})