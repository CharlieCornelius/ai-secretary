"""节点1: 知识注入 - 组装 system_prompt + context"""

from __future__ import annotations

from app.common.config import get_config
from app.common.database import get_session_factory
from app.common.logging import get_logger
from app.engine.state import ConversationState
from app.memory.knowledge import assemble
from app.memory.profile import get_or_create_profile
from app.plugins.loader import has_tools

logger = get_logger("knowledge_injector")


async def knowledge_inject(state: ConversationState) -> ConversationState:
    """知识注入节点"""
    logger.info("知识注入开始", session_id=state.session_id)

    try:
        # 获取用户画像（独立 session，新用户需 commit 持久化）
        factory = get_session_factory()
        async with factory() as db:
            profile = await get_or_create_profile(db, state.user_id)
            await db.commit()

        # 组装知识（外部知识由插件工具通过 tool_call 提供，不在此处注入）
        system_prompt, context_messages = await assemble(
            user_id=state.user_id,
            session_id=state.session_id,
            user_message=state.user_message,
            profile=profile,
        )

        state.system_prompt = system_prompt
        state.context_messages = context_messages

        # 群聊模式声明：由配置驱动
        if state.session_mode == "group":
            group_chat_hint = get_config().knowledge.prompt_prefixes.group_chat_hint
            if group_chat_hint:
                state.system_prompt = f"{state.system_prompt}\n\n{group_chat_hint}"

        # 附件提示注入：有附件时追加提示，由配置驱动
        if state.attachments:
            attachment_hint = _build_attachment_hint(state.attachments)
            if attachment_hint:
                state.system_prompt = f"{state.system_prompt}\n\n{attachment_hint}"

    except Exception as e:
        # Chroma/DB 等失败时，用户消息已入库；设 error 让 llm_call 跳过、post_process 兜底补回复，
        # 保证 user/assistant 成对，避免下轮 get_context 看到孤立 user 消息
        logger.error("知识注入失败", session_id=state.session_id, error=str(e))
        state.error = f"知识注入失败：{str(e)}"
        state.final_response = get_config().context.fallback_response

    # 初始化 conversation_history（本轮编排中间产物，由 llm_call 和 tool_executor 填充）
    state.conversation_history = []

    # 注意：用户消息已在 API 层（chat.py）加入上下文，此处不再重复添加

    # 执行事件
    state.events.append({
        "event": "thinking",
        "data": {"status": "knowledge_injected"},
    })

    logger.info("知识注入完成", session_id=state.session_id)
    return state


def _build_attachment_hint(attachments: list[dict]) -> str:
    """构建附件提示：由配置驱动，区分有无工具场景"""
    prefixes = get_config().knowledge.prompt_prefixes

    lines = [prefixes.attachment_header]
    for att in attachments:
        att_type = att.get("type", "unknown")
        att_data = att.get("data", {})
        lines.append(f"- {att_type}: {att_data}")

    if has_tools():
        lines.append(prefixes.attachment_with_tools)
    else:
        lines.append(prefixes.attachment_no_tools)

    return "\n".join(lines)
