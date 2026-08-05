"""认证中间件测试"""

import pytest
from fastapi.testclient import TestClient


def test_health_no_auth_required(client):
    """健康检查无需认证"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ai-secretary"


def test_api_with_valid_key(client, auth_headers):
    """有效 API Key 可通过认证"""
    response = client.get("/api/v1/sessions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_api_with_invalid_key(client):
    """无效 API Key 被拒绝"""
    response = client.get("/api/v1/sessions", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "AUTH_ERROR"


@pytest.fixture
def no_auth_client(monkeypatch, tmp_path):
    """创建无需认证的 TestClient（api_keys 为空列表）"""
    import app.common.config as config_module
    import app.common.database as db_module
    from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

    db_path = tmp_path / "test_secretary.db"
    test_cfg = AppConfig(
        llm=LLMConfig(api_key="test-mock-key", base_url="http://mock", model="mock-model"),
        auth=AuthConfig(api_keys=[]),  # 空列表 = 无需认证
        database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
        chroma=ChromaConfig(persist_directory=str(tmp_path / "chroma")),
    )
    config_module._config = test_cfg
    db_module._engine = None
    db_module._session_factory = None

    def _fake_init_config(*args, **kwargs):
        return test_cfg
    monkeypatch.setattr(config_module, "init_config", _fake_init_config)

    from app.main import create_app
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_no_api_key_required(no_auth_client):
    """api_keys 为空时，无需认证即可访问"""
    # 不带 X-API-Key
    response = no_auth_client.get("/api/v1/sessions")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


@pytest.fixture
def multi_key_client(monkeypatch, tmp_path):
    """创建多 API Key 的 TestClient"""
    import app.common.config as config_module
    import app.common.database as db_module
    from app.common.config import AppConfig, LLMConfig, AuthConfig, DatabaseConfig, ChromaConfig

    db_path = tmp_path / "test_secretary.db"
    test_cfg = AppConfig(
        llm=LLMConfig(api_key="test-mock-key", base_url="http://mock", model="mock-model"),
        auth=AuthConfig(api_keys=["key1", "key2", "key3"]),
        database=DatabaseConfig(url=f"sqlite+aiosqlite:///{db_path}"),
        chroma=ChromaConfig(persist_directory=str(tmp_path / "chroma")),
    )
    config_module._config = test_cfg
    db_module._engine = None
    db_module._session_factory = None

    def _fake_init_config(*args, **kwargs):
        return test_cfg
    monkeypatch.setattr(config_module, "init_config", _fake_init_config)

    from app.main import create_app
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("valid_key", ["key1", "key2", "key3"])
def test_multi_key_any_valid(multi_key_client, valid_key):
    """多个 API Key 中任意一个有效即可通过"""
    response = multi_key_client.get("/api/v1/sessions", headers={"X-API-Key": valid_key})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_multi_key_invalid_rejected(multi_key_client):
    """多个 API Key 配置下，无效 key 被拒绝"""
    response = multi_key_client.get("/api/v1/sessions", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401
    data = response.json()
    assert data["ok"] is False


def test_multi_key_missing_rejected(multi_key_client):
    """多个 API Key 配置下，未提供 key 被拒绝"""
    response = multi_key_client.get("/api/v1/sessions")
    assert response.status_code == 401
    data = response.json()
    assert data["ok"] is False