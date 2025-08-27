from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import AppLogger
from app.core.database import get_db
from app.core.redis import get_redis, RedisService
from app.core.security import security_service
from app.repositories.company_repository import CompanyRepository
from app.repositories.recruiter_repository import RecruiterRepository
from app.repositories.user_repository import UserRepository
from app.services.company_service import CompanyService
from app.services.user_service import UserService
from app.services.auth_service import GoogleOAuthService
from app.services.github_auth_service import GitHubOAuthService
from app.schemas.user import User
from app.core.exceptions import AuthenticationError

# Security scheme
security = HTTPBearer()


# Repo Deps
async def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """Get user repository dependency."""
    return UserRepository(db)


async def get_company_repository(db: AsyncSession = Depends(get_db)) -> CompanyRepository:
    """Get company repository dependency."""
    return CompanyRepository(db)


async def get_recruiter_repository(db: AsyncSession = Depends(get_db)) -> RecruiterRepository:
    """Get recruiter repository dependency."""
    return RecruiterRepository(db)


async def get_google_oauth_service(
        redis_service: RedisService = Depends(get_redis),
) -> GoogleOAuthService:
    """Get Google OAuth service dependency."""
    return GoogleOAuthService(redis_service)


async def get_github_oauth_service(
        redis_service: RedisService = Depends(get_redis),
) -> GitHubOAuthService:
    """Get GitHub OAuth service dependency."""
    return GitHubOAuthService(redis_service)


async def get_user_service(
        user_repo: UserRepository = Depends(get_user_repository),
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> UserService:
    """Get user service dependency."""
    return UserService(user_repo, google_oauth_service, github_oauth_service)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Get current authenticated user."""
    token = credentials.credentials

    # Verify token
    payload = security_service.verify_token(token)
    if not payload or not payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
    try:
        user_id = UUID(payload.sub)
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """Get current superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user


def get_current_active_user(
        current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def get_authenticated_user_id(
        current_user: User = Depends(get_current_user)
) -> UUID:
    """Get current user ID for user-specific rate limiting."""
    return current_user.id


async def get_company_service(
        company_repo: CompanyRepository = Depends(get_company_repository),
        recruiter_repo: RecruiterRepository = Depends(get_recruiter_repository),
        user_repo: UserRepository = Depends(get_user_repository),
) -> CompanyService:
    """Get company service dependency."""
    return CompanyService(company_repo, recruiter_repo, user_repo)


async def update_recruiter_activity(
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> None:
    """Update recruiter activity for authenticated requests"""
    try:
        # Только обновляем активность, если пользователь является рекрутером
        await company_service.update_recruiter_activity(current_user.id)
    except Exception:
        # Don't fail the request if activity update fails
        pass


async def get_logger(request: Request = None) -> AppLogger:
    context = {}

    if request and hasattr(request.state, 'request_id'):
        context['request_id'] = request.state.request_id

    return AppLogger('api', **context)
