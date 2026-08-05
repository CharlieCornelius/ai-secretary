"""LangGraph 对话图 - 知识注入 → LLM → 工具执行(可循环) → 后处理"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.common.config import get_config
from app.common.logging import get_logger
from app.engine.nodes.knowledge_injector import knowledge_inject
from app.engine.nodes.llm_caller import llm_call
from app.engine.nodes.post_processor import post_process
from app.engine.nodes.tool_executor import tool_execute
from app.engine.state import ConversationState

logger = get_logger("graph")


def _after_tool_execution(state: ConversationState) -> str:
    """条件边：工具执行后判断是否继续"""
    # 检查是否超过最大循环次数
    max_iter = get_config().context.max_tool_iterations
    if state.iteration_count >= max_iter:
        logger.warning("多步编排达到最大循环次数", session_id=state.session_id, count=state.iteration_count)
        return "post_process"

    # 有工具结果，继续让 LLM 决定下一步
    return "continue"


def build_conversation_graph() -> StateGraph:
    """构建对话图（支持多步工具编排）"""
    graph = StateGraph(ConversationState)

    # 添加节点
    graph.add_node("knowledge_inject", knowledge_inject)
    graph.add_node("llm_call", llm_call)
    graph.add_node("tool_execute", tool_execute)
    graph.add_node("post_process", post_process)

    # 设置入口
    graph.set_entry_point("knowledge_inject")

    # 添加边
    graph.add_edge("knowledge_inject", "llm_call")

    # 条件边：LLM 后，有 error 则直接后处理，有 tool_calls 则执行，否则后处理
    graph.add_conditional_edges(
        "llm_call",
        lambda s: "error" if s.error else ("execute_tools" if s.tool_calls else "post_process"),
        {
            "execute_tools": "tool_execute",
            "post_process": "post_process",
            "error": "post_process",
        },
    )

    # 条件边：工具执行后 → 继续编排或后处理
    graph.add_conditional_edges(
        "tool_execute",
        _after_tool_execution,
        {
            "continue": "llm_call",     # 继续编排，回到 LLM 判断下一步
            "post_process": "post_process",
        },
    )

    graph.add_edge("post_process", END)

    logger.info("对话图已构建（支持多步编排）")
    return graph


# 全局图实例
_compiled_graph = None


def get_compiled_graph():
    """获取编译后的图实例"""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_conversation_graph()
        _compiled_graph = graph.compile()
    return _compiled_graph


async def run_conversation(
    user_id: str,
    session_id: str,
    user_message: str,
    attachments: list[dict] | None = None,
    session_mode: str = "single",
) -> ConversationState:
    """运行一次对话流程"""
    graph = get_compiled_graph()

    initial_state = ConversationState(
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        attachments=attachments or [],
        session_mode=session_mode,
    )

    result = await graph.ainvoke(initial_state)
    # LangGraph ainvoke 返回 dict，需要转换回 ConversationState
    if isinstance(result, dict):
        return ConversationState(**result)
    return result
