"""知识注入测试"""

import pytest


def test_persona_cache_populated():
    """_load_persona() 加载后缓存被填充"""
    import app.memory.knowledge as knowledge_module

    # 重置缓存
    knowledge_module._persona_cache = None
    knowledge_module._persona_mtime = 0

    # 首次加载
    persona = knowledge_module._load_persona()
    assert persona is not None
    assert isinstance(persona, dict)

    # 验证缓存已填充
    assert knowledge_module._persona_cache is not None
    assert knowledge_module._persona_mtime > 0

    # 再次调用应返回缓存（同一对象）
    persona2 = knowledge_module._load_persona()
    assert persona2 is persona


def test_persona_returns_dict():
    """_load_persona() 返回字典"""
    from app.memory.knowledge import _load_persona

    persona = _load_persona()
    assert isinstance(persona, dict)
    assert "system_prompt" in persona


def test_format_time_context():
    """format_time_context() 返回包含日期和时间的字符串"""
    from app.memory.knowledge import format_time_context

    result = format_time_context()
    assert isinstance(result, str)
    assert len(result) > 0
    # 应包含日期和时间信息
    from datetime import datetime
    now = datetime.now()
    assert str(now.year) in result


@pytest.mark.asyncio
async def test_assemble_returns_tuple(setup_test_db):
    """assemble() 返回 (system_prompt, context_messages)"""
    from app.memory.knowledge import assemble

    system_prompt, context_messages = await assemble(
        user_id="test",
        session_id="test",
        user_message="hello",
    )
    assert isinstance(system_prompt, str)
    assert isinstance(context_messages, list)


@pytest.mark.asyncio
async def test_assemble_injects_tool_list(setup_test_db):
    """有已注册工具时，system_prompt 应包含工具列表（防止注入异常被静默吞掉）"""
    from app.memory.knowledge import assemble
    import app.plugins.loader as loader_module

    loader_module._tool_registry["fake_tool_xyz"] = {
        "executor": None,
        "definition": {"name": "fake_tool_xyz", "description": "测试工具"},
        "plugin": "test",
        "check_status": None,
    }
    try:
        system_prompt, _ = await assemble(
            user_id="test", session_id="test", user_message="hello",
        )
        assert "fake_tool_xyz" in system_prompt
    finally:
        loader_module._tool_registry.pop("fake_tool_xyz", None)