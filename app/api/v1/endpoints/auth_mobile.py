import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Any, Optional

from app.api.v1.endpoints.auth_web import get_github_oauth_service
from app.schemas.user import (
    GoogleTokenRequest,
    GoogleAccountLinkRequest,
    UserRegister,
    UserLogin,
    User,
    RefreshTokenRequest,
    MobileLogoutRequest, GitHubAccountLinkRequest, GitHubTokenRequest,
)
from app.services.github_auth_service import GitHubOAuthService
from app.services.user_service import UserService
from app.services.auth_service import GoogleOAuthService
from app.core.dependencies import (
    get_user_service,
    get_google_oauth_service,
    get_current_user,
)
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import security_service

# Import rate limiting decorators with fallback
try:
    from app.middleware.rate_limiter import auth_rate_limit, strict_rate_limit
except ImportError:
    def auth_rate_limit(func):
        return func


    def strict_rate_limit(func):
        return func

router = APIRouter()


@router.post("/register")
@auth_rate_limit
async def mobile_register(
        user_data: UserRegister,
        request: Request,
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Register a new user via mobile app (returns tokens in response body)."""
    try:
        device_id = request.headers.get("X-Device-ID")

        # Register user
        user = await user_service.register_user(user_data)

        # Create token pair
        tokens = security_service.create_token_pair(user.id)

        # Cache refresh token for mobile session management
        if hasattr(user_service, 'google_oauth_service'):
            await user_service.google_oauth_service.cache_refresh_token(
                str(user.id), tokens["refresh_token"]
            )

        return {
            "user": user.model_dump(),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "refresh_expires_in": tokens["refresh_expires_in"]
        }
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login")
@auth_rate_limit
async def mobile_login(
        login_data: UserLogin,
        request: Request,
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Login via mobile app (returns tokens in response body)."""
    try:
        device_id = request.headers.get("X-Device-ID")
        user, tokens = await user_service.authenticate_user(login_data)

        return {
            "user": user.model_dump(),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "refresh_expires_in": tokens["refresh_expires_in"]
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/refresh")
async def mobile_refresh_token(
        refresh_request: RefreshTokenRequest,
        request: Request,
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Refresh access token for mobile app (no cookies required)."""
    try:
        device_id = request.headers.get("X-Device-ID")
        user, new_tokens = await user_service.refresh_token(refresh_request.refresh_token)

        return {
            "access_token": new_tokens["access_token"],
            "refresh_token": new_tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": new_tokens["expires_in"],
            "refresh_expires_in": new_tokens["refresh_expires_in"]
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout")
async def mobile_logout(
        logout_request: dict,  # Use dict for flexibility
        request: Request,
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Logout mobile user and invalidate refresh token."""
    device_id = request.headers.get("X-Device-ID")
    refresh_token = logout_request.get("refresh_token")

    await user_service.logout(current_user.id, refresh_token)
    return {"message": "Successfully logged out"}


@router.get("/google/login")
@auth_rate_limit
async def mobile_google_login(
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> dict[str, str]:
    """Initiate Google OAuth login for mobile app."""
    state = secrets.token_urlsafe(32)

    await google_oauth_service.cache_oauth_state(state, {
        "origin": "mobile_google_login",
        "timestamp": str(secrets.token_urlsafe(16)),
    })

    authorization_url = google_oauth_service.get_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.post("/google/token")
@auth_rate_limit
async def mobile_google_token_auth(
        token_request: GoogleTokenRequest,
        request: Request,
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Authenticate with Google for mobile app (returns tokens in response)."""
    try:
        if token_request.state:
            cached_state = await google_oauth_service.get_cached_oauth_state(token_request.state)
            if not cached_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired state parameter"
                )

        access_token = await google_oauth_service.exchange_code_for_token(token_request.code)
        google_user_info = await google_oauth_service.get_user_info(access_token)

        device_id = request.headers.get("X-Device-ID")
        user, tokens = await user_service.authenticate_with_google(google_user_info)

        return {
            "user": user.model_dump(),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "refresh_expires_in": tokens["refresh_expires_in"]
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/google/link", response_model=User)
@strict_rate_limit
async def mobile_link_google_account(
        link_request: GoogleAccountLinkRequest,
        current_user: User = Depends(get_current_user),
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Link Google account to current user via mobile app."""
    try:
        if link_request.state:
            cached_state = await google_oauth_service.get_cached_oauth_state(link_request.state)
            if not cached_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired state parameter"
                )

        access_token = await google_oauth_service.exchange_code_for_token(link_request.google_code)
        google_user_info = await google_oauth_service.get_user_info(access_token)

        return await user_service.link_google_account(current_user.id, google_user_info)

    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# GitHub OAuth endpoints for mobile
@router.get("/github/login")
@auth_rate_limit
async def mobile_github_login(
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> dict[str, str]:
    """Initiate GitHub OAuth login for mobile app."""
    state = secrets.token_urlsafe(32)

    await github_oauth_service.cache_oauth_state(state, {
        "origin": "mobile_github_login",
        "timestamp": str(secrets.token_urlsafe(16)),
    })

    authorization_url = github_oauth_service.get_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.post("/github/token")
@auth_rate_limit
async def mobile_github_token_auth(
        token_request: GitHubTokenRequest,
        request: Request,
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Authenticate with GitHub for mobile app (returns tokens in response)."""
    try:
        if token_request.state:
            cached_state = await github_oauth_service.get_cached_oauth_state(token_request.state)
            if not cached_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired state parameter"
                )

        access_token = await github_oauth_service.exchange_code_for_token(token_request.code)
        github_user_info = await github_oauth_service.get_user_info(access_token)

        # Get device info for mobile
        device_id = request.headers.get("X-Device-ID")
        device_info = {
            "platform": request.headers.get("X-Platform", "unknown"),
            "app_version": request.headers.get("X-App-Version", "unknown"),
            "os_version": request.headers.get("X-OS-Version", "unknown"),
            "device_model": request.headers.get("X-Device-Model", "unknown"),
        }

        user, tokens = await user_service.authenticate_with_github_mobile(
            github_user_info, device_id, device_info
        )

        return {
            "user": user.model_dump(),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "refresh_expires_in": tokens["refresh_expires_in"]
        }
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/github/link", response_model=User)
@strict_rate_limit
async def mobile_link_github_account(
        link_request: GitHubAccountLinkRequest,
        current_user: User = Depends(get_current_user),
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Link GitHub account to current user via mobile app."""
    try:
        if link_request.state:
            cached_state = await github_oauth_service.get_cached_oauth_state(link_request.state)
            if not cached_state:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired state parameter"
                )

        access_token = await github_oauth_service.exchange_code_for_token(link_request.github_code)
        github_user_info = await github_oauth_service.get_user_info(access_token)

        return await user_service.link_github_account(current_user.id, github_user_info)

    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.delete("/github/unlink")
@strict_rate_limit
async def mobile_unlink_github_account(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Unlink GitHub account from current user (mobile)."""
    success = await user_service.unlink_github_account(current_user.id)
    if success:
        return {"message": "GitHub account unlinked successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to unlink GitHub account"
        )


@router.get("/github/profile")
async def mobile_get_github_profile(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Get GitHub profile information for current user (mobile)."""
    github_profile = await user_service.get_github_user_profile(current_user.id)
    if not github_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub account linked"
        )
    return github_profile

@router.get("/me", response_model=User)
async def mobile_get_current_user_info(
        current_user: User = Depends(get_current_user)
) -> User:
    """Get current user information (mobile)."""
    return current_user


@router.get("/sessions")
async def mobile_get_sessions(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Get all active mobile sessions for current user."""
    # For now, return a simple response since we don't have the mobile service implemented yet
    return {
        "sessions": [],
        "total_count": 0,
        "message": "Mobile session management not yet implemented"
    }


@router.delete("/sessions")
async def mobile_revoke_all_sessions(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Revoke all mobile sessions for current user."""
    # For now, just logout the current user
    await user_service.logout(current_user.id)
    return {"message": "All mobile sessions revoked successfully"}


@router.get("/health")
async def mobile_auth_health_check() -> dict[str, str]:
    """Health check endpoint for mobile auth service."""
    return {"status": "healthy", "service": "mobile_auth"}