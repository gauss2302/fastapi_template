import time
import hashlib
from enum import Enum
from typing import Optional, Callable, Dict, Any, Union
import inspect
from functools import wraps

from fastapi import Depends, Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from limits import parse
from limits.storage import RedisStorage, MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.core.config.config import settings
from app.core.redis.redis import RedisService


class RateLimitType(str, Enum):
    """Rate limit types for different endpoint categories."""
    AUTH = "auth"
    API = "api"
    STRICT = "strict"
    UPLOAD = "upload"
    PUBLIC = "public"


def _get_client_ip(request: Request) -> str:
    """Extract client IP with proxy support."""

    forwarded_for = request.headers.get("x-real-ip")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip

    return request.client.host if request.client else "unknown"


class RateLimiter:
    LIMITS = {
        RateLimitType.AUTH: "5/minute;10/hour",  # 5 per minute, 10 per hour
        RateLimitType.API: "100/minute;1000/hour",
        RateLimitType.STRICT: "1/10seconds;5/minute",
        RateLimitType.UPLOAD: "3/5minutes;10/hour",
        RateLimitType.PUBLIC: "1000/hour",
    }

    def __init__(self, redis_service: Optional[RedisService] = None):
        if redis_service:
            uri: Optional[str] = getattr(redis_service, 'redis_url', None)

            if redis_service.redis:
                connection_kwargs = redis_service.redis.connection_pool.connection_kwargs
                host = connection_kwargs.get('host', 'localhost')
                port = connection_kwargs.get('port', 6379)
                db = connection_kwargs.get('db', 0)
                username = connection_kwargs.get('username')
                password = connection_kwargs.get('password')
                ssl = connection_kwargs.get('ssl', False)

                scheme = 'rediss' if ssl else 'redis'
                credentials = ''
                if username or password:
                    user = username or ''
                    pwd = password or ''
                    credentials = f"{user}:{pwd}@"

                uri = f"{scheme}://{credentials}{host}:{port}/{db}"

            if uri:
                self.storage = RedisStorage(uri=uri)
            else:
                self.storage = MemoryStorage()
        else:
            self.storage = MemoryStorage()

        self.limiter = MovingWindowRateLimiter(self.storage)

    def _get_client_key(self, request: Request, identifier_func: Optional[Callable] = None) -> str:
        """Gen rate limit key for client"""

        if identifier_func:
            identifier = identifier_func(request)
        else:
            ip = _get_client_ip(request)
            user_agent = request.headers.get("user-agent", "")
            ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
            identifier = f"{ip}:{ua_hash}"

        endpoint = request.url.path
        method = request.method
        return f"{endpoint}:{method}:{identifier}"

    async def check_rate_limit(
            self,
            request: Request,
            limit_type: Union[RateLimitType, str],
            identifier_func: Optional[Callable] = None,
            skip_condition: Optional[Callable] = None
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request should be rate limited.

        Returns:
            (is_allowed, headers_info)
        """
        if skip_condition and skip_condition(request):
            return True, {}

        if isinstance(limit_type, RateLimitType):
            limit_str = self.LIMITS.get(limit_type, "100/minute")
        else:
            limit_str = limit_type

        rate_limits = [parse(limit) for limit in limit_str.split(";")]

        key = self._get_client_key(request, identifier_func)

        for rate_limit in rate_limits:
            if not self.limiter.hit(rate_limit, key):
                window_stats = self.limiter.get_window_stats(rate_limit, key)

                headers = {
                    "X-RateLimit-Limit": str(rate_limit.amount),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + window_stats.reset_time)),
                    "Retry-After": str(int(window_stats.reset_time)),
                }

                return False, headers

        main_limit = rate_limits[0]
        window_stats = self.limiter.get_window_stats(main_limit, key)

        headers = {
            "X-RateLimit-Limit": str(main_limit.amount),
            "X-RateLimit-Remaining": str(max(0, int(window_stats.remaining))),
            "X-RateLimit-Reset": str(int(time.time() + window_stats.reset_time)),
        }

        return True, headers

    def create_custom_limit(self, limit_string: str) -> str:
        """Create a custom limit string."""
        return limit_string


def _get_or_create_rate_limiter(request: Request) -> RateLimiter:
    """Fetch shared rate limiter instance from app state or create one on demand."""

    rate_limiter = getattr(request.app.state, 'rate_limiter', None)
    if rate_limiter is None:
        redis_service = getattr(request.app.state, 'redis_service', None)
        rate_limiter = RateLimiter(redis_service)
        request.app.state.rate_limiter = rate_limiter
        if redis_service is not None:
            request.app.state.redis_service = redis_service

    return rate_limiter


async def _enforce_rate_limit(
        request: Request,
        limit_type: Union[RateLimitType, str],
        identifier_func: Optional[Callable],
        skip_condition: Optional[Callable]
) -> None:
    rate_limiter = _get_or_create_rate_limiter(request)

    is_allowed, headers = await rate_limiter.check_rate_limit(
        request,
        limit_type,
        identifier_func,
        skip_condition,
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=headers,
        )


def _build_rate_limit_dependency(
        limit_type: Union[RateLimitType, str] = RateLimitType.API,
        identifier_func: Optional[Callable] = None,
        skip_condition: Optional[Callable] = None,
):
    async def dependency(request: Request) -> None:
        await _enforce_rate_limit(request, limit_type, identifier_func, skip_condition)

    return dependency


def rate_limit_dependency(
        limit_type: Union[RateLimitType, str] = RateLimitType.API,
        identifier_func: Optional[Callable] = None,
        skip_condition: Optional[Callable] = None,
):
    """Create a FastAPI Depends object for the specified rate limit."""

    return Depends(_build_rate_limit_dependency(limit_type, identifier_func, skip_condition))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for global application."""

    def __init__(self, app, redis_service: Optional[RedisService] = None):
        super().__init__(app)
        self.redis_service = redis_service
        self.rate_limiter = RateLimiter(redis_service)
        self._attach_to_app_state(app)

        self.path_limits = {
            f"{settings.API_V1_STR}/auth": RateLimitType.AUTH,
            f"{settings.API_V1_STR}/users": RateLimitType.API,
            settings.API_V1_STR: RateLimitType.API,
            "/health": RateLimitType.PUBLIC
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        """Applicaiton rate limiting based on the path pattern"""

        self._attach_to_app_state(request.app)

        if self._should_skip(request):
            return await call_next(request)

        limit_type = self._get_limit_type(request)
        if not limit_type:
            return await call_next(request)

        is_allowed, headers = await self.rate_limiter.check_rate_limit(request, limit_type)

        if not is_allowed:
            response = Response(
                content='{"error": "Rate limit exceeded", "status_code": 429}',
                status_code=429,
                headers=headers,
                media_type="application/json"
            )
            return response

        response = await call_next(request)

        for header, value in headers.items():
            response.headers[header] = value

        return response

    def _should_skip(self, request: Request) -> bool:
        """Check if request should skip rate limiting."""
        skip_paths = {
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            f"{settings.API_V1_STR}/docs",
            f"{settings.API_V1_STR}/redoc",
            f"{settings.API_V1_STR}/openapi.json",
            "/docs/oauth2-redirect",
        }
        return any(request.url.path.startswith(path) for path in skip_paths)

    def _get_limit_type(self, request: Request) -> Optional[RateLimitType]:
        """Determine rate limit type for request path."""
        path = request.url.path
        for pattern, limit_type in self.path_limits.items():
            if path.startswith(pattern):
                return limit_type
        return None

    def _attach_to_app_state(self, target_app: Any) -> None:
        """Ensure shared limiter and redis service are available via app state when supported."""

        state = getattr(target_app, 'state', None)
        if state is None:
            return

        if getattr(state, 'rate_limiter', None) is None:
            state.rate_limiter = self.rate_limiter

        if self.redis_service is not None and getattr(state, 'redis_service', None) is None:
            state.redis_service = self.redis_service


def rate_limit(
        limit_type: Union[RateLimitType, str] = RateLimitType.API,
        identifier_func: Optional[Callable] = None,
        skip_condition: Optional[Callable] = None
):
    """
    Decorator for rate limiting specific endpoints.

    Args:
        limit_type: Rate limit type or custom limit string (e.g., "10/minute")
        identifier_func: Function to generate client identifier
        skip_condition: Function to check if rate limiting should be skipped
    """

    def decorator(func: Callable) -> Callable:
        dependency_callable = _build_rate_limit_dependency(
            limit_type=limit_type,
            identifier_func=identifier_func,
            skip_condition=skip_condition,
        )

        original_signature = inspect.signature(func)
        dependency_param = inspect.Parameter(
            name="_rate_limit_guard",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=Depends(dependency_callable),
            annotation=inspect._empty,
        )
        new_parameters = list(original_signature.parameters.values()) + [dependency_param]
        new_signature = original_signature.replace(parameters=new_parameters)

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            return await func(*args, **kwargs)

        wrapper.__signature__ = new_signature
        return wrapper
    return decorator


def auth_rate_limit(func: Callable = None, **kwargs):
    """Rate limit for authentication endpoints."""
    if func is None:
        return lambda f: rate_limit(RateLimitType.AUTH, **kwargs)(f)
    else:
        return rate_limit(RateLimitType.AUTH, **kwargs)(func)


def auth_rate_limit_dependency(**kwargs):
    """Dependency shortcut for authentication rate limits."""
    return rate_limit_dependency(RateLimitType.AUTH, **kwargs)


def api_rate_limit(func: Callable = None, **kwargs):
    """Rate limit for general API endpoints."""
    if func is None:
        return lambda f: rate_limit(RateLimitType.API, **kwargs)(f)
    else:
        return rate_limit(RateLimitType.API, **kwargs)(func)


def api_rate_limit_dependency(**kwargs):
    """Dependency shortcut for general API rate limits."""
    return rate_limit_dependency(RateLimitType.API, **kwargs)


def strict_rate_limit(func: Callable = None, **kwargs):
    """Strict rate limit for sensitive endpoints."""
    if func is None:
        return lambda f: rate_limit(RateLimitType.STRICT, **kwargs)(f)
    else:
        return rate_limit(RateLimitType.STRICT, **kwargs)(func)


def strict_rate_limit_dependency(**kwargs):
    """Dependency shortcut for strict rate limits."""
    return rate_limit_dependency(RateLimitType.STRICT, **kwargs)


def upload_rate_limit(func: Callable = None, **kwargs):
    """Rate limit for file upload endpoints."""
    if func is None:
        return lambda f: rate_limit(RateLimitType.UPLOAD, **kwargs)(f)
    else:
        return rate_limit(RateLimitType.UPLOAD, **kwargs)(func)


def upload_rate_limit_dependency(**kwargs):
    """Dependency shortcut for upload rate limits."""
    return rate_limit_dependency(RateLimitType.UPLOAD, **kwargs)


# Helper functions for identifier generation
def user_based_identifier(request: Request) -> str:
    """Generate identifier based on authenticated user."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return f"user:{hashlib.md5(token.encode()).hexdigest()[:16]}"

    # Fallback to IP
    return f"ip:{request.client.host if request.client else 'unknown'}"


def ip_based_identifier(request: Request) -> str:
    """Generate identifier based on IP address."""
    # Check for real IP behind proxy
    real_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip") or
            (request.client.host if request.client else "unknown")
    )
    return f"ip:{real_ip}"


def device_based_identifier(request: Request) -> str:
    """Generate identifier based on device ID (mobile apps)."""
    device_id = request.headers.get("X-Device-ID")
    if device_id:
        return f"device:{device_id}"

    # Fallback to IP + User-Agent
    ip = request.client.host if request.client else "unknown"
    ua_hash = hashlib.md5(request.headers.get("user-agent", "").encode()).hexdigest()[:12]
    return f"fallback:{ip}:{ua_hash}"


# Skip conditions
def admin_bypass_condition(request: Request) -> bool:
    """Skip rate limiting for admin users."""
    return request.headers.get("x-admin-bypass") == "secret_key"


def premium_user_condition(request: Request) -> bool:
    """Skip rate limiting for premium users."""
    return request.headers.get("x-premium-user") == "true"


__all__ = [
    'RateLimitType',
    'RateLimiter',
    'RateLimitMiddleware',
    'rate_limit',
    'rate_limit_dependency',
    'auth_rate_limit',
    'auth_rate_limit_dependency',
    'api_rate_limit',
    'api_rate_limit_dependency',
    'strict_rate_limit',
    'strict_rate_limit_dependency',
    'upload_rate_limit',
    'upload_rate_limit_dependency',
    'user_based_identifier',
    'ip_based_identifier',
    'device_based_identifier',
    'admin_bypass_condition',
    'premium_user_condition'
]
