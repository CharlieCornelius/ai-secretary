"""pytest 配置和共享 fixtures"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保能找到 app 包
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient


# ─── 会话级临时目录（所有测试共享） ───
_test_tmp_dir: Path | None = None


@pytest.fixture(scope="session", autouse=True)
def _session_tmp_dir(tmp_path_factory):
    """创建会话级临时目录，供 autouse 数据隔离 fixture 使用"""
    global _test_tmp_dir
    _test_tmp_dir = tmp_path_factory.mktemp("ai_secretary_test_data")
    yield
    _test_tmp_dir = None


@pytest.fixture(autouse=True)
def _isolate_test_data():
    """确保每个测试使用临时目录，不留下脏文件/脏数据/脏目录

    - 测试前：将配置的数据路径重定向到临时目录，重置 DB 引擎和 Chroma 缓存
    - 测试后：重置 DB 引擎和 Chroma 缓存，防止状态泄漏
    - 对于显式调用 init_config() 的测试（如 test_config.py），
      它们会自行设置 _config = None 再调用 init_config()，
      此时数据路径会指向真实目录，但这些测试只读取配置不创建文件，不受影响
    """
    import app.common.background as background_module
    import app.common.config as config_module
    import app.common.database as db_module
    import app.memory.experience as exp_module

    # 重置数据库引擎、Chroma 缓存和后台任务运行器（避免前一个测试的状态泄漏）
    db_module._engine = None
    db_module._session_factory = None
    exp_module._client = None
    exp_module._collection = None
    background_module._runner = None

    # 确保配置存在且数据路径指向临时目录
    if _test_tmp_dir is not None:
        if config_module._config is None:
            # 配置未加载，创建最小测试配置（避免 get_config() 加载真实路径）
            from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig
            config_module._config = AppConfig(
                llm=LLMConfig(api_key="test-key", base_url="http://mock", model="mock"),
                auth=AuthConfig(api_keys=[]),
                database=DatabaseConfig(url=f"sqlite+aiosqlite:///{_test_tmp_dir / 'test_secretary.db'}"),
                chroma=ChromaConfig(persist_directory=str(_test_tmp_dir / "chroma")),
            )
        else:
            # 配置已加载，重定向数据路径到临时目录
            cfg = config_module._config
            cfg.database.url = f"sqlite+aiosqlite:///{_test_tmp_dir / 'test_secretary.db'}"
            cfg.chroma.persist_directory = str(_test_tmp_dir / "chroma")

    yield

    # 清理：重置数据库引擎、Chroma 缓存和后台任务运行器
    db_module._engine = None
    db_module._session_factory = None
    exp_module._client = None
    exp_module._collection = None
    background_module._runner = None


@pytest.fixture
def client(monkeypatch, tmp_path):
    """创建 FastAPI TestClient（全局 mock LLM，避免 API 调用）"""
    import app.engine.graph as graph_module
    import app.engine.nodes.llm_caller as llm_module

    async def _fake_llm(state):
        """全局 mock LLM：返回空响应，无工具调用"""
        state.llm_response = "mock response"
        state.tool_calls = []
        state.events.append({
            "event": "llm_response",
            "data": {"has_tool_calls": False, "tool_count": 0},
        })
        return state

    # mock LLM 调用
    monkeypatch.setattr(graph_module, "llm_call", _fake_llm)
    monkeypatch.setattr(llm_module, "llm_call", _fake_llm)
    monkeypatch.setattr(graph_module, "_compiled_graph", None)

    # 完全绕过配置文件系统，直接注入测试配置
    import app.common.config as config_module
    import app.common.database as db_module
    from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

    # 使用临时目录的数据库，避免 data/ 目录不存在的问题
    db_path = tmp_path / "test_secretary.db"
    chroma_path = tmp_path / "chroma"

    test_cfg = AppConfig(
        llm=LLMConfig(api_key="test-mock-key", base_url="http://mock", model="mock-model"),
        auth=AuthConfig(api_keys=["test-api-key-123"]),
        database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
        chroma=ChromaConfig(persist_directory=str(chroma_path)),
    )
    config_module._config = test_cfg

    # 重置数据库引擎，确保使用新配置
    db_module._engine = None
    db_module._session_factory = None

    # 让 init_config 直接返回测试配置
    def _fake_init_config(*args, **kwargs):
        return test_cfg

    monkeypatch.setattr(config_module, "init_config", _fake_init_config)

    from app.main import create_app
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    # 清理：关闭数据库连接
    import asyncio
    try:
        asyncio.run(db_module.close_db())
    except Exception:
        pass


@pytest.fixture
def auth_headers():
    """测试用的认证请求头"""
    return {"X-API-Key": "test-api-key-123"}


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return "test-user-123"


@pytest.fixture
async def setup_test_db(tmp_path, monkeypatch):
    """为直接调用引擎节点的测试提供临时数据库（含建表）"""
    import app.common.config as config_module
    import app.common.database as db_module
    from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

    db_path = tmp_path / "test_secretary.db"
    chroma_path = tmp_path / "chroma"

    test_cfg = AppConfig(
        llm=LLMConfig(api_key="test-mock-key", base_url="http://mock", model="mock-model"),
        auth=AuthConfig(api_keys=["test-api-key-123"]),
        database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
        chroma=ChromaConfig(persist_directory=str(chroma_path)),
    )
    config_module._config = test_cfg

    # 重置数据库引擎
    db_module._engine = None
    db_module._session_factory = None

    # 让 init_config 直接返回测试配置
    def _fake_init_config(*args, **kwargs):
        return test_cfg
    monkeypatch.setattr(config_module, "init_config", _fake_init_config)

    # 建表
    from app.db.migrations import run_migrations
    await run_migrations()

    yield test_cfg

    # 清理
    await db_module.close_db()
    db_module._engine = None
    db_module._session_factory = None