from fastapi import APIRouter

from app.api.v1.endpoints import auth_web, auth_mobile, users

api_router = APIRouter()

api_router.include_router(
    auth_web.router,
    prefix="/auth/web",
    tags=["web-authentication"]
)

api_router.include_router(
    auth_mobile.router,
    prefix="/auth/mobile",
    tags=["mobile-authentication"]
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"]
)