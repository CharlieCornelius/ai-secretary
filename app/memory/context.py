"""会话上下文管理 - 全量持久化到 SQLite，重启后可恢复"""

from __future__ import annotations

from sqlalchemy import delete, select

from app.common.config import get_config
from app.common.database import get_session_factory
from app.common.logging import get_logger
from app.db.models import Message

logger = get_logger("context")


def _get_max_messages() -> int:
    """从配置读取上下文窗口大小（按消息条数计）"""
    return get_config().context.max_context_turns


async def get_context(session_id: str) -> list[dict]:
    """从 DB 获取会话上下文（最近 N 条消息，按时间正序返回）

    返回字段含 tool_calls（assistant）与 tool_call_id（tool），
    供 llm_caller 重建 AIMessage(tool_calls) / ToolMessage，保持多轮工具记忆。
    """
    max_messages = _get_max_messages()
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(max_messages)
        )
        messages = list(result.scalars().all())
        result_msgs = []
        for m in reversed(messages):
            msg: dict = {"role": m.role, "content": m.content}
            # assistant 消息回填 tool_calls，供 LLM 重建工具调用上下文
            if m.role == "assistant" and m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            # tool 消息回填 tool_call_id，供 LLM 关联工具结果
            if m.role == "tool" and m.metadata_:
                tool_call_id = m.metadata_.get("tool_call_id")
                if tool_call_id:
                    msg["tool_call_id"] = tool_call_id
            # 群聊发言人识别：user 消息动态拼接前缀（给 LLM 看，DB 存原始内容）
            if m.role == "user" and m.metadata_:
                uid = m.metadata_.get("user_id")
                if uid:
                    prefix_fmt = get_config().knowledge.prompt_prefixes.group_chat_prefix
                    msg["content"] = prefix_fmt.format(user_id=uid, content=m.content)
            result_msgs.append(msg)

        # 窗口边界可能截断掉 tool 消息的父 assistant(tool_call)，
        # 留下孤立的 tool 消息会导致 LLM API 报错——裁剪开头的孤立 tool 消息
        while result_msgs and result_msgs[0]["role"] == "tool":
            result_msgs.pop(0)

        return result_msgs


async def add_message(session_id: str, role: str, content: str, **kwargs) -> None:
    """添加消息到 DB"""
    factory = get_session_factory()
    async with factory() as db:
        db.add(Message(session_id=session_id, role=role, content=content, **kwargs))
        await db.commit()
        logger.debug("消息已持久化", session_id=session_id, role=role)


async def clear_context(session_id: str) -> None:
    """清除会话上下文（删除 DB 记录）"""
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(delete(Message).where(Message.session_id == session_id))
        await db.commit()
        logger.info("上下文已清除", session_id=session_id)
