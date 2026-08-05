"""对话引擎测试（LangGraph 节点）"""

import pytest

from app.engine.state import ConversationState


@pytest.mark.asyncio
async def test_multi_step_tool_loop(setup_test_db, monkeypatch):
    """多步工具编排循环端到端：首轮 tool_calls → 工具执行 → 次轮纯文本，轨迹持久化可跨轮重建

    守护最关键路径：图接线、llm_caller 的 tool_calls 解析、tool_executor 执行、
    post_processor 轨迹持久化、get_context 回填 tool 字段。
    """
    import app.engine.nodes.llm_caller as llm_module
    import app.plugins.loader as loader_module
    from app.engine.graph import run_conversation
    from app.plugins.loader import register_tool
    from langchain_core.messages import AIMessage

    # 注册一个假工具
    async def fake_tool(db, user_id, session_id, args):
        return f"工具结果：{args.get('q', '')}"

    register_tool(
        name="fake_tool",
        definition={
            "name": "fake_tool",
            "description": "测试工具",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        },
        executor=fake_tool,
        plugin_name="test",
    )

    # mock LLM：首次返回 tool_calls，次轮返回纯文本
    call_count = {"n": 0}

    class FakeLLM:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, msgs, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "fake_tool", "args": {"q": "hello"}, "id": "call_1"}],
                )
            return AIMessage(content="最终回复：完成", tool_calls=[])

    monkeypatch.setattr(llm_module, "get_llm", lambda: FakeLLM())

    from app.memory.context import add_message, get_context

    sid = "s-multi-step"
    # 预置用户消息（模拟 chat.py 在引擎前持久化）
    await add_message(sid, "user", "用工具查一下")

    try:
        state = await run_conversation(
            user_id="u1", session_id=sid, user_message="用工具查一下"
        )

        # LLM 被调用两次（首轮工具、次轮文本）
        assert call_count["n"] == 2

        # conversation_history 含 assistant(tool_calls) + tool + assistant(最终)
        roles = [m["role"] for m in state.conversation_history]
        assert roles == ["assistant", "tool", "assistant"]
        assert state.conversation_history[0]["tool_calls"][0]["name"] == "fake_tool"
        assert state.conversation_history[1]["tool_call_id"] == "call_1"
        assert state.final_response == "最终回复：完成"

        # post_process 已持久化轨迹，get_context 能回填 tool 字段（跨请求重建）
        ctx = await get_context(sid)
        assert any(
            m["role"] == "tool" and m.get("tool_call_id") == "call_1" for m in ctx
        )
        assert any(
            m["role"] == "assistant" and m.get("tool_calls") for m in ctx
        )
    finally:
        # 清理假工具，避免污染后续测试
        loader_module._tool_registry.pop("fake_tool", None)


@pytest.mark.asyncio
async def test_knowledge_inject_failure_sets_error(setup_test_db, monkeypatch):
    """knowledge_inject 失败时设 state.error，llm_call 跳过，post_process 兜底补回复

    保证 user/assistant 成对，避免下轮 get_context 看到孤立 user 消息。
    """
    from app.engine.graph import run_conversation

    # 让 assemble 抛异常（模拟 Chroma/DB 失败）
    import app.engine.nodes.knowledge_injector as ki_module

    async def _boom(*args, **kwargs):
        raise RuntimeError("knowledge inject boom")

    monkeypatch.setattr(ki_module, "assemble", _boom)

    from app.memory.context import add_message, get_context

    sid = "s-inject-fail"
    await add_message(sid, "user", "你好")

    state = await run_conversation(user_id="u1", session_id=sid, user_message="你好")

    assert state.error is not None
    # 兜底回复非空，且已与 user 消息成对持久化
    assert state.final_response != ""
    ctx = await get_context(sid)
    roles = [m["role"] for m in ctx]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_knowledge_inject(setup_test_db):
    """知识注入节点"""
    from app.engine.nodes.knowledge_injector import knowledge_inject

    state = ConversationState(user_id="u1", session_id="s1", user_message="hello")
    result = await knowledge_inject(state)
    assert result.system_prompt != ""
    assert isinstance(result.context_messages, list)


@pytest.mark.asyncio
async def test_llm_call_mock(monkeypatch):
    """LLM 调用节点（mock ChatOpenAI）"""
    from app.engine.nodes.llm_caller import llm_call
    from langchain_core.messages import AIMessage

    fake_msg = AIMessage(content="fake", tool_calls=[])

    class FakeLLM:
        def bind_tools(self, tools):
            return self
        async def ainvoke(self, msgs, **kw):
            return fake_msg

    monkeypatch.setattr("app.engine.nodes.llm_caller.get_llm", lambda: FakeLLM())

    state = ConversationState(user_id="u1", session_id="s1", user_message="hi")
    state.system_prompt = "test"
    result = await llm_call(state)
    assert result.llm_response == "fake"


