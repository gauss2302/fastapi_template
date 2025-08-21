import time
import hashlib
from enum import Enum
from typing import Optional, Callable, Dict, Any, Union
from functools import wraps
from dataclasses import dataclass, field

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.redis import RedisService


class RateLimitType(str, Enum):
    """Rate limit types for different endpoint categories."""
    AUTH = "auth"
    API = "api"
    STRICT = "strict"
    UPLOAD = "upload"
    PUBLIC = "public"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    calls: int
    period: int  # seconds
    burst: Optional[int] = None  # burst allowance
    key_func: Optional[Callable[[Request], str]] = field(default=None, repr=False)
    skip_successful: bool = False  # Don't count successful requests
    skip_if: Optional[Callable[[Request], bool]] = field(default=None, repr=False)

    def __post_init__(self):
        """Ensure functions are not serialized in schema generation."""
        if self.key_func is None:
            self.key_func = self._default_key_func
        if hasattr(self, '__dataclass_fields__'):
            # Hide callable fields from serialization
            self.__dataclass_fields__['key_func'].repr = False
            self.__dataclass_fields__['skip_if'].repr = False

    def _default_key_func(self, request: Request) -> str:
        """Default key function."""
        return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimitStorage:
    """Optimized rate limit storage with fallback."""

    def __init__(self, redis_service: Optional[RedisService] = None):
        self.redis_service = redis_service
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._memory_cleanup_time = time.time()

    async def get_count(self, key: str) -> Optional[int]:
        """Get current count for key."""
        if self.redis_service and self.redis_service.redis:
            try:
                count = await self.redis_service.get(key)
                return int(count) if count else None
            except Exception:
                pass

        # Fallback to memory cache
        self._cleanup_memory_cache()
        entry = self._memory_cache.get(key)
        if entry and entry["expires"] > time.time():
            return entry["count"]
        return None

    async def increment(self, key: str, expire: int) -> int:
        """Increment counter and set expiration."""
        if self.redis_service and self.redis_service.redis:
            try:
                count = await self.redis_service.incr(key)
                if count == 1:  # First increment, set expiration
                    await self.redis_service.expire(key, expire)
                return count
            except Exception:
                pass

        # Fallback to memory cache
        self._cleanup_memory_cache()
        current_time = time.time()
        entry = self._memory_cache.get(key)

        if not entry or entry["expires"] <= current_time:
            self._memory_cache[key] = {
                "count": 1,
                "expires": current_time + expire
            }
            return 1
        else:
            entry["count"] += 1
            return entry["count"]

    def _cleanup_memory_cache(self):
        """Clean expired entries from memory cache."""
        current_time = time.time()
        if current_time - self._memory_cleanup_time > 60:  # Cleanup every minute
            expired_keys = [
                key for key, entry in self._memory_cache.items()
                if entry["expires"] <= current_time
            ]
            for key in expired_keys:
                del self._memory_cache[key]
            self._memory_cleanup_time = current_time


