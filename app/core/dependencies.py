from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis, RedisService
from app.core.security import security_service
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from app.services.auth_service import GoogleOAuthService
from app.services.github_auth_service import GitHubOAuthService  # Add this import
from app.schemas.user import User
from app.core.exceptions import AuthenticationError

# Security scheme
security = HTTPBearer()


async def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """Get user repository dependency."""
    return UserRepository(db)


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
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),  # Add this
) -> UserService:
    """Get user service dependency."""
    return UserService(user_repo, google_oauth_service, github_oauth_service)  # Update this


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


# Optional: If you need user-specific rate limiting in dependencies
async def get_authenticated_user_id(
    current_user: User = Depends(get_current_user)
) -> UUID:
    """Get current user ID for user-specific rate limiting."""
    return current_user.id