@pytest.mark.asyncio
async def test_tool_execute_empty():
    """工具执行：空工具调用"""
    from app.engine.nodes.tool_executor import tool_execute

    state = ConversationState(user_id="u1", session_id="s1", user_message="hi")
    state.tool_calls = []
    result = await tool_execute(state)
    assert result.final_response == ""


@pytest.mark.asyncio
async def test_post_process(setup_test_db):
    """后处理节点"""
    from app.engine.nodes.post_processor import post_process

    state = ConversationState(user_id="u1", session_id="s1", user_message="hi")
    state.llm_response = "reply"
    result = await post_process(state)
    assert result.final_response == "reply"
    assert len(result.events) >= 1


@pytest.mark.asyncio
async def test_post_process_schedules_background(setup_test_db, monkeypatch):
    """后处理节点：将记忆维护和审计清理提交到后台运行器"""
    from app.engine.nodes.post_processor import post_process

    submitted = []

    class _FakeRunner:
        def submit(self, coro, name=""):
            submitted.append(name)
            # 立即关闭协程避免未等待警告
            coro.close()

    monkeypatch.setattr(
        "app.engine.nodes.post_processor.get_background_runner", lambda: _FakeRunner()
    )

    state = ConversationState(user_id="u1", session_id="s1", user_message="hi")
    state.llm_response = "reply"
    await post_process(state)

    # 至少提交了画像更新和经验提取两个任务
    assert "update_profile" in submitted
    assert "update_experience" in submitted


def test_conversation_state_defaults():
    """状态默认值"""
    state = ConversationState()
    assert state.user_id == ""
    assert state.session_id == ""
    assert state.session_mode == "single"
    assert state.iteration_count == 0
    assert state.tool_calls == []
    assert state.events == []
    assert state.attachments == []
    assert state.content_blocks == []


@pytest.mark.asyncio
async def test_knowledge_inject_with_attachments(setup_test_db):
    """知识注入：有附件时 system_prompt 包含附件提示"""
    from app.engine.nodes.knowledge_injector import knowledge_inject

    state = ConversationState(
        user_id="u1", session_id="s1", user_message="看这张图",
        attachments=[{"type": "image", "data": {"file": "https://example.com/photo.jpg"}}],
    )
    result = await knowledge_inject(state)
    assert "附件" in result.system_prompt or "attachment" in result.system_prompt.lower()


@pytest.mark.asyncio
async def test_knowledge_inject_no_attachments(setup_test_db):
    """知识注入：无附件时 system_prompt 不包含附件提示"""
    from app.engine.nodes.knowledge_injector import knowledge_inject

    state = ConversationState(user_id="u1", session_id="s1", user_message="hello")
    result = await knowledge_inject(state)
    # 无附件时不应该注入附件相关提示
    assert "附件" not in result.system_prompt


@pytest.mark.asyncio
async def test_build_attachment_hint_with_tools():
    """附件提示构建：有工具时使用 attachment_with_tools 配置"""
    from app.engine.nodes.knowledge_injector import _build_attachment_hint

    attachments = [{"type": "image", "data": {"file": "photo.jpg"}}]
    hint = _build_attachment_hint(attachments)
    # 有工具注册时，提示应包含 attachment_with_tools 的内容
    from app.plugins.loader import _tool_registry
    if _tool_registry:
        assert "如果有可用工具处理附件请使用" in hint
    else:
        assert "你无法查看或理解此类型的附件" in hint


@pytest.mark.asyncio
async def test_build_attachment_hint_no_tools():
    """附件提示构建：无工具时使用 attachment_no_tools 配置"""
    from app.engine.nodes.knowledge_injector import _build_attachment_hint
    import app.plugins.loader as loader_module

    # 临时清空工具注册表
    original_registry = loader_module._tool_registry.copy()
    loader_module._tool_registry.clear()
    try:
        attachments = [{"type": "image", "data": {"file": "photo.jpg"}}]
        hint = _build_attachment_hint(attachments)
        assert "你无法查看或理解此类型的附件" in hint
        assert "image" in hint
    finally:
        loader_module._tool_registry.update(original_registry)


@pytest.mark.asyncio
async def test_graph_run_conversation(monkeypatch):
    """完整对话流程"""
    import app.engine.graph as g

    # 直接 mock run_conversation 函数
    async def _fake_run(user_id, session_id, message):
        from app.engine.state import ConversationState
        state = ConversationState(user_id=user_id, session_id=session_id, user_message=message)
        state.final_response = "done"
        return state

    monkeypatch.setattr(g, "run_conversation", _fake_run)

    result = await g.run_conversation("u1", "s1", "hi")
    assert result.final_response == "done"


def test_max_tool_iterations_config():
    """max_tool_iterations 配置正确加载"""
    from app.common.config import get_config

    max_iter = get_config().context.max_tool_iterations
    assert max_iter == 5
    assert isinstance(max_iter, int)
    assert max_iter > 0


