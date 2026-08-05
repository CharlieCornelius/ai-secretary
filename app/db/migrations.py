"""简单迁移脚本 - 启动时自动执行"""

from __future__ import annotations

from app.common.logging import get_logger
from app.common.database import get_engine
from app.db.models import Base

logger = get_logger("migrations")


async def run_migrations() -> None:
    """启动时自动建表（若不存在）"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库迁移完成")