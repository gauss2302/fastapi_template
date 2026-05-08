from typing import Optional
from uuid import UUID

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.database.database import AsyncSessionLocal
from app.core.logging.logger import AppLogger
from app.core.security.security import security_service
from app.repositories.user_repository import UserRepository
from app.schemas.user import User

logger = AppLogger("auth_middleware")


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        self.public_paths = {
            "/health",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/openapi.json",
            "/api/v1/auth",
            "/api/v1/jobs/search",
            "/api/v1/jobs/slug",
            "/api/v1/companies/search",
            "/api/v1/companies/slug",
        }

    async def dispatch(self, request: Request, call_next):
        if self._is_public_path(request.url.path):
            return await call_next(request)

        token = self._extract_token(request)
        if not token:
            return self._auth_error("Missing authentication token")

        try:
            user = await self._authenticate_token(token)
            if not user:
                return self._auth_error("Invalid token")

            request.state.current_user = user

        except Exception:
            logger.exception("authentication_failed", path=request.url.path)
            return self._auth_error("Authentication failed")

        return await call_next(request)

    def _is_public_path(self, path: str) -> bool:
        return any(path.startswith(public_path) for public_path in self.public_paths)

    def _extract_token(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    async def _authenticate_token(self, token: str) -> Optional[User]:
        """Validate access JWT and load active user (read-only DB session)."""
        payload = security_service.verify_token(token, expected_type="access")
        if not payload or not payload.sub:
            return None

        try:
            user_id = UUID(payload.sub)
        except ValueError:
            logger.warning("invalid_user_id_in_token", sub=payload.sub)
            return None

        async with AsyncSessionLocal() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_id(user_id)

            if not db_user or not db_user.is_active:
                return None

            return User.model_validate(db_user)

    def _auth_error(self, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": message},
            headers={"WWW-Authenticate": "Bearer"},
        )
