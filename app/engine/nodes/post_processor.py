"""节点5: 后处理 - 更新上下文、持久化消息、三层记忆维护"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from app.common.background import get_background_runner
from app.common.config import get_config
from app.common.database import get_session_factory
from app.common.logging import get_logger
from app.db.models import AuditLog
from app.engine.state import ConversationState
from app.memory.context import add_message
logger = get_logger("post_processor")


async def post_process(state: ConversationState) -> ConversationState:
    """后处理节点：更新上下文 + 持久化 + 三层记忆维护"""
    logger.info("后处理开始", session_id=state.session_id)

    # 检查 LLM 调用是否失败，记录到 events
    if state.error:
        # events 会返回给客户端，只用通用文案，完整错误仅记日志（避免泄露 API key 片段等）
        state.events.append({
            "event": "error",
            "data": {"error": "LLM 调用失败"},
        })
        logger.warning("LLM 调用失败，使用兜底回复", session_id=state.session_id, error=state.error)

    # 确定 final_response：优先取轨迹中最后一条有内容的 assistant 消息
    if not state.final_response:
        for msg in reversed(state.conversation_history):
            if msg.get("role") == "assistant" and msg.get("content"):
                state.final_response = msg["content"]
                break
    # 兜底：使用 llm_response
    if not state.final_response and state.llm_response:
        state.final_response = state.llm_response

    # 终极兜底：确保用户不会收到空消息
    if not state.final_response:
        state.final_response = get_config().context.fallback_response
        logger.warning("最终兜底回复触发", session_id=state.session_id)

    # 1. 持久化完整编排轨迹（assistant 含 tool_calls + tool 结果），让多轮工具记忆可重建
    #    用户消息已在 API 层（chat.py）入库，此处只存本轮编排产物
    await _persist_conversation_trace(state)

    # 2. 审计日志持久化
    await _persist_audit(state)

    # 3. 异步维护长期记忆（不阻塞响应）
    _schedule_memory_updates(state)

    # 4. 完成事件
    state.events.append({
        "event": "complete",
        "data": {"response": state.final_response},
    })

    logger.info("后处理完成", session_id=state.session_id)
    return state


async def _persist_conversation_trace(state: ConversationState) -> None:
    """持久化编排轨迹：assistant(tool_calls) + tool(result) + 最终 assistant

    - assistant 且有 tool_calls → 写 Message.tool_calls
    - tool → role=tool，tool_call_id 存 metadata_
    - 与 final_response 一致的最后一条 assistant 附带 content_blocks
    - 轨迹为空或最终回复未被轨迹覆盖（兜底路径）→ 补一条 assistant
    """
    covers_final = False
    for msg in state.conversation_history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "assistant":
            tool_calls = msg.get("tool_calls") or None
            is_final_reply = bool(content) and content == state.final_response
            if is_final_reply:
                covers_final = True
            meta = (
                {"content_blocks": state.content_blocks}
                if is_final_reply and state.content_blocks
                else None
            )
            await add_message(
                state.session_id, "assistant", content,
                tool_calls=tool_calls, metadata_=meta,
            )
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            meta = {"tool_call_id": tool_call_id} if tool_call_id else None
            await add_message(state.session_id, "tool", content, metadata_=meta)

    # 轨迹为空（mock/异常路径）或最终回复来自兜底而非轨迹 → 补存最终 assistant
    if not covers_final:
        meta = {"content_blocks": state.content_blocks} if state.content_blocks else None
        await add_message(state.session_id, "assistant", state.final_response, metadata_=meta)


async def _persist_audit(state: ConversationState) -> None:
    """审计日志持久化"""
    factory = get_session_factory()

    async with factory() as db:
        db.add(AuditLog(
            user_id=state.user_id,
            session_id=state.session_id,
            direction="user",
            content=state.user_message,
        ))
        db.add(AuditLog(
            user_id=state.user_id,
            session_id=state.session_id,
            direction="assistant",
            content=state.final_response,
            metadata_={
                "tool_calls": state.all_tool_calls,
                "tool_results": state.all_tool_results,
            } if state.all_tool_calls or state.all_tool_results else None,
        ))

        await db.commit()

        # 审计日志滚动存储检查（异步，不阻塞）
        get_background_runner().submit(_trim_audit_logs_if_needed(), name="trim_audit_logs")


async def _trim_audit_logs_if_needed() -> None:
    """审计日志超阈值时，异步删除最旧的部分"""
    cfg = get_config().audit
    factory = get_session_factory()
    try:
        async with factory() as db:
            # 获取总数
            result = await db.execute(select(func.count()).select_from(AuditLog))
            total = result.scalar() or 0

            if total > cfg.max_logs:
                to_delete = int(cfg.max_logs * cfg.trim_ratio)
                # 查询最旧的 to_delete 条
                old_result = await db.execute(
                    select(AuditLog.id)
                    .order_by(AuditLog.created_at.asc())
                    .limit(to_delete)
                )
                old_ids = [r[0] for r in old_result.all()]
                if old_ids:
                    await db.execute(
                        delete(AuditLog).where(AuditLog.id.in_(old_ids))
                    )
                    await db.commit()
                    logger.info("审计日志已滚动清理", deleted=len(old_ids), remaining=total - len(old_ids))
    except Exception as e:
        logger.warning("审计日志滚动清理失败", error=str(e))


def _schedule_memory_updates(state: ConversationState) -> None:
    """异步调度三层记忆的维护任务（提交到后台运行器，异常隔离）"""
    user_id = state.user_id
    user_msg = state.user_message
    ai_reply = state.final_response or state.llm_response or ""

    async def _update_profile():
        try:
            from app.memory.profile_updater import update_profile_from_conversation
            await update_profile_from_conversation(user_id, user_msg, ai_reply)
        except Exception as e:
            logger.warning("用户画像更新失败", error=str(e), user_id=user_id)

    async def _update_experience():
        try:
            from app.memory.experience import extract_and_store_abstract_experience
            await extract_and_store_abstract_experience(user_msg, ai_reply)
        except Exception as e:
            logger.warning("抽象经验提取失败", error=str(e))

    # 提交到后台运行器（引用由 runner 管理，异常隔离）
    get_background_runner().submit(_update_profile(), name="update_profile")
    get_background_runner().submit(_update_experience(), name="update_experience")
    logger.debug("记忆更新任务已调度", session_id=state.session_id)
