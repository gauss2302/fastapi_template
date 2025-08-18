from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from app.core.redis import RedisService
from app.core.security import security_service
from app.core.exceptions import AuthenticationError
from app.schemas.user import User


class MobileTokenService:
    """Service for managing mobile authentication tokens without cookies."""

    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service

    async def create_mobile_session(
            self,
            user_id: UUID,
            device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a mobile session with tokens."""
        tokens = security_service.create_token_pair(user_id)

        # Store refresh token with device association
        session_key = f"mobile_session:{user_id}"
        if device_id:
            session_key += f":{device_id}"

        session_data = {
            "user_id": str(user_id),
            "device_id": device_id,
            "refresh_token": tokens["refresh_token"],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat()
        }

        await self.redis_service.set(
            session_key,
            session_data,
            expire=tokens["refresh_expires_in"]
        )

        return tokens

    async def refresh_mobile_token(
            self,
            refresh_token: str,
            device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Refresh mobile tokens and update session."""
        # Verify refresh token
        payload = security_service.verify_token(refresh_token)
        if not payload or not payload.sub:
            raise AuthenticationError("Invalid refresh token")

        user_id = UUID(payload.sub)

        # Find session by refresh token
        session_key = await self._find_session_by_token(user_id, refresh_token, device_id)
        if not session_key:
            raise AuthenticationError("Session not found or expired")

        # Generate new tokens
        new_tokens = security_service.create_token_pair(user_id)

        # Update session with new refresh token
        session_data = await self.redis_service.get(session_key)
        if session_data:
            session_data["refresh_token"] = new_tokens["refresh_token"]
            session_data["last_used"] = datetime.utcnow().isoformat()

            await self.redis_service.set(
                session_key,
                session_data,
                expire=new_tokens["refresh_expires_in"]
            )

        return new_tokens

    async def revoke_mobile_session(
            self,
            user_id: UUID,
            refresh_token: Optional[str] = None,
            device_id: Optional[str] = None
    ) -> bool:
        """Revoke mobile session."""
        if device_id:
            # Revoke specific device session
            session_key = f"mobile_session:{user_id}:{device_id}"
            return await self.redis_service.delete(session_key)
        elif refresh_token:
            # Find and revoke session by refresh token
            session_key = await self._find_session_by_token(user_id, refresh_token)
            if session_key:
                return await self.redis_service.delete(session_key)
        else:
            # Revoke all sessions for user
            pattern = f"mobile_session:{user_id}*"
            if self.redis_service.redis:
                try:
                    keys = await self.redis_service.redis.keys(pattern)
                    if keys:
                        await self.redis_service.redis.delete(*keys)
                    return True
                except Exception:
                    pass

        return False

    async def get_active_sessions(self, user_id: UUID) -> list[Dict[str, Any]]:
        """Get all active mobile sessions for a user."""
        if not self.redis_service.redis:
            return []

        try:
            pattern = f"mobile_session:{user_id}*"
            keys = await self.redis_service.redis.keys(pattern)
            sessions = []

            for key in keys:
                session_data = await self.redis_service.get(key)
                if session_data:
                    sessions.append({
                        "device_id": session_data.get("device_id"),
                        "created_at": session_data.get("created_at"),
                        "last_used": session_data.get("last_used"),
                        "session_key": key
                    })

            return sessions
        except Exception:
            return []

    async def _find_session_by_token(
            self,
            user_id: UUID,
            refresh_token: str,
            device_id: Optional[str] = None
    ) -> Optional[str]:
        """Find session key by refresh token."""
        if not self.redis_service.redis:
            return None

        try:
            if device_id:
                # Check specific device session
                session_key = f"mobile_session:{user_id}:{device_id}"
                session_data = await self.redis_service.get(session_key)
                if session_data and session_data.get("refresh_token") == refresh_token:
                    return session_key
            else:
                # Search all user sessions
                pattern = f"mobile_session:{user_id}*"
                keys = await self.redis_service.redis.keys(pattern)

                for key in keys:
                    session_data = await self.redis_service.get(key)
                    if session_data and session_data.get("refresh_token") == refresh_token:
                        return key
        except Exception:
            pass

        return None

    async def cleanup_expired_sessions(self) -> int:
        """Cleanup expired mobile sessions (maintenance task)."""
        if not self.redis_service.redis:
            return 0

        try:
            pattern = "mobile_session:*"
            keys = await self.redis_service.redis.keys(pattern)
            cleaned = 0

            for key in keys:
                # Redis will automatically remove expired keys,
                # but we can also check and clean up invalid sessions
                session_data = await self.redis_service.get(key)
                if not session_data:
                    cleaned += 1
                    continue

                # Verify refresh token is still valid
                refresh_token = session_data.get("refresh_token")
                if refresh_token:
                    payload = security_service.verify_token(refresh_token)
                    if not payload:
                        await self.redis_service.delete(key)
                        cleaned += 1

            return cleaned
        except Exception:
            return 0