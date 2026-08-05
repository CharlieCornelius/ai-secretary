"""API 路由聚合"""

from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.experiences import router as experiences_router
from app.api.routes.plugins import router as plugins_router
from app.api.routes.profile import router as profile_router
from app.api.routes.sessions import router as sessions_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(profile_router)
api_router.include_router(experiences_router)
api_router.include_router(plugins_router)
