"""API Key 认证中间件 - 纯认证，不携带用户信息"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from app.common.config import get_config
from app.common.errors import AuthError
from app.common.logging import get_logger

logger = get_logger("auth")

# 合法 API Key 集合（启动时加载）
_valid_keys: set[str] = set()
# 请求头提取器（启动时从配置加载 header 名；缺省 X-API-Key）
_api_key_header: APIKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)


def init_auth() -> None:
    """初始化认证：从配置加载合法 API Key 列表与请求头名"""
    global _valid_keys, _api_key_header
    config = get_config()
    _valid_keys.clear()

    for key in config.auth.api_keys:
        if key:
            _valid_keys.add(key)

    _api_key_header = APIKeyHeader(name=config.auth.api_key_header, auto_error=False)

    logger.info("认证初始化完成", key_count=len(_valid_keys), header=config.auth.api_key_header)


async def _extract_api_key(request: Request) -> str | None:
    """从请求中提取 API Key（运行时读取当前 header 提取器，支持配置热更新）"""
    return await _api_key_header(request)


async def verify_api_key(api_key: str | None = Depends(_extract_api_key)) -> None:
    """验证 API Key 是否有效 - 仅认证，不返回用户信息
    api_keys 为空列表时跳过认证（无需 API Key）"""
    # 未配置任何 API Key → 开放访问
    if not _valid_keys:
        return

    if not api_key:
        raise AuthError(f"缺少 API Key，请在请求头中添加 {get_config().auth.api_key_header}")

    if api_key not in _valid_keys:
        raise AuthError("无效的 API Key")
