"""聊天路由 - /interact"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.auth import verify_api_key
from app.common.database import get_session_factory
from app.common.errors import SessionError
from app.common.logging import get_logger
from app.common.schemas import InteractData, InteractRequest, OkResponse
from app.db.models import Session
from app.engine.graph import run_conversation
from app.memory.context import add_message

logger = get_logger("chat_routes")
router = APIRouter(tags=["chat"])


async def _session_exists(session_id: str) -> Session | None:
    """用独立短生命周期 session 校验会话存在性，校验后立即释放连接"""
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()


@router.post("/sessions/{session_id}/interact", response_model=OkResponse[InteractData], response_model_exclude_none=True)
async def interact(
    session_id: str,
    body: InteractRequest,
    _: None = Depends(verify_api_key),
):
    """对话交互入口"""
    # 校验会话存在（独立 session，校验后释放，避免持有连接贯穿整个 LLM 调用）
    session = await _session_exists(session_id)
    if session is None:
        raise SessionError("会话不存在")

    # 附件数据处理（可省略，缺省为空列表）
    attachments_data = [a.model_dump() for a in body.attachments] if body.attachments else []

    # 用户消息持久化到 DB（独立 session）
    # 群聊模式：metadata_ 存 user_id + 附件；单人模式：仅附件存入 metadata_
    # content 存原始消息（群聊前缀由 context.py 读历史时动态拼接给 LLM）
    msg_metadata = {}
    if session.mode == "group":
        msg_metadata["user_id"] = body.user_id
    if attachments_data:
        msg_metadata["attachments"] = attachments_data
    await add_message(
        session_id, "user", body.message,
        metadata_=msg_metadata or None,
    )

    # 运行对话引擎（引擎内部自管 DB session，不占用请求级连接）
    state = await run_conversation(
        user_id=body.user_id,
        session_id=session_id,
        user_message=body.message,
        attachments=attachments_data or None,
        session_mode=session.mode,
    )

    data = {
        "type": "response",
        "response": state.final_response,
        "events": state.events,
    }
    if state.content_blocks:
        data["content_blocks"] = state.content_blocks

    return OkResponse(data=data)
