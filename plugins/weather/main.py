"""天气查询插件 - get_weather

配置说明：
    plugins/weather/config.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx2
import yaml

from app.common.logging import get_logger

logger = get_logger("weather_plugin")


def _load_config() -> dict:
    """加载插件配置文件"""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_CONFIG = _load_config()


async def get_weather(
    db: Any,
    user_id: str,
    session_id: str,
    args: dict,
) -> str:
    """查询天气（使用 wttr.in 免费 API）"""
    city = args.get("city", "")

    if not city:
        return "请提供城市名"

    weather_cfg = _CONFIG.get("weather", {})
    timeout = weather_cfg.get("timeout", 10)
    url_template = weather_cfg.get(
        "url_template",
        "https://wttr.in/{city}?format=%C|%t|%h|%w|%p&lang=zh",
    )

    try:
        url = url_template.format(city=city)
        async with httpx2.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        data = resp.text.strip()
        if "Unknown location" in data:
            return f"未找到城市「{city}」的天气信息"

        parts = data.split("|")
        if len(parts) >= 5:
            condition, temp, humidity, wind, precip = parts[:5]
            return (
                f"🌤 {city} 天气\n"
                f"天气状况：{condition}\n"
                f"温度：{temp}\n"
                f"湿度：{humidity}\n"
                f"风速：{wind}\n"
                f"降水量：{precip}"
            )
        return f"{city} 天气：{data}"

    except Exception as e:
        logger.error("天气查询失败", city=city, error=str(e))
        return f"天气查询失败：{str(e)}"