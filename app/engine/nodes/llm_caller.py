"""节点2: LLM 调用 - 调用大模型，解析 tool_calls"""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from app.common.config import get_config
from app.common.llm import get_llm
from app.common.logging import get_logger
from app.engine.state import ConversationState
from app.plugins.loader import get_all_tool_definitions

logger = get_logger("llm_caller")


def _convert_to_lc_messages(messages: list[dict]) -> list:
    """将字典消息转换为 LangChain 消息对象"""
    lc_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                # LangChain AIMessage.tool_calls 格式: [{"name": "...", "args": {...}, "id": "..."}]
                lc_tool_calls = []
                for tc in tool_calls:
                    args = tc.get("args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    lc_tool_calls.append({
                        "name": tc["name"],
                        "args": args,
                        "id": tc["id"],
                    })
                lc_messages.append(AIMessage(content=content, tool_calls=lc_tool_calls))
            else:
                lc_messages.append(AIMessage(content=content))
        elif role == "tool":
            lc_messages.append(ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", ""),
            ))
        else:
            lc_messages.append(HumanMessage(content=content))

    return lc_messages


async def llm_call(state: ConversationState) -> ConversationState:
    """LLM 调用节点"""
    logger.info("LLM 调用开始", session_id=state.session_id, iteration=state.iteration_count)

    # 上游节点（如 knowledge_inject）已失败时跳过 LLM 调用，让 post_process 兜底补回复，
    # 保证 user/assistant 成对（条件边会因 state.error 路由到 post_process）
    if state.error:
        logger.warning("跳过 LLM 调用（上游节点已失败）", session_id=state.session_id, error=state.error)
        return state

    # 消息构建与工具绑定：编程错误直接抛出，不被 LLM 失败兜底掩盖
    llm = get_llm()

    # 构建消息列表：system + 历史对话 + 本轮编排
    messages = [{"role": "system", "content": state.system_prompt}]
    messages.extend(state.context_messages)       # 历史 user/assistant（含当前 user）
    messages.extend(state.conversation_history)   # 本轮 assistant(tool_call) + tool(result)

    # 获取工具定义
    tool_defs = get_all_tool_definitions()

    # 绑定工具
    if tool_defs:
        llm_with_tools = llm.bind_tools(tool_defs)
    else:
        llm_with_tools = llm

    # 转换消息（LangChain 消息对象）
    lc_messages = _convert_to_lc_messages(messages)

    # 仅 LLM 调用与响应解析纳入异常兜底（网络/API 错误 → 兜底回复）
    try:
        response = await llm_with_tools.ainvoke(lc_messages)

        # 解析响应
        state.llm_response = response.content or ""

        # 解析 tool_calls（确保 id 非空，args 为纯 dict）
        tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                args = tc.get("args") or tc.get("function", {}).get("arguments", {})
                # 处理 BaseModel / 字符串等情况
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                elif hasattr(args, "dict"):
                    args = args.dict()
                elif hasattr(args, "model_dump"):
                    args = args.model_dump()
                elif not isinstance(args, dict):
                    args = {}

                tool_id = tc.get("id", "")
                if not tool_id:
                    tool_id = f"call_{uuid.uuid4().hex[:16]}"

                tool_calls.append({
                    "name": tc.get("name") or tc.get("function", {}).get("name", ""),
                    "args": args,
                    "id": tool_id,
                })

        state.tool_calls = tool_calls

        # 将 assistant 消息加入 conversation_history
        assistant_msg = {"role": "assistant", "content": state.llm_response or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "name": tc["name"], "args": tc["args"]} for tc in tool_calls
            ]
        state.conversation_history.append(assistant_msg)

        # 执行事件
        state.events.append({
            "event": "llm_response",
            "data": {
                "has_tool_calls": len(tool_calls) > 0,
                "tool_count": len(tool_calls),
            },
        })

        logger.info(
            "LLM 调用完成",
            session_id=state.session_id,
            has_tool_calls=len(tool_calls) > 0,
            iteration=state.iteration_count,
        )

    except Exception as e:
        logger.error("LLM 调用失败", error=str(e))
        state.error = f"LLM 调用失败：{str(e)}"
        state.final_response = get_config().context.fallback_response

    return state
