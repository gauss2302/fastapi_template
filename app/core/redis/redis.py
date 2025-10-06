import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config.config import settings


class RedisService:
    def __init__(self) -> None:
        self.redis: Optional[aioredis.Redis] = None
        self.redis_url: str = str(settings.REDIS_URL)

    async def init_redis(self) -> None:
        """Initialize Redis connection."""
        try:
            self.redis = aioredis.from_url(
                str(settings.REDIS_URL),
                encoding="utf-8",
                decode_responses=True,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            await self.redis.ping()
        except Exception as e:
            print(f"Warning: Could not connect to Redis: {e}")
            print("Redis features will be disabled")
            self.redis = None

    async def close_redis(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis."""
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            return None
        except Exception:
            return None

    async def set(
            self,
            key: str,
            value: Any,
            expire: Optional[int] = None
    ) -> bool:
        """Set value in Redis with optional expiration."""
        if not self.redis:
            return False

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)

            return await self.redis.set(key, value, ex=expire)
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.delete(key))
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.exists(key))
        except Exception:
            return False

    async def incr(self, key: str) -> int:
        """Increment value in Redis."""
        if not self.redis:
            return 0

        try:
            return await self.redis.incr(key)
        except Exception:
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for key."""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.expire(key, seconds))
        except Exception:
            return False


# Global Redis service instance
redis_service = RedisService()


async def get_redis() -> RedisService:
    """Dependency for getting Redis service."""
    return redis_service
