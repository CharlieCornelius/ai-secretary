"""
SearXNG 网页搜索插件

用法：
    1. 先启动 SearXNG：docker compose up -d
    2. 将本插件目录复制到 AI Secretary 的 plugins/ 目录下
    3. 重启 AI Secretary 服务
"""
from __future__ import annotations

import httpx
from pathlib import Path
from typing import Any
import yaml

# 插件加载时读取私有配置
_CONFIG: dict = {}

def _load_config() -> dict:
    """加载插件私有配置"""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

_CONFIG = _load_config()

# 从配置中读取 SearXNG 地址，支持环境变量覆盖
SEARXNG_URL = _CONFIG.get("searxng", {}).get("base_url", "http://localhost:8080")
TIMEOUT = _CONFIG.get("searxng", {}).get("timeout", 15)
DEFAULT_MAX_RESULTS = _CONFIG.get("searxng", {}).get("default_max_results", 5)


def _format_results(results: list[dict], query: str) -> str:
    """将 SearXNG 结果格式化为易读文本"""
    if not results:
        return f"未找到与「{query}」相关的结果。"

    header = f"搜索「{query}」的结果："
    lines = [header, ""]
    for i, r in enumerate(results, 1):
        title = r.get("title", "无标题").strip()
        url = r.get("url", "").strip()
        content = (r.get("content", "") or r.get("snippet", "")).strip()
        # 截断过长摘要
        if len(content) > 200:
            content = content[:200] + "..."
        lines.append(f"{i}. {title}")
        if content:
            lines.append(f"   {content}")
        if url:
            lines.append(f"   链接：{url}")
        lines.append("")

    return "\n".join(lines)


async def search_web(
    db: Any,
    user_id: str,
    session_id: str,
    args: dict,
) -> str:
    """
    通过 SearXNG 执行网页搜索。

    Args:
        db: SQLAlchemy AsyncSession（本插件未使用）
        user_id: 当前用户 ID
        session_id: 当前会话 ID
        args: LLM 传入的参数，包含 query 和可选的 max_results

    Returns:
        格式化后的搜索结果文本
    """
    query = args.get("query", "").strip()
    max_results = min(args.get("max_results", DEFAULT_MAX_RESULTS), 10)

    if not query:
        return "请提供搜索关键词。"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={
                    "q": query,
                    "format": "json",
                    "language": "zh-CN",
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AI-Secretary-Plugin/1.0",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])[:max_results]
        return _format_results(results, query)

    except httpx.ConnectError:
        return (
            f"无法连接到 SearXNG 搜索服务（{SEARXNG_URL}）。\n"
            "请确认：\n"
            "1. SearXNG 是否已启动：docker compose up -d\n"
            "2. config.yaml 中的 base_url 配置是否正确"
        )
    except httpx.TimeoutException:
        return "搜索请求超时，请稍后重试。"
    except Exception as e:
        return f"搜索失败：{str(e)}"


# ===== 可选：状态检测 =====
async def check_status() -> str | None:
    """
    检查 SearXNG 服务是否可用。
    返回 None 表示正常，返回字符串表示异常信息。
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{SEARXNG_URL}/healthz",
                headers={"User-Agent": "AI-Secretary-Plugin/1.0"},
            )
            if resp.status_code == 200:
                return None
            return f"SearXNG 状态异常（HTTP {resp.status_code}）"
    except Exception as e:
        return f"SearXNG 不可达：{str(e)}"
