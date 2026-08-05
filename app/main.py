"""AI Secretary 主入口 - FastAPI 应用工厂"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api.router import api_router
from app.common.background import shutdown_background
from app.common.config import get_config, init_config
from app.common.database import close_db
from app.common.errors import register_error_handlers
from app.common.logging import get_logger, setup_logging
from app.db.migrations import run_migrations
from app.plugins.loader import init_plugins


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # === 启动 ===
    config = init_config()
    setup_logging()
    logger = get_logger("main")

    logger.info("AI Secretary 启动中...")

    # 确保数据目录存在
    import os
    import pathlib
    chroma_dir = pathlib.Path(config.chroma.persist_directory)
    dirs_to_create = [chroma_dir]
    # 仅 sqlite 需要预建目录；_resolve_data_paths 已解析为绝对路径，
    # URL 形如 sqlite+aiosqlite:///<abs_path>，去掉前缀取文件路径
    db_url = config.database.url
    if db_url.startswith("sqlite+aiosqlite:///"):
        db_path_str = db_url[len("sqlite+aiosqlite:///"):]
        if db_path_str:
            dirs_to_create.append(pathlib.Path(db_path_str).parent)
    for d in dirs_to_create:
        os.makedirs(d, exist_ok=True)

    # 数据库迁移
    await run_migrations()
    logger.info("数据库就绪")

    # 初始化认证
    from app.common.auth import init_auth
    init_auth()
    logger.info("认证就绪")

    # 初始化插件
    init_plugins()
    logger.info("插件就绪")

    logger.info("AI Secretary 已启动 ✅")

    yield

    # === 关闭 ===
    logger.info("AI Secretary 关闭中...")
    # 先等待后台任务完成，再关闭数据库连接，避免后台任务使用已关闭的引擎报错
    await shutdown_background()
    await close_db()
    logger.info("AI Secretary 已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    config = get_config()
    app = FastAPI(
        title=config.app.title,
        description=config.app.description,
        version=config.app.version,
        lifespan=lifespan,
    )

    # CORS（origins=* 与 credentials=True 不兼容，浏览器会拒绝）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors.allow_origins,
        allow_credentials=config.cors.allow_credentials,
        allow_methods=config.cors.allow_methods,
        allow_headers=config.cors.allow_headers,
    )

    # request-id：每请求生成/透传 id，绑定 structlog contextvars 便于跨请求排障，
    # 回写响应头 X-Request-Id（补全 logging.py 已挂的 merge_contextvars 基建）
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            clear_contextvars()

    # 错误处理
    register_error_handlers(app)

    # 路由
    app.include_router(api_router)

    # 健康检查
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "ai-secretary"}

    return app


app = create_app()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    config = init_config()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
    )