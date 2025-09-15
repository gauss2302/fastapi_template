from typing import Optional
import httpx
import requests
from google.oauth2 import id_token

from app.core.config.config import settings
from app.core.redis.redis import RedisService
from google_auth_oauthlib.flow import Flow
from app.core.exceptions.exceptions import AuthenticationError
from app.schemas.user import GoogleUserInfo


class GoogleOAuthService:
    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service
        self.client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        }

    def get_authorization_url(self, state: str) -> str:
        """Generate Google OAuth authorization URL."""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=[
                "openid",
                "email",
                "profile",
            ],
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state
        )
        return authorization_url

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token."""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=[
                "openid",
                "email",
                "profile",
            ],
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

        try:
            flow.fetch_token(code=code)
            return flow.credentials.token
        except Exception as e:
            raise AuthenticationError(f"Failed to exchange code for token: {str(e)}")

    async def get_user_info(self, access_token: str) -> GoogleUserInfo:
        """Get user information from Google API."""
        url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise AuthenticationError("Failed to get user info from google")

            user_data = response.json()
            return GoogleUserInfo(**user_data)

    async def verify_id_token(self, id_token_str: str) -> dict:
        """Verify Google ID token."""
        try:
            idinfo = id_token.verify_oauth2_token(
                id_token_str, requests.Request(), settings.GOOGLE_CLIENT_ID
            )

            if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
                raise AuthenticationError("Invalid token issuer")

            return idinfo
        except ValueError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")

    async def cache_oauth_state(self, state: str, user_data: dict) -> None:
        """Cache OAuth state for CSRF protection."""
        await self.redis_service.set(
            f"oauth_state:{state}",
            user_data,
            expire=600
        )

    async def get_cached_oauth_state(self, state: str) -> Optional[dict]:
        """Cache OAuth state for CSRF"""
        data = await self.redis_service.get(f"oauth_state:{state}")
        if data:
            await self.redis_service.delete(f"oauth_state:{state}")
        return data

    async def cache_refresh_token(self, user_id: str, refresh_token: str) -> None:
        """Cache refresh token"""
        await self.redis_service.set(
            f"refresh_token:{user_id}",
            refresh_token,
            expire=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        )

    async def revoke_refresh_token(self, user_id: str) -> None:
        """Revoke cached refresh token."""
        await self.redis_service.delete(f"refresh_token:{user_id}")

    async def get_refresh_token(self, user_id: str) -> Optional[str]:
        """Get cached refresh token."""
        return await self.redis_service.get(f"refresh_token:{user_id}")

    async def blacklist_token(self, token: str) -> None:
        """Add token to blacklist."""
        await self.redis_service.set(
            f"blacklist_token:{token}",
            "true",
            expire=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        )

    async def is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted."""
        return await self.redis_service.exists(f"blacklist_token:{token}")