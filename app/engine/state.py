"""LangGraph 状态定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConversationState:
    """对话引擎状态 - 在 LangGraph 节点间流转"""

    # 基础信息
    user_id: str = ""
    session_id: str = ""
    session_mode: str = "single"  # "single" | "group"

    # 用户输入
    user_message: str = ""

    # 知识注入结果
    system_prompt: str = ""
    context_messages: list[dict] = field(default_factory=list)

    # 完整对话历史（供 LLM 多轮编排使用，包含 user/assistant/tool 消息）
    conversation_history: list[dict] = field(default_factory=list)

    # LLM 响应
    llm_response: str = ""
    tool_calls: list[dict] = field(default_factory=list)

    # 工具执行结果（当前轮次）
    tool_results: list[dict] = field(default_factory=list)

    # 累积的工具调用和结果（跨轮次，用于审计日志）
    all_tool_calls: list[dict] = field(default_factory=list)
    all_tool_results: list[dict] = field(default_factory=list)

    # 最终输出
    final_response: str = ""

    # 执行事件列表（用于追踪对话流程，非 SSE 协议）
    events: list[dict] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)     # 用户输入附件
    content_blocks: list[dict] = field(default_factory=list)  # AI 输出富内容

    # 多步编排计数
    iteration_count: int = 0

    # 错误
    error: Optional[str] = None