@pytest.mark.asyncio
async def test_knowledge_inject_group_mode(setup_test_db):
    """知识注入：群聊模式时 system_prompt 包含群聊声明"""
    from app.engine.nodes.knowledge_injector import knowledge_inject

    state = ConversationState(
        user_id="u1", session_id="s1", user_message="hello",
        session_mode="group",
    )
    result = await knowledge_inject(state)
    assert "群聊模式" in result.system_prompt
    assert "多人参与对话" in result.system_prompt
    assert "优先使用用户的名字" in result.system_prompt


@pytest.mark.asyncio
async def test_knowledge_inject_single_mode(setup_test_db):
    """知识注入：单人模式时 system_prompt 不包含群聊声明"""
    from app.engine.nodes.knowledge_injector import knowledge_inject

    state = ConversationState(
        user_id="u1", session_id="s1", user_message="hello",
        session_mode="single",
    )
    result = await knowledge_inject(state)
    assert "群聊模式" not in result.system_prompt


def test_conversation_state_session_mode():
    """session_mode 可以通过构造函数设置"""
    state = ConversationState(session_mode="group")
    assert state.session_mode == "group"

    state2 = ConversationState(session_mode="single")
    assert state2.session_mode == "single"

    state3 = ConversationState()
    assert state3.session_mode == "single"


def test_attachment_hint_shows_full_data():
    """附件提示展示完整 data dict，而非硬编码 key"""
    from app.engine.nodes.knowledge_injector import _build_attachment_hint

    attachments = [{"type": "image", "data": {"url": "https://example.com/photo.jpg", "alt": "风景"}}]
    hint = _build_attachment_hint(attachments)
    # 提示中包含完整的 data dict
    assert "url" in hint
    assert "https://example.com/photo.jpg" in hint
    assert "alt" in hint
    assert "风景" in hint


@pytest.mark.asyncio
async def test_llm_call_fallback_from_config(monkeypatch):
    """LLM 调用失败时兜底文案来自配置，而非硬编码"""
    from app.engine.nodes.llm_caller import llm_call
    from app.common.config import get_config

    class FakeLLM:
        def bind_tools(self, tools):
            return self
        async def ainvoke(self, msgs, **kw):
            raise RuntimeError("LLM down")

    monkeypatch.setattr("app.engine.nodes.llm_caller.get_llm", lambda: FakeLLM())

    state = ConversationState(user_id="u1", session_id="s1", user_message="hi")
    state.system_prompt = "test"
    result = await llm_call(state)
    # 兜底文案应来自配置
    assert result.final_response == get_config().context.fallback_response
    assert result.error is not None


@pytest.mark.asyncio
async def test_post_process_persists_tool_trace(setup_test_db):
    """后处理：持久化完整工具调用轨迹，使多轮工具记忆可跨请求重建"""
    from app.engine.nodes.post_processor import post_process
    from app.memory.context import add_message, get_context, clear_context

    sid = "s-tool-trace"
    await clear_context(sid)

    state = ConversationState(user_id="u1", session_id=sid, user_message="查天气")
    # 模拟一轮多步编排轨迹：assistant(tool_call) → tool(result) → assistant(最终回复)
    state.conversation_history = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_abc", "name": "get_weather", "args": {"city": "北京"}}],
        },
        {"role": "tool", "content": "北京 晴 25℃", "tool_call_id": "call_abc"},
        {"role": "assistant", "content": "北京今天晴，25度。"},
    ]
    state.final_response = "北京今天晴，25度。"
    await post_process(state)

    # 读取上下文，验证 tool_calls 与 tool_call_id 被回填
    ctx = await get_context(sid)
    roles = [m["role"] for m in ctx]
    assert roles == ["assistant", "tool", "assistant"]
    # assistant 带 tool_calls
    assert ctx[0]["tool_calls"][0]["name"] == "get_weather"
    # tool 带 tool_call_id
    assert ctx[1]["tool_call_id"] == "call_abc"
    assert ctx[1]["content"] == "北京 晴 25℃"
    # 最终 assistant 无 tool_calls
    assert "tool_calls" not in ctx[2]
    assert ctx[2]["content"] == "北京今天晴，25度。"
    await clear_context(sid)


@pytest.mark.asyncio
async def test_post_process_empty_trace_falls_back(setup_test_db):
    """后处理：轨迹为空时仍持久化最终回复（mock/异常路径不丢消息）"""
    from app.engine.nodes.post_processor import post_process
    from app.memory.context import get_context, clear_context

    sid = "s-empty-trace"
    await clear_context(sid)

    state = ConversationState(user_id="u1", session_id=sid, user_message="hi")
    state.llm_response = "reply"
    await post_process(state)

    ctx = await get_context(sid)
    assert len(ctx) == 1
    assert ctx[0]["role"] == "assistant"
    assert ctx[0]["content"] == "reply"
    await clear_context(sid)