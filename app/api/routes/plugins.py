"""插件路由 - 查看已加载插件"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.common.auth import verify_api_key
from app.common.schemas import OkResponse, PluginResponse
from app.plugins.loader import get_plugin_list

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("", response_model=OkResponse[list[PluginResponse]])
async def list_plugins(
    _: None = Depends(verify_api_key),
):
    """列出已加载插件"""
    plugins = get_plugin_list()
    return OkResponse(data=[
        PluginResponse(
            name=p["name"],
            version=p["version"],
            description=p.get("description"),
            tools=p.get("tools", []),
        )
        for p in plugins
    ])