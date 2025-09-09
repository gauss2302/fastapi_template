from fastapi import APIRouter
from app.api.v1.endpoints import auth_web, auth_mobile, users, companies, recruiters, jobs

api_router = APIRouter()

# Authentication routes
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

# User management routes
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"]
)

# Company management routes
api_router.include_router(
    companies.router,
    prefix="/companies",
    tags=["companies"]
)

# Recruiter management routes
api_router.include_router(
    recruiters.router,
    prefix="/recruiters",
    tags=["recruiters"]
)

# Job posting routes
api_router.include_router(
    jobs.router,
    prefix="/jobs",
    tags=["jobs"]
)