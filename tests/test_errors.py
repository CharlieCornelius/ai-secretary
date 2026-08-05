"""错误处理测试"""

import pytest

from app.common.errors import (
    AppError,
    AuthError,
    NotFoundError,
    PluginError,
    SessionError,
    ValidationError,
    format_error_response,
)


class TestErrorClasses:
    """错误类"""

    def test_app_error_base(self):
        err = AppError("test", code="TEST", status_code=418)
        assert err.message == "test"
        assert err.code == "TEST"
        assert err.status_code == 418

    def test_not_found_error(self):
        err = NotFoundError("resource")
        assert err.status_code == 404
        assert err.code == "NOT_FOUND"

    def test_auth_error(self):
        err = AuthError("bad key")
        assert err.status_code == 401
        assert err.code == "AUTH_ERROR"

    def test_validation_error(self):
        err = ValidationError("bad data")
        assert err.status_code == 422
        assert err.code == "VALIDATION_ERROR"

    def test_session_error(self):
        err = SessionError("expired")
        assert err.status_code == 400
        assert err.code == "SESSION_ERROR"

    def test_plugin_error(self):
        err = PluginError("load fail")
        assert err.status_code == 500
        assert err.code == "PLUGIN_ERROR"


class TestErrorResponseFormat:
    """错误响应格式"""

    def test_format_with_details(self):
        err = AppError("msg", code="X", details={"key": "val"})
        resp = format_error_response(err)
        assert resp["ok"] is False
        assert resp["error"]["code"] == "X"
        assert resp["error"]["details"] == {"key": "val"}

    def test_format_without_details(self):
        err = AppError("msg", code="X")
        resp = format_error_response(err)
        assert "details" not in resp["error"]


class TestErrorHandlers:
    """FastAPI 全局异常处理器"""

    def test_app_error_handler(self, client):
        """AppError 被正确处理"""
        # 访问不存在的会话触发 NotFoundError
        r = client.get("/api/v1/sessions/fake", headers={"X-API-Key": "test-api-key-123"})
        assert r.status_code == 404
        data = r.json()
        assert data["ok"] is False
        assert "error" in data
        assert "code" in data["error"]