"""数据库连接管理测试"""

import pytest


class TestDatabaseEngine:
    """异步引擎和 session 工厂"""

    def test_get_engine_returns_engine(self, monkeypatch, tmp_path):
        """get_engine() 返回异步引擎"""
        import app.common.config as config_module
        import app.common.database as db_module
        from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

        db_path = tmp_path / "test_secretary.db"
        test_cfg = AppConfig(
            llm=LLMConfig(api_key="test-key", base_url="http://mock", model="mock"),
            auth=AuthConfig(api_keys=[]),
            database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
            chroma=ChromaConfig(persist_directory=str(tmp_path / "chroma")),
        )
        config_module._config = test_cfg
        db_module._engine = None
        db_module._session_factory = None

        engine = db_module.get_engine()
        assert engine is not None
        # 再次调用应返回同一引擎
        engine2 = db_module.get_engine()
        assert engine2 is engine

    def test_get_session_factory_returns_factory(self, monkeypatch, tmp_path):
        """get_session_factory() 返回 session 工厂"""
        import app.common.config as config_module
        import app.common.database as db_module
        from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

        db_path = tmp_path / "test_secretary.db"
        test_cfg = AppConfig(
            llm=LLMConfig(api_key="test-key", base_url="http://mock", model="mock"),
            auth=AuthConfig(api_keys=[]),
            database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
            chroma=ChromaConfig(persist_directory=str(tmp_path / "chroma")),
        )
        config_module._config = test_cfg
        db_module._engine = None
        db_module._session_factory = None

        factory = db_module.get_session_factory()
        assert factory is not None
        # 再次调用应返回同一工厂
        factory2 = db_module.get_session_factory()
        assert factory2 is factory

    @pytest.mark.asyncio
    async def test_close_db_disposes_engine(self, monkeypatch, tmp_path):
        """close_db() 释放引擎和 session 工厂"""
        import app.common.config as config_module
        import app.common.database as db_module
        from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

        db_path = tmp_path / "test_secretary.db"
        test_cfg = AppConfig(
            llm=LLMConfig(api_key="test-key", base_url="http://mock", model="mock"),
            auth=AuthConfig(api_keys=[]),
            database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
            chroma=ChromaConfig(persist_directory=str(tmp_path / "chroma")),
        )
        config_module._config = test_cfg
        db_module._engine = None
        db_module._session_factory = None

        # 先创建引擎
        _ = db_module.get_engine()
        assert db_module._engine is not None

        # 关闭
        await db_module.close_db()
        assert db_module._engine is None
        assert db_module._session_factory is None

    @pytest.mark.asyncio
    async def test_close_db_when_no_engine(self):
        """close_db() 在引擎为 None 时不报错"""
        import app.common.database as db_module

        db_module._engine = None
        db_module._session_factory = None
        await db_module.close_db()  # 不应抛异常