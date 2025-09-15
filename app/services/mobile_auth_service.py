# app/services/mobile_auth_service.py
# Mobile-specific authentication service for future enhancements

from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from app.core.redis.redis import RedisService
from app.core.security.security import security_service
from app.schemas.user import DeviceInfo


class MobileAuthService:
    """Service for mobile-specific authentication features."""

    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service

    async def create_mobile_session(
            self,
            user_id: UUID,
            device_info: Optional[DeviceInfo] = None
    ) -> Dict[str, Any]:
        """Create a mobile session with enhanced device tracking."""
        tokens = security_service.create_token_pair(user_id)

        # Create session key
        device_id = device_info.device_id if device_info else "unknown"
        session_key = f"mobile_session:{user_id}:{device_id}"

        session_data = {
            "user_id": str(user_id),
            "device_id": device_id,
            "device_info": device_info.model_dump() if device_info else {},
            "refresh_token": tokens["refresh_token"],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
            "is_active": True
        }

        # Store session with expiration
        await self.redis_service.set(
            session_key,
            session_data,
            expire=tokens["refresh_expires_in"]
        )

        return tokens

    async def get_device_sessions(self, user_id: UUID) -> list[Dict[str, Any]]:
        """Get all active device sessions for a user."""
        if not self.redis_service.redis:
            return []

        try:
            pattern = f"mobile_session:{user_id}:*"
            keys = await self.redis_service.redis.keys(pattern)
            sessions = []

            for key in keys:
                session_data = await self.redis_service.get(key)
                if session_data and session_data.get("is_active"):
                    sessions.append({
                        "session_key": key,
                        "device_id": session_data.get("device_id"),
                        "device_info": session_data.get("device_info", {}),
                        "created_at": session_data.get("created_at"),
                        "last_used": session_data.get("last_used")
                    })

            return sessions
        except Exception:
            return []

    async def revoke_device_session(
            self,
            user_id: UUID,
            device_id: str
    ) -> bool:
        """Revoke a specific device session."""
        session_key = f"mobile_session:{user_id}:{device_id}"
        return await self.redis_service.delete(session_key)

    async def revoke_all_sessions(self, user_id: UUID) -> int:
        """Revoke all mobile sessions for a user."""
        if not self.redis_service.redis:
            return 0

        try:
            pattern = f"mobile_session:{user_id}:*"
            keys = await self.redis_service.redis.keys(pattern)
            if keys:
                deleted = await self.redis_service.redis.delete(*keys)
                return deleted
            return 0
        except Exception:
            return 0

    async def update_session_activity(
            self,
            user_id: UUID,
            device_id: str
    ) -> bool:
        """Update last activity timestamp for a session."""
        session_key = f"mobile_session:{user_id}:{device_id}"
        session_data = await self.redis_service.get(session_key)

        if session_data:
            session_data["last_used"] = datetime.utcnow().isoformat()
            # Get remaining TTL to preserve expiration
            if self.redis_service.redis:
                ttl = await self.redis_service.redis.ttl(session_key)
                await self.redis_service.set(session_key, session_data, expire=ttl)
            return True
        return False