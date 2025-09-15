from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from app.core.redis.redis import RedisService


class WebAuthService:
    """Service for web-specific authentication features."""

    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service

    async def manage_web_session(
            self,
            user_id: UUID,
            session_id: Optional[str] = None,
            user_agent: Optional[str] = None,
            ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Manage web session with browser fingerprinting."""

        # Create unique session identifier
        if not session_id:
            session_id = f"web_session_{user_id}_{datetime.utcnow().timestamp()}"

        session_key = f"web_session:{user_id}:{session_id}"

        session_data = {
            "user_id": str(user_id),
            "session_id": session_id,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "created_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
            "is_active": True
        }

        # Store session for 24 hours (typical web session)
        await self.redis_service.set(
            session_key,
            session_data,
            expire=86400  # 24 hours
        )

        return session_data

    async def get_web_sessions(self, user_id: UUID) -> list[Dict[str, Any]]:
        """Get all active web sessions for a user."""
        if not self.redis_service.redis:
            return []

        try:
            pattern = f"web_session:{user_id}:*"
            keys = await self.redis_service.redis.keys(pattern)
            sessions = []

            for key in keys:
                session_data = await self.redis_service.get(key)
                if session_data and session_data.get("is_active"):
                    sessions.append(session_data)

            return sessions
        except Exception:
            return []

    async def revoke_web_session(
            self,
            user_id: UUID,
            session_id: str
    ) -> bool:
        """Revoke a specific web session."""
        session_key = f"web_session:{user_id}:{session_id}"
        return await self.redis_service.delete(session_key)

    async def validate_session_security(
            self,
            user_id: UUID,
            session_id: str,
            current_ip: str,
            current_user_agent: str
    ) -> bool:
        """Validate session security by checking IP and user agent."""
        session_key = f"web_session:{user_id}:{session_id}"
        session_data = await self.redis_service.get(session_key)

        if not session_data:
            return False

        # Check for suspicious activity (IP or user agent change)
        stored_ip = session_data.get("ip_address")
        stored_ua = session_data.get("user_agent")

        if stored_ip and stored_ip != current_ip:
            # Log security event
            await self._log_security_event(
                user_id,
                "ip_change",
                {"old_ip": stored_ip, "new_ip": current_ip}
            )
            # Could invalidate session or require re-authentication

        if stored_ua and stored_ua != current_user_agent:
            await self._log_security_event(
                user_id,
                "user_agent_change",
                {"old_ua": stored_ua, "new_ua": current_user_agent}
            )

        return True

    async def _log_security_event(
            self,
            user_id: UUID,
            event_type: str,
            details: Dict[str, Any]
    ) -> None:
        """Log security events for monitoring."""
        security_log = {
            "user_id": str(user_id),
            "event_type": event_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store security log
        log_key = f"security_log:{user_id}:{datetime.utcnow().date()}"
        logs = await self.redis_service.get(log_key) or []
        logs.append(security_log)

        # Keep logs for 30 days
        await self.redis_service.set(log_key, logs, expire=2592000)