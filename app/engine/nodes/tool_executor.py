"""节点4: 工具执行 - 遍历 tool_calls 并执行，结果加入 conversation_history"""

from __future__ import annotations

from app.common.database import get_session_factory
from app.common.logging import get_logger
from app.engine.state import ConversationState
from app.plugins.loader import execute_tool

logger = get_logger("tool_executor")


def _parse_tool_result(result) -> tuple[str, list[dict]]:
    """解析工具返回值：str 或 dict → (text, content_blocks)"""
    if isinstance(result, dict):
        text = result.get("text", str(result))
        content_blocks = result.get("content_blocks", [])
        return text, content_blocks
    else:
        return str(result), []


async def tool_execute(state: ConversationState) -> ConversationState:
    """工具执行节点：执行所有 tool_calls，结果加入 conversation_history"""
    if not state.tool_calls:
        return state

    logger.info(
        "工具执行开始",
        session_id=state.session_id,
        tool_count=len(state.tool_calls),
        iteration=state.iteration_count,
    )

    state.iteration_count += 1

    factory = get_session_factory()
    tool_results = []

    for tc in state.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]
        tool_id = tc.get("id", "")

        # 每个工具独立事务
        async with factory() as db:
            try:
                result = await execute_tool(
                    tool_name=tool_name,
                    db=db,
                    user_id=state.user_id,
                    session_id=state.session_id,
                    args=tool_args,
                )
                await db.commit()

                # 解析工具返回值
                text, content_blocks = _parse_tool_result(result)
                if content_blocks:
                    state.content_blocks.extend(content_blocks)
                state.conversation_history.append({
                    "role": "tool",
                    "content": text,
                    "tool_call_id": tool_id,
                })

                tool_results.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                    "success": True,
                })

                state.events.append({
                    "event": "tool_executed",
                    "data": {"tool": tool_name, "success": True},
                })

                logger.info("工具执行成功", tool=tool_name, iteration=state.iteration_count)

            except Exception as e:
                await db.rollback()
                error_msg = str(e)
                state.conversation_history.append({
                    "role": "tool",
                    "content": f"执行失败: {error_msg}",
                    "tool_call_id": tool_id,
                })

                tool_results.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": error_msg,
                    "success": False,
                })

                state.events.append({
                    "event": "tool_error",
                    # events 返回客户端，用通用文案；完整错误仅日志
                    "data": {"tool": tool_name, "error": "工具执行失败"},
                })

                logger.error("工具执行失败", tool=tool_name, error=error_msg)

    state.tool_results = tool_results
    # 累积到跨轮次列表（用于审计日志），然后清空当前轮次
    state.all_tool_calls.extend(state.tool_calls)
    state.all_tool_results.extend(tool_results)
    state.tool_calls = []

    logger.info(
        "工具执行完成",
        session_id=state.session_id,
        results_count=len(tool_results),
        iteration=state.iteration_count,
    )

    return state