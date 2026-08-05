"""插件系统测试"""

import pytest


class TestPluginLoader:
    """插件加载器"""

    def test_plugins_loaded(self):
        from app.plugins.loader import get_all_tool_definitions

        defs = get_all_tool_definitions()
        assert isinstance(defs, list)

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        from app.plugins.loader import execute_tool
        from app.common.errors import PluginError

        with pytest.raises(PluginError, match="未知工具"):
            await execute_tool("fake", None, "u1", "s1", {})


class TestToolReturnValues:
    """工具返回值：str 和 dict 格式"""

    def test_tool_executor_parses_str_result(self):
        """str 返回值：text 直接使用，无 content_blocks"""
        from app.engine.nodes.tool_executor import _parse_tool_result

        text, blocks = _parse_tool_result("搜索结果：xxx")
        assert text == "搜索结果：xxx"
        assert blocks == []

    def test_tool_executor_parses_dict_result(self):
        """dict 返回值：提取 text 和 content_blocks"""
        from app.engine.nodes.tool_executor import _parse_tool_result

        result = {
            "text": "分析完成",
            "content_blocks": [{"type": "image", "data": {"file": "chart.png"}}],
        }
        text, blocks = _parse_tool_result(result)
        assert text == "分析完成"
        assert len(blocks) == 1
        assert blocks[0]["type"] == "image"

    def test_tool_executor_dict_missing_text(self):
        """dict 返回值缺少 text 时，使用 str() 兜底"""
        from app.engine.nodes.tool_executor import _parse_tool_result

        result = {"content_blocks": []}
        text, blocks = _parse_tool_result(result)
        assert isinstance(text, str)
        assert blocks == []

    def test_tool_executor_dict_missing_content_blocks(self):
        """dict 返回值缺少 content_blocks 时，默认空列表"""
        from app.engine.nodes.tool_executor import _parse_tool_result

        result = {"text": "只返回文本"}
        text, blocks = _parse_tool_result(result)
        assert text == "只返回文本"
        assert blocks == []


class TestQueryProfilePlugin:
    """query_profile 插件：支持 user_id 和 name 查询"""

    def test_format_profile_basic(self):
        """格式化画像：基本字段"""
        from plugins.profile_query.main import _format_profile

        formatted = _format_profile("u1", {"name": "张三", "role": "开发者"})
        assert "u1" in formatted
        assert "张三" in formatted
        assert "开发者" in formatted

    def test_format_profile_with_display_name(self):
        """格式化画像：使用 display_name 替代 user_id 显示"""
        from plugins.profile_query.main import _format_profile

        formatted = _format_profile("u1", {"name": "张三"}, display_name="张三")
        assert "张三" in formatted
        assert "u1" in formatted

    @pytest.mark.asyncio
    async def test_query_profile_args_validation(self):
        """参数验证：user_id 和 name 至少提供一个"""
        from plugins.profile_query.main import query_profile

        result = await query_profile({}, "u1", "s1", {})
        assert "至少提供一个" in result

    @pytest.mark.asyncio
    async def test_query_profile_by_user_id(self, setup_test_db):
        """按 user_id 查询画像"""
        from plugins.profile_query.main import query_profile
        from app.memory.profile import update_memories
        from app.common.database import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            await update_memories(db, "query-test-user", {"name": "测试用户"})
            result = await query_profile(db, "u1", "s1", {"user_id": "query-test-user"})

        assert "query-test-user" in result
        assert "测试用户" in result

    @pytest.mark.asyncio
    async def test_query_profile_not_found(self, setup_test_db):
        """查询不存在的用户画像"""
        from plugins.profile_query.main import query_profile
        from app.common.database import get_session_factory

        factory = get_session_factory()
        async with factory() as db:
            result = await query_profile(db, "u1", "s1", {"user_id": "nonexistent-user"})

        assert "未找到" in result or "无" in result
