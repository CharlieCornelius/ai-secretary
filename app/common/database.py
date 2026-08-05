"""SQLite 异步连接管理"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.config import get_config

_engine = None
_session_factory = None


def get_engine():
    """获取异步引擎"""
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_async_engine(
            config.database.url,
            echo=config.database.echo,
            pool_pre_ping=config.database.pool_pre_ping,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取 session 工厂"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：获取数据库 session"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """关闭数据库连接"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None