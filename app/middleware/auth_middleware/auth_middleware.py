from typing import Optional
from uuid import UUID
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import time

from app.core.database.database import get_db
from app.core.security.security import security_service
from app.core.deps.dependencies import get_user_service
from app.repositories.user_repository import UserRepository
from app.schemas.user import User


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        self.public_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/auth",
            "/api/v1/jobs/search",
            "/api/v1/jobs/slug",
            "/api/v1/companies/search",
            "/api/v1/companies/slug"
        }

    async def dispatch(self, request: Request, call_next):
        # Пропускаем публичные маршруты
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # Извлекаем токен
        token = self._extract_token(request)
        if not token:
            return self._auth_error("Missing authentication token")

        # Проверяем токен и получаем пользователя
        try:
            user = await self._authenticate_token(token)
            if not user:
                return self._auth_error("Invalid token")

            # Сохраняем пользователя в состоянии запроса
            request.state.current_user = user

        except Exception as e:
            return self._auth_error(f"Authentication failed: {str(e)}")

        return await call_next(request)

    def _is_public_path(self, path: str) -> bool:
        """Проверяет, является ли путь публичным"""
        return any(path.startswith(public_path) for public_path in self.public_paths)

    def _extract_token(self, request: Request) -> Optional[str]:
        """Извлекает токен из заголовка Authorization"""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    async def _authenticate_token(self, token: str) -> Optional[User]:
        """Проверяет токен и возвращает пользователя"""
        # Проверяем JWT токен
        payload = security_service.verify_token(token)
        if not payload or not payload.sub:
            return None, None

        try:
            user_id = UUID(payload.sub)
            async for db in get_db():
                user_repo = UserRepository(db)
                db_user = await user_repo.get_by_id(user_id)
                
                if not db_user or not db_user.is_active:
                    return None
                
                return User.model_validate(db_user)
        
        except (ValueError, Exception) as e:
            print(f"Error in _authenticate_token: {e}")
            return None

    def _auth_error(self, message: str) -> JSONResponse:
        """Возвращает ошибку аутентификации"""
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": message},
            headers={"WWW-Authenticate": "Bearer"}
        )


# app/core/auth_helpers.py
from fastapi import Request, HTTPException, status
from app.schemas.user import User


def get_current_user(request: Request) -> User:
    """Получает текущего пользователя из middleware"""
    user = getattr(request.state, 'current_user', None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user


def get_current_superuser(request: Request) -> User:
    """Получает текущего суперпользователя из middleware"""
    user = get_current_user(request)
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return user