class RateLimiter:
    """Advanced rate limiter with multiple algorithms."""

    # Predefined configurations - only store simple data, no functions
    SIMPLE_CONFIGS = {
        RateLimitType.AUTH: {"calls": 5, "period": 60, "burst": 2},
        RateLimitType.API: {"calls": 100, "period": 60, "burst": 20},
        RateLimitType.STRICT: {"calls": 1, "period": 10},
        RateLimitType.UPLOAD: {"calls": 3, "period": 300, "burst": 1},
        RateLimitType.PUBLIC: {"calls": 1000, "period": 3600, "burst": 100},
    }

    def __init__(self, storage: RateLimitStorage):
        self.storage = storage

    def _get_config(self, limit_type: Union[RateLimitType, RateLimitConfig]) -> RateLimitConfig:
        """Get configuration from type or return config directly."""
        if isinstance(limit_type, RateLimitType):
            config_data = self.SIMPLE_CONFIGS[limit_type]
            return RateLimitConfig(**config_data)
        return limit_type

    def _get_client_key(self, request: Request, config: RateLimitConfig) -> str:
        """Generate rate limit key for client."""
        if config.key_func:
            identifier = config.key_func(request)
        else:
            # Default: IP + User-Agent hash for better uniqueness
            ip = self._get_client_ip(request)
            user_agent = request.headers.get("user-agent", "")
            ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
            identifier = f"{ip}:{ua_hash}"

        endpoint = request.url.path
        method = request.method
        return f"rate_limit:{endpoint}:{method}:{identifier}"

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with proxy support."""
        # Check for forwarded headers (proxy/load balancer)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    async def check_rate_limit(
            self,
            request: Request,
            limit_type: Union[RateLimitType, RateLimitConfig]
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request should be rate limited.

        Returns:
            (is_allowed, headers_info)
        """
        config = self._get_config(limit_type)

        # Skip if condition met
        if config.skip_if and config.skip_if(request):
            return True, {}

        key = self._get_client_key(request, config)
        current_count = await self.storage.get_count(key)

        # Check limits
        limit = config.calls
        if config.burst and current_count is not None:
            # Allow burst for new periods
            if current_count <= config.burst:
                limit += config.burst

        if current_count is None or current_count < limit:
            # Increment counter
            new_count = await self.storage.increment(key, config.period)

            headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(max(0, limit - new_count)),
                "X-RateLimit-Reset": str(int(time.time()) + config.period),
            }

            return True, headers
        else:
            # Rate limited
            headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + config.period),
                "Retry-After": str(config.period),
            }

            return False, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for global application."""

    def __init__(self, app, redis_service: Optional[RedisService] = None):
        super().__init__(app)
        self.storage = RateLimitStorage(redis_service)
        self.rate_limiter = RateLimiter(self.storage)

        # Global rate limits by path patterns
        self.path_limits = {
            "/api/v1/auth": RateLimitType.AUTH,
            "/api/v1/users": RateLimitType.API,
            "/health": RateLimitType.PUBLIC,
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply rate limiting based on path patterns."""
        # Skip rate limiting for certain paths
        if self._should_skip(request):
            return await call_next(request)

        # Determine rate limit type
        limit_type = self._get_limit_type(request)
        if not limit_type:
            return await call_next(request)

        # Check rate limit
        is_allowed, headers = await self.rate_limiter.check_rate_limit(
            request, limit_type
        )

        if not is_allowed:
            response = Response(
                content='{"error": "Rate limit exceeded", "status_code": 429}',
                status_code=429,
                headers=headers,
                media_type="application/json"
            )
            return response

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        for header, value in headers.items():
            response.headers[header] = value

        return response

    def _should_skip(self, request: Request) -> bool:
        """Check if request should skip rate limiting."""
        skip_paths = ["/docs", "/redoc", "/openapi.json", "/favicon.ico"]
        return any(request.url.path.startswith(path) for path in skip_paths)

    def _get_limit_type(self, request: Request) -> Optional[RateLimitType]:
        """Determine rate limit type for request path."""
        path = request.url.path
        for pattern, limit_type in self.path_limits.items():
            if path.startswith(pattern):
                return limit_type
        return None


# Decorators for endpoint-specific rate limiting
def rate_limit(
        limit_type: Union[RateLimitType, RateLimitConfig],
        redis_service: Optional[RedisService] = None
):
    """
    Decorator for rate limiting specific endpoints.

    Usage:
        @rate_limit(RateLimitType.AUTH)
        async def login(...):
            ...

        @rate_limit(RateLimitConfig(calls=3, period=60))
        async def upload_file(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract Request from function parameters
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                # Try to find in kwargs
                for value in kwargs.values():
                    if isinstance(value, Request):
                        request = value
                        break

            if request:
                # Apply rate limiting
                storage = RateLimitStorage(redis_service)
                rate_limiter = RateLimiter(storage)

                is_allowed, headers = await rate_limiter.check_rate_limit(
                    request, limit_type
                )

                if not is_allowed:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded",
                        headers=headers
                    )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Convenience decorators
def auth_rate_limit(redis_service: Optional[RedisService] = None):
    """Rate limit for authentication endpoints."""
    def decorator(func: Callable) -> Callable:
        return rate_limit(RateLimitType.AUTH, redis_service)(func)
    return decorator


def api_rate_limit(redis_service: Optional[RedisService] = None):
    """Rate limit for general API endpoints."""
    def decorator(func: Callable) -> Callable:
        return rate_limit(RateLimitType.API, redis_service)(func)
    return decorator


def strict_rate_limit(redis_service: Optional[RedisService] = None):
    """Strict rate limit for sensitive endpoints."""
    def decorator(func: Callable) -> Callable:
        return rate_limit(RateLimitType.STRICT, redis_service)(func)
    return decorator


def upload_rate_limit(redis_service: Optional[RedisService] = None):
    """Rate limit for file upload endpoints."""
    def decorator(func: Callable) -> Callable:
        return rate_limit(RateLimitType.UPLOAD, redis_service)(func)
    return decorator