"""会话路由 - CRUD"""

from __future__ import annotations

from uuid import uuid4

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.auth import verify_api_key
from app.common.config import get_config
from app.common.database import get_db
from app.common.errors import NotFoundError
from app.common.logging import get_logger
from app.common.schemas import MessageResponse, OkResponse, SessionCreate, SessionResponse, SessionUpdate
from app.db.models import AuditLog, Message, Session as SessionModel
logger = get_logger("session_routes")
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=OkResponse[SessionResponse])
async def create_session(
    body: SessionCreate,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """创建新会话"""
    session = SessionModel(
        id=str(uuid4()),
        title=body.title,
        mode=body.mode,
    )
    db.add(session)
    await db.flush()

    return OkResponse(data=SessionResponse.from_model(session))


@router.get("", response_model=OkResponse[list[SessionResponse]])
async def list_sessions(
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """列出所有活跃会话"""
    result = await db.execute(
        select(SessionModel)
        .where(SessionModel.status == "active")
        .order_by(SessionModel.updated_at.desc())
    )
    sessions = list(result.scalars().all())

    return OkResponse(data=[SessionResponse.from_model(s) for s in sessions])


@router.get("/{session_id}", response_model=OkResponse[SessionResponse])
async def get_session(
    session_id: str,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """获取会话详情"""
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("会话不存在")

    return OkResponse(data=SessionResponse.from_model(session))


@router.patch("/{session_id}", response_model=OkResponse[SessionResponse])
async def update_session(
    session_id: str,
    body: SessionUpdate,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """修改会话标题"""
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("会话不存在")

    if body.title is not None:
        session.title = body.title
        await db.flush()

    return OkResponse(data=SessionResponse.from_model(session))


@router.delete("/{session_id}", response_model=OkResponse[dict])
async def delete_session(
    session_id: str,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """硬删除会话（级联删除消息、确认、审计日志）"""
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("会话不存在")

    # 级联删除（Message、AuditLog、Session 在同一事务中）
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(delete(AuditLog).where(AuditLog.session_id == session_id))
    await db.execute(delete(SessionModel).where(SessionModel.id == session_id))
    await db.flush()

    return OkResponse(data={"id": session_id, "deleted": True})


@router.get("/{session_id}/messages", response_model=OkResponse[list[MessageResponse]])
async def get_session_messages(
    session_id: str,
    limit: Optional[int] = None,
    _: None = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """获取会话消息列表"""
    if limit is None:
        limit = get_config().api_defaults.session_limit
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("会话不存在")

    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(msg_result.scalars().all())

    return OkResponse(data=[
        MessageResponse(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            tool_calls=m.tool_calls,
            metadata=m.metadata_,
            created_at=m.created_at,
        )
        for m in reversed(messages)
    ])
