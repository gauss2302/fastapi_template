from typing import Optional, List
from urllib.parse import urlencode

import httpx

from app.core.redis.redis import RedisService
from app.core.config.config import settings
from app.core.exceptions.exceptions import AuthenticationError
from app.schemas.user import GitHubUserInfo


class GitHubOAuthService:
    """Service for GitHub OAuth authentication."""

    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service
        self.client_id = settings.GITHUB_CLIENT_ID
        self.client_secret = settings.GITHUB_CLIENT_SECRET
        self.redirect_uri = settings.GITHUB_REDIRECT_URI

        # GitHub OAuth URLs
        self.auth_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.user_api_url = "https://api.github.com/user"
        self.user_emails_api_url = "https://api.github.com/user/emails"

    def get_authorization_url(self, state: str, scopes: Optional[List[str]] = None) -> str:
        """Generate GitHub OAuth authorization URL."""
        if scopes is None:
            scopes = ["user:email"]  # Default scopes

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "allow_signup": "true"
        }

        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> str:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.token_url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"
                    },
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": self.redirect_uri
                    }
                )

                if response.status_code != 200:
                    raise AuthenticationError(f"GitHub token exchange failed: {response.text}")

                token_data = response.json()

                if "error" in token_data:
                    raise AuthenticationError(
                        f"GitHub OAuth error: {token_data.get('error_description', 'Unknown error')}")

                access_token = token_data.get("access_token")
                if not access_token:
                    raise AuthenticationError("No access token received from GitHub")

                return access_token

            except httpx.HTTPError as e:
                raise AuthenticationError(f"Failed to exchange code for token: {str(e)}")

    async def get_user_info(self, access_token: str) -> GitHubUserInfo:
        """Get user information from GitHub API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"
        }

        async with httpx.AsyncClient() as client:
            try:
                # Get basic user info
                user_response = await client.get(self.user_api_url, headers=headers)

                if user_response.status_code != 200:
                    raise AuthenticationError(f"Failed to get GitHub user info: {user_response.text}")

                user_data = user_response.json()

                # Get user emails (GitHub email might be private)
                email = user_data.get("email")
                if not email:
                    try:
                        emails_response = await client.get(self.user_emails_api_url, headers=headers)
                        if emails_response.status_code == 200:
                            emails_data = emails_response.json()
                            # Find primary verified email
                            for email_info in emails_data:
                                if email_info.get("primary") and email_info.get("verified"):
                                    email = email_info.get("email")
                                    break
                            # Fallback to first verified email
                            if not email:
                                for email_info in emails_data:
                                    if email_info.get("verified"):
                                        email = email_info.get("email")
                                        break
                    except Exception:
                        pass  # Continue without email if API call fails

                # Convert GitHub user data to our schema
                github_user = GitHubUserInfo(
                    id=user_data["id"],
                    login=user_data["login"],
                    email=email,
                    name=user_data.get("name"),
                    avatar_url=user_data.get("avatar_url"),
                    bio=user_data.get("bio"),
                    company=user_data.get("company"),
                    location=user_data.get("location"),
                    blog=user_data.get("blog"),
                    public_repos=user_data.get("public_repos"),
                    followers=user_data.get("followers"),
                    following=user_data.get("following"),
                    created_at=user_data.get("created_at"),
                    updated_at=user_data.get("updated_at")
                )

                return github_user

            except httpx.HTTPError as e:
                raise AuthenticationError(f"Failed to get user info from GitHub: {str(e)}")

    async def get_user_repositories(self, access_token: str, per_page: int = 30) -> List[dict]:
        """Get user's repositories from GitHub API (optional feature)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://api.github.com/user/repos",
                    headers=headers,
                    params={
                        "sort": "updated",
                        "per_page": per_page,
                        "type": "owner"
                    }
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return []

            except Exception:
                return []

    async def cache_oauth_state(self, state: str, user_data: dict) -> None:
        """Cache OAuth state for CSRF protection."""
        await self.redis_service.set(
            f"github_oauth_state:{state}",
            user_data,
            expire=600  # 10 minutes
        )

    async def get_cached_oauth_state(self, state: str) -> Optional[dict]:
        """Get and remove cached OAuth state."""
        data = await self.redis_service.get(f"github_oauth_state:{state}")
        if data:
            await self.redis_service.delete(f"github_oauth_state:{state}")
        return data

    async def revoke_token(self, access_token: str) -> bool:
        """Revoke GitHub access token."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(
                    f"https://api.github.com/applications/{self.client_id}/token",
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"
                    },
                    json={"access_token": access_token},
                    auth=(self.client_id, self.client_secret)
                )

                return response.status_code in [204, 404]  # 204 = success, 404 = token already revoked

            except Exception:
                return False

    async def validate_token(self, access_token: str) -> bool:
        """Validate GitHub access token."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.user_api_url, headers=headers)
                return response.status_code == 200
            except Exception:
                return False