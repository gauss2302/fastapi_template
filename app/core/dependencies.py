from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis, RedisService
from app.core.security import security_service
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from app.services.auth_service import GoogleOAuthService
from app.schemas.user import User
from app.core.exceptions import AuthenticationError, AuthorizationError

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


async def get_user_service(
        user_repo: UserRepository = Depends(get_user_repository),
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> UserService:
    """Get user service dependency."""
    return UserService(user_repo, google_oauth_service)


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


async def rate_limit_auth(
        request: Request,
        redis_service: RedisService = Depends(get_redis),
):
    """Rate limiter for auth endpoints (5 calls per minute)."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:auth:{client_ip}"

    current = await redis_service.get(key)
    if current is None:
        await redis_service.set(key, 1, expire=60)
        return

    if int(current) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )

    await redis_service.incr(key)


async def rate_limit_api(
        request: Request,
        redis_service: RedisService = Depends(get_redis),
):
    """Rate limiter for API endpoints (100 calls per minute)."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:api:{client_ip}"

    current = await redis_service.get(key)
    if current is None:
        await redis_service.set(key, 1, expire=60)
        return

    if int(current) >= 100:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    await redis_service.incr(key)

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


async def get_current_superuser(
        current_user: User = Depends(get_current_user),
) -> User:
    """Get current superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user


class RateLimiter:
    """Rate limiter dependency."""

    def __init__(self, calls: int, period: int):
        self.calls = calls
        self.period = period

    async def __call__(
            self,
            request,
            redis_service: RedisService = Depends(get_redis),
    ):
        # Get client identifier (you might want to use user ID for authenticated requests)
        client_ip = request.client.host
        key = f"rate_limit:{client_ip}"

        # Get current count
        current = await redis_service.get(key)
        if current is None:
            await redis_service.set(key, 1, expire=self.period)
            return

        if int(current) >= self.calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )

        await redis_service.incr(key)


# Rate limiter instances
rate_limit_auth = RateLimiter(calls=5, period=60)  # 5 calls per minute
rate_limit_api = RateLimiter(calls=100, period=60)  # 100 calls per minute