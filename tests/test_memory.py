"""记忆系统测试"""

import pytest


class TestContext:
    """会话上下文（全量持久化到 DB）"""

    @pytest.mark.asyncio
    async def test_add_and_get(self, setup_test_db):
        from app.memory.context import add_message, get_context, clear_context

        sid = "test-s1-add-get"
        await clear_context(sid)
        await add_message(sid, "user", "hello")
        await add_message(sid, "assistant", "hi")
        ctx = await get_context(sid)
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        await clear_context(sid)

    @pytest.mark.asyncio
    async def test_context_limit(self, setup_test_db):
        from app.memory.context import add_message, get_context, clear_context

        sid = "test-s3-limit"
        await clear_context(sid)
        for i in range(50):
            await add_message(sid, "user", f"msg{i}")
        ctx = await get_context(sid)
        # max_context_turns 现按消息条数计（含 tool 消息）
        assert len(ctx) <= 20
        await clear_context(sid)


class TestExperience:
    """经验库（Chroma）"""

    @pytest.mark.asyncio
    async def test_store_and_search(self):
        from app.memory.experience import store_experience, search_experiences, clear_all_experiences

        await clear_all_experiences()
        await store_experience("用户喜欢简洁回复", category="test")
        results = await search_experiences("简洁", n_results=3)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_clear(self):
        from app.memory.experience import store_experience, clear_all_experiences, search_experiences

        await store_experience("test", category="test")
        await clear_all_experiences()
        results = await search_experiences("test", n_results=3)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_add_experience(self):
        from app.memory.experience import store_experience, search_experiences, clear_all_experiences

        await clear_all_experiences()
        await store_experience("手动添加的经验", category="manual")
        results = await search_experiences("手动", n_results=3)
        assert len(results) >= 1


class TestProfile:
    """用户画像（SQLite）"""

    @pytest.mark.asyncio
    async def test_get_or_create(self, setup_test_db):
        from app.common.database import get_session_factory
        from app.memory.profile import get_or_create_profile

        factory = get_session_factory()
        async with factory() as db:
            profile = await get_or_create_profile(db, "user-test")
            assert profile.user_id == "user-test"
            assert profile.memories == {}

    @pytest.mark.asyncio
    async def test_update_memories(self, setup_test_db):
        from app.common.database import get_session_factory
        from app.memory.profile import update_memories, get_profile

        factory = get_session_factory()
        async with factory() as db:
            await update_memories(db, "user-test-2", {"theme": "dark"})
            profile = await get_profile(db, "user-test-2")
            assert profile.memories["theme"] == "dark"