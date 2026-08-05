"""统一错误定义与处理器"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.common.logging import get_logger

logger = get_logger("errors")


class AppError(Exception):
    """应用错误基类"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Any = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    """404 资源不存在"""

    def __init__(self, message: str = "资源不存在", details: Any = None):
        super().__init__(message, code="NOT_FOUND", status_code=404, details=details)


class AuthError(AppError):
    """401 认证失败"""

    def __init__(self, message: str = "认证失败", details: Any = None):
        super().__init__(message, code="AUTH_ERROR", status_code=401, details=details)


class ValidationError(AppError):
    """422 数据校验失败"""

    def __init__(self, message: str = "数据校验失败", details: Any = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422, details=details)


class SessionError(AppError):
    """会话相关错误"""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message, code="SESSION_ERROR", status_code=400, details=details)


class PluginError(AppError):
    """插件加载/执行错误"""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message, code="PLUGIN_ERROR", status_code=500, details=details)


def format_error_response(error: AppError) -> dict:
    """格式化错误响应"""
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message,
            **({"details": error.details} if error.details else {}),
        },
    }


def register_error_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(exc),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("未捕获异常", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content=format_error_response(
                AppError(message="内部服务器错误", code="INTERNAL_ERROR")
            ),
        )
