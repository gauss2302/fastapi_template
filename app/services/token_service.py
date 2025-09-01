import hashlib
from datetime import datetime, timedelta
from uuid import UUID
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.redis import RedisService
from app.core.security import security_service


class TokenService:
    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service

    async def create_token_pair(self, user_id: UUID) -> Dict[str, Any]:
        tokens = security_service.create_token_pair(user_id)

        await self.store_refresh_token

    async def store_refresh_token(self, user_id: UUID, refresh_token: str, device_id: Optional[str] = None) -> None:
        token_hash = self._hash_token(refresh_token)

        if device_id:
            redis_key = f"refresh_token:user:{user_id}:device:{device_id}"
        else:
            redis_key = f"refresh_token:user:{user_id}:web"

        token_data = {
            "token_hash": token_hash,
            "user_id": str(user_id),
            "device_id": device_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
            "is_active": True
        }

        await self.redis_service.set(
            redis_key,
            token_data,
            expire=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        )

        await self.redis_service.set(
            f"token_hash:{token_hash}",
            redis_key,
            expire=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        )

    async def rotate_refresh_token(self, old_refresh_token: str, user_id: UUID, device_id: Optional[str] = None) -> \
            Dict[str, Any]:
        """Rotate refresh token: create new one and blacklist the old."""

        if not await self.is_refresh_token_valid(old_refresh_token, user_id):
            raise AuthenticationError("Invalid refresh token")

        await self.blacklist_token(old_refresh_token, reason="rotated")

        await self.revoke_refresh_token(user_id, device_id)

        new_tokens = security_service.create_token_pair(user_id)

        await self.store_refresh_token(user_id, new_tokens['refresh_token'], device_id)

        await self.update_token_usage(user_id, device_id)

        return new_tokens

    async def is_refresh_token_valid(self, refresh_token: str, user_id: UUID, device_id: Optional[str] = None) -> bool:
        """Check if refresh token is valid and not blacklisted."""

        if await self.is_token_blacklisted(refresh_token):
            return False

        payload = security_service.verify_token(refresh_token)
        if not payload or payload.sub != str(user_id):
            return False

        token_hash = self._hash_token(refresh_token)
        redis_key_lookup = await self.redis_service.get(f"token_hash:{token_hash}")

        if not redis_key_lookup:
            return False

        token_data = await self.redis_service.get(redis_key_lookup)
        if not token_data or not token_data.get("is_active"):
            return False

        return True

    async def blacklist_token(self, token: str, reason: str = 'manual_revoke', ttl: Optional[int] = None) -> None:
        ''''Add token to blacklist'''

        token_hash = self._hash_token(token)

        if not ttl:
            payload = security_service.verify_token(token)
            if payload and payload.exp:
                ttl = max(0, payload.exp - int(datetime.utcnow().timestamp()))
            else:
                ttl = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60

        blacklist_data = {
            "token_hash": token_hash,
            "blacklisted_at": datetime.utcnow().isoformat(),
            "reason": reason,
            "expires_at": (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()
        }

        await self.redis_service.set(
            f"blacklist:{token_hash}",
            blacklist_data,
            expire=ttl
        )

    async def is_token_blacklisted(self, token: str) -> bool:
        '''Check if token is blacklisted'''

        token_hash = self._hash_token(token)
        blacklist_data = await self.redis_service.get(f"blacklist:{token_hash}")
        return blacklist_data is not None

    async def revoke_refresh_token(
            self,
            user_id: UUID,
            device_id: Optional[str] = None
    ) -> bool:
        """Revoke refresh token from active storage."""

        if device_id:
            redis_key = f"refresh_token:user:{user_id}:device:{device_id}"
        else:
            redis_key = f"refresh_token:user:{user_id}:web"

        token_data = await self.redis_service.get(redis_key)
        if token_data and token_data.get("token_hash"):
            await self.redis_service.delete(f"token_hash:{token_data['token_hash']}")

        return await self.redis_service.delete(redis_key)

    async def revoke_all_user_tokens(self, user_id: UUID) -> int:
        '''Revoke all refresh tokens for a user'''

        if not self.redis_service.redis:
            return 0

        try:
            pattern = f"refresh_token:user:{user_id}:*"
            keys = await self.redis_service.redis.keys(pattern)

            revoked_count = 0
            for key in keys:
                token_data = await self.redis_service.get(key)
                if token_data and token_data.get("token_hash"):
                    await self.redis_service.delete(f"token_hash:{token_data['token_hash']}")

                if await self.redis_service.delete(key):
                    revoked_count += 1

            return revoked_count
        except Exception as e:
            print(f"Error revoking user tokens: {e}")
            return 0

    async def update_token_usage(self, user_id: UUID, device_id: Optional[str] = None):
        """Update last usage timestamp for token."""
        if device_id:
            redis_key = f"refresh_token:user:{user_id}:device:{device_id}"
        else:
            redis_key = f"refresh_token:user:{user_id}:web"

        token_data = await self.redis_service.get(redis_key)
        if token_data:
            token_data["last_used"] = datetime.utcnow().isoformat()

            if self.redis_service.redis:
                ttl = await self.redis_service.redis.ttl(redis_key)
                await self.redis_service.set(redis_key, token_data, expire=ttl)

    async def cleanup_expired_token(self) -> Dict[str, int]:
        """Cleanup expired tokens and blacklist entries."""
        if not self.redis_service.redis:
            return {"blacklist_cleaned": 0, "tokens_cleaned": 0}

        try:
            blacklist_cleaned = 0
            tokens_cleaned = 0

            hash_keys = await self.redis_service.redis.keys("token_hash:*")
            for hash_key in hash_keys:
                redis_key = await self.redis_service.get(hash_key)
                if not redis_key or not await self.redis_service.exists(redis_key):
                    await self.redis_service.delete(hash_key)
                    tokens_cleaned += 1

            return {
                "blacklist_cleaned": blacklist_cleaned,
                "tokens_cleaned": tokens_cleaned
            }

        except Exception:
            return {"blacklist_cleaned": 0, "tokens_cleaned": 0}

    def _hash_token(self, token: str) -> str:
        """Create a hash of token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()
