from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timedelta
import secrets
import hashlib

from app.core.redis import RedisService
from app.core.security import security_service
from app.core.exceptions import AuthenticationError
from app.schemas.user import User, DeviceInfo


class MobileTokenService:
    """Service for managing mobile authentication tokens and sessions without cookies."""

    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service

    async def create_mobile_session(
            self,
            user_id: UUID,
            device_id: Optional[str] = None,
            device_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a mobile session with device tracking."""
        tokens = security_service.create_token_pair(user_id)

        # Generate device ID if not provided
        if not device_id:
            device_id = f"device_{secrets.token_urlsafe(16)}"

        # Store refresh token with device association
        session_key = f"mobile_session:{user_id}:{device_id}"

        session_data = {
            "user_id": str(user_id),
            "device_id": device_id,
            "device_info": device_info or {},
            "refresh_token": tokens["refresh_token"],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": datetime.utcnow().isoformat(),
            "is_active": True,
            "login_count": 1
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
            session_data["login_count"] = session_data.get("login_count", 0) + 1

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
            return await self.revoke_all_mobile_sessions(user_id) > 0

        return False

    async def revoke_all_mobile_sessions(self, user_id: UUID) -> int:
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

    async def get_active_sessions(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Get all active mobile sessions for a user."""
        if not self.redis_service.redis:
            return []

        try:
            pattern = f"mobile_session:{user_id}:*"
            keys = await self.redis_service.redis.keys(pattern)
            sessions = []

            for key in keys:
                session_data = await self.redis_service.get(key)
                if session_data and session_data.get("is_active"):
                    # Clean session data for response
                    clean_session = {
                        "device_id": session_data.get("device_id"),
                        "device_info": session_data.get("device_info", {}),
                        "created_at": session_data.get("created_at"),
                        "last_used": session_data.get("last_used"),
                        "login_count": session_data.get("login_count", 0),
                        "session_key": key.split(":")[-1]  # Just the device ID part
                    }
                    sessions.append(clean_session)

            # Sort by last used (most recent first)
            sessions.sort(key=lambda x: x.get("last_used", ""), reverse=True)
            return sessions
        except Exception as e:
            print(f"Error getting mobile sessions: {e}")
            return []

    async def update_device_info(
            self,
            user_id: UUID,
            device_id: str,
            device_info: Dict[str, Any]
    ) -> bool:
        """Update device information for a session."""
        session_key = f"mobile_session:{user_id}:{device_id}"
        session_data = await self.redis_service.get(session_key)

        if not session_data:
            return False

        # Update device info and last used
        session_data["device_info"].update(device_info)
        session_data["last_used"] = datetime.utcnow().isoformat()

        # Preserve TTL when updating
        if self.redis_service.redis:
            ttl = await self.redis_service.redis.ttl(session_key)
            await self.redis_service.set(session_key, session_data, expire=ttl)
            return True

        return False

    async def validate_device_session(
            self,
            user_id: UUID,
            device_id: str,
            device_fingerprint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate device session and check for security issues."""
        session_key = f"mobile_session:{user_id}:{device_id}"
        session_data = await self.redis_service.get(session_key)

        if not session_data:
            raise AuthenticationError("Device session not found")

        security_issues = []

        # Check device fingerprint if available
        if device_fingerprint:
            stored_fingerprint = session_data.get("device_info", {}).get("fingerprint")
            if stored_fingerprint and stored_fingerprint != device_fingerprint:
                security_issues.append("device_fingerprint_changed")

        # Check for unusual activity patterns
        last_used = session_data.get("last_used")
        if last_used:
            last_activity = datetime.fromisoformat(last_used)
            time_since_activity = datetime.utcnow() - last_activity

            # Flag if device was inactive for more than 30 days but suddenly active
            if time_since_activity > timedelta(days=30):
                security_issues.append("long_inactivity_period")

        return {
            "is_valid": True,
            "security_issues": security_issues,
            "session_data": session_data,
            "requires_reverification": len(security_issues) > 0
        }

    async def get_device_statistics(self, user_id: UUID) -> Dict[str, Any]:
        """Get statistics about user's mobile devices and sessions."""
        sessions = await self.get_active_sessions(user_id)

        if not sessions:
            return {
                "total_devices": 0,
                "active_sessions": 0,
                "platforms": {},
                "oldest_session": None,
                "newest_session": None
            }

        # Analyze platforms
        platforms = {}
        for session in sessions:
            platform = session.get("device_info", {}).get("platform", "unknown")
            platforms[platform] = platforms.get(platform, 0) + 1

        # Find oldest and newest sessions
        oldest_session = min(sessions, key=lambda x: x.get("created_at", ""))
        newest_session = max(sessions, key=lambda x: x.get("created_at", ""))

        return {
            "total_devices": len(sessions),
            "active_sessions": len(sessions),
            "platforms": platforms,
            "oldest_session": {
                "device_id": oldest_session.get("device_id"),
                "created_at": oldest_session.get("created_at"),
                "platform": oldest_session.get("device_info", {}).get("platform")
            },
            "newest_session": {
                "device_id": newest_session.get("device_id"),
                "created_at": newest_session.get("created_at"),
                "platform": newest_session.get("device_info", {}).get("platform")
            }
        }

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
                pattern = f"mobile_session:{user_id}:*"
                keys = await self.redis_service.redis.keys(pattern)

                for key in keys:
                    session_data = await self.redis_service.get(key)
                    if session_data and session_data.get("refresh_token") == refresh_token:
                        return key
        except Exception:
            pass

        return None

    async def create_device_fingerprint(
            self,
            device_info: Dict[str, Any]
    ) -> str:
        """Create a unique fingerprint for the device."""
        fingerprint_data = ""

        # Use stable device characteristics
        stable_fields = [
            "platform", "os_version", "device_model",
            "screen_resolution", "timezone", "language"
        ]

        for field in stable_fields:
            if field in device_info:
                fingerprint_data += str(device_info[field])

        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    async def track_device_usage(
            self,
            user_id: UUID,
            device_id: str,
            usage_data: Dict[str, Any]
    ) -> bool:
        """Track device usage patterns for security analysis."""
        usage_key = f"device_usage:{user_id}:{device_id}"

        # Get existing usage data
        existing_usage = await self.redis_service.get(usage_key) or []

        # Add new usage entry
        usage_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            **usage_data
        }
        existing_usage.append(usage_entry)

        # Keep only last 50 usage entries to prevent bloat
        existing_usage = existing_usage[-50:]

        # Store usage data for 30 days
        await self.redis_service.set(usage_key, existing_usage, expire=2592000)

        return True