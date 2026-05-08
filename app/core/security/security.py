from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config.config import settings
from app.schemas.user import TokenPayload

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_TOKEN_TYPE_ACCESS = "access"
JWT_TOKEN_TYPE_REFRESH = "refresh"


class SecurityService:
    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def create_access_token(
            subject: str | UUID,
            expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token."""
        if expires_delta:
            expire = SecurityService._now_utc() + expires_delta
        else:
            expire = SecurityService._now_utc() + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode = {
            "exp": expire,
            "sub": str(subject),
            "type": JWT_TOKEN_TYPE_ACCESS,
        }
        return jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

    @staticmethod
    def create_refresh_token(
            subject: str | UUID,
            expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT refresh token."""
        if expires_delta:
            expire = SecurityService._now_utc() + expires_delta
        else:
            expire = SecurityService._now_utc() + timedelta(
                minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES
            )

        to_encode = {
            "exp": expire,
            "sub": str(subject),
            "type": JWT_TOKEN_TYPE_REFRESH,
        }
        return jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

    @staticmethod
    def verify_token(
        token: str,
        *,
        expected_type: Optional[str] = None,
    ) -> Optional[TokenPayload]:
        """Verify JWT signature and expiry; enforce access vs refresh with optional legacy migration."""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
        except jwt.PyJWTError:
            return None

        token_type = payload.get("type")

        if expected_type is None:
            return TokenPayload(**payload)

        if expected_type == JWT_TOKEN_TYPE_ACCESS:
            if token_type == JWT_TOKEN_TYPE_REFRESH:
                return None
            if token_type == JWT_TOKEN_TYPE_ACCESS:
                return TokenPayload(**payload)
            if token_type is None and settings.JWT_ACCESS_ALLOW_MISSING_TYPE_CLAIM:
                return TokenPayload(**payload)
            return None

        if expected_type == JWT_TOKEN_TYPE_REFRESH:
            if token_type == JWT_TOKEN_TYPE_ACCESS:
                return None
            if token_type == JWT_TOKEN_TYPE_REFRESH:
                return TokenPayload(**payload)
            if token_type is None and settings.JWT_REFRESH_ALLOW_MISSING_TYPE_CLAIM:
                return TokenPayload(**payload)
            return None

        if token_type != expected_type:
            return None
        return TokenPayload(**payload)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generate password hash."""
        return pwd_context.hash(password)

    @staticmethod
    def create_token_pair(user_id: UUID) -> dict[str, Any]:
        """Create access and refresh token pair."""
        access_token = SecurityService.create_access_token(user_id)
        refresh_token = SecurityService.create_refresh_token(user_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "refresh_expires_in": settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        }


security_service = SecurityService()