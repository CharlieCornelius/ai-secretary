"""插件系统 - 运行时发现、加载、注册工具"""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from typing import Any, Callable

from app.common.config import get_config
from app.common.errors import PluginError
from app.common.logging import get_logger

logger = get_logger("plugins")

# 工具注册表：tool_name -> {"executor": callable, "definition": dict, "plugin": str, "check_status": callable}
_tool_registry: dict[str, dict] = {}

# 插件信息列表
_plugins: list[dict] = []


def register_tool(
    name: str,
    definition: dict,
    executor: Callable,
    *,
    plugin_name: str = "builtin",
    check_status: Callable | None = None,
) -> None:
    """注册工具到全局注册表"""
    _tool_registry[name] = {
        "executor": executor,
        "definition": definition,
        "plugin": plugin_name,
        "check_status": check_status,
    }
    logger.info("工具已注册", tool_name=name, plugin=plugin_name)


def has_tools() -> bool:
    """是否有已注册的工具"""
    return bool(_tool_registry)


def get_all_tool_definitions() -> list[dict]:
    """获取所有工具定义（用于 LLM tool 列表）"""
    return [info["definition"] for info in _tool_registry.values()]


def get_plugin_list() -> list[dict]:
    """获取已加载插件列表"""
    return _plugins.copy()


async def execute_tool(
    tool_name: str,
    db: Any,
    user_id: str,
    session_id: str,
    args: dict,
) -> str | dict:
    """执行工具（调用前可选状态检测）

    返回值:
        str: 纯文本结果（向后兼容）
        dict: 结构化结果，格式 {"text": str, "content_blocks": list[dict]}
    """
    tool = _tool_registry.get(tool_name)
    if tool is None:
        raise PluginError(f"未知工具：{tool_name}")

    # 状态检测（可选，由插件自主实现）
    check_status = tool.get("check_status")
    if check_status:
        try:
            if asyncio.iscoroutinefunction(check_status):
                status_msg = await check_status()
            else:
                status_msg = check_status()
            if status_msg is not None:
                # 插件返回错误消息，直接返回给 LLM（带工具名前缀），不执行
                return f"[{tool_name}] {status_msg}"
        except Exception as e:
            # 状态检测异常应视为不可用，而非放行执行
            logger.warning("状态检测异常，工具不可用", tool_name=tool_name, error=str(e))
            return f"[{tool_name}] 状态检测异常：{str(e)}"

    executor = tool["executor"]
    try:
        result = await executor(db, user_id, session_id, args)
        return result
    except Exception as e:
        logger.error("工具执行失败", tool_name=tool_name, error=str(e))
        raise PluginError(f"工具执行失败：{tool_name} - {str(e)}")


def load_plugins() -> None:
    """加载插件（plugins/ 目录）"""
    plugins_dir = Path(get_config().plugins.directory)

    if not plugins_dir.exists():
        return

    for plugin_path in plugins_dir.iterdir():
        if not plugin_path.is_dir():
            continue

        manifest_path = plugin_path / "manifest.yaml"
        if not manifest_path.exists():
            logger.warning("插件缺少 manifest.yaml", path=str(plugin_path))
            continue

        try:
            import yaml
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {}

            plugin_name = manifest.get("name", plugin_path.name)

            # 启用开关
            if not manifest.get("enabled", True):
                logger.info("插件已禁用", plugin=plugin_name)
                continue
            plugin_version = manifest.get("version", "0.0.1")
            plugin_description = manifest.get("description", "")
            tool_defs = manifest.get("tools", [])

            # 动态导入插件模块
            module_name = f"plugins.{plugin_path.name}.main"
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                logger.warning("插件模块导入失败", plugin=plugin_name)
                continue

            registered_tools = []
            for tool_def in tool_defs:
                tool_name = tool_def["name"]
                executor = getattr(module, tool_name, None)
                if executor is None:
                    logger.warning("插件工具未找到", tool=tool_name, plugin=plugin_name)
                    continue

                check_status = getattr(module, "check_status", None)
                register_tool(
                    name=tool_name,
                    definition=tool_def,
                    executor=executor,
                    plugin_name=plugin_name,
                    check_status=check_status,
                )
                registered_tools.append(tool_name)

            _plugins.append({
                "name": plugin_name,
                "version": plugin_version,
                "description": plugin_description,
                "tools": registered_tools,
            })
            logger.info("外部插件已加载", plugin=plugin_name, tools=registered_tools)

        except Exception as e:
            logger.error("插件加载失败", path=str(plugin_path), error=str(e))


def init_plugins() -> None:
    """初始化插件"""
    load_plugins()
    logger.info("插件系统初始化完成", total_tools=len(_tool_registry), total_plugins=len(_plugins))