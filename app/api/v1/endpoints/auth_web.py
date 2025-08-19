import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from typing import Any

from app.core.redis import RedisService, get_redis
from app.schemas.user import (
    GoogleTokenRequest,
    GoogleAccountLinkRequest,
    UserRegister,
    UserLogin,
    UserPasswordUpdate,
    User, GitHubAccountLinkRequest,
)
from app.services.github_auth_service import GitHubOAuthService
from app.schemas.user import GitHubTokenRequest
from app.services.user_service import UserService
from app.services.auth_service import GoogleOAuthService
from app.core.dependencies import (
    get_user_service,
    get_google_oauth_service,
    get_current_user,
    get_github_oauth_service
)
from app.core.exceptions import AuthenticationError, ConflictError

# Import rate limiting decorators with fallback
try:
    from app.middleware.rate_limiter import auth_rate_limit, strict_rate_limit
except ImportError:
    def auth_rate_limit(func):
        return func
    def strict_rate_limit(func):
        return func

router = APIRouter()


@router.post("/register", response_model=User)
@auth_rate_limit
async def web_register(
        user_data: UserRegister,
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Register a new user with email and password (web)."""
    try:
        user = await user_service.register_user(user_data)
        return user
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
async def web_login(
        login_data: UserLogin,
        response: Response,
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Login with email and password (web - uses cookies)."""
    try:
        user, tokens = await user_service.authenticate_user(login_data)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,  # HTTPS only in production
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"  # Restrict to auth endpoints
        )

        # Return only access token to client
        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.put("/password")
@auth_rate_limit
async def web_update_password(
        password_data: UserPasswordUpdate,
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Update user password (web)."""
    try:
        await user_service.update_password(current_user.id, password_data)
        return {"message": "Password updated successfully"}
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/google/login")
@auth_rate_limit
async def web_google_login(
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> dict[str, str]:
    """Initiate Google OAuth login (web)."""
    state = secrets.token_urlsafe(32)

    await google_oauth_service.cache_oauth_state(state, {
        "origin": "web_google_login",
        "timestamp": str(secrets.token_urlsafe(16)),
    })

    authorization_url = google_oauth_service.get_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.get("/google/callback")
@auth_rate_limit
async def web_google_callback(
        code: str,
        state: str,
        response: Response,
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Handle Google OAuth callback (web)."""
    try:
        cached_state = await google_oauth_service.get_cached_oauth_state(state)
        if not cached_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state parameter"
            )

        access_token = await google_oauth_service.exchange_code_for_token(code)
        google_user_info = await google_oauth_service.get_user_info(access_token)
        user, tokens = await user_service.authenticate_with_google(google_user_info)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication failed")


@router.post("/google/token")
@auth_rate_limit
async def web_google_token_auth(
        token_request: GoogleTokenRequest,
        response: Response,
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Authenticate with Google using authorization code (web)."""
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
        user, tokens = await user_service.authenticate_with_google(google_user_info)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/google/link", response_model=User)
@strict_rate_limit
async def web_link_google_account(
        link_request: GoogleAccountLinkRequest,
        current_user: User = Depends(get_current_user),
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Link Google account to current user (web)."""
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


@router.post("/refresh")
async def web_refresh_token(
        request: Request,
        response: Response,
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Refresh access token using HttpOnly cookie (web)."""
    # Get refresh token from HttpOnly cookie
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found"
        )

    try:
        # Generate new token pair and rotate refresh token
        user, new_tokens = await user_service.refresh_token(refresh_token)

        # Set new refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=new_tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=new_tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        # Return only new access token
        return {
            "access_token": new_tokens["access_token"],
            "token_type": "bearer",
            "expires_in": new_tokens["expires_in"]
        }

    except AuthenticationError as e:
        # Clear invalid refresh token cookie
        response.delete_cookie(
            key="refresh_token",
            path="/api/v1/auth"
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout")
async def web_logout(
        request: Request,
        response: Response,
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Logout current user and invalidate refresh token (web)."""
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")

    # Invalidate refresh token in Redis
    if refresh_token:
        await user_service.logout(current_user.id, refresh_token)

    # Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth"
    )

    return {"message": "Successfully logged out"}

# GitHub
@router.get("/github/login")
@auth_rate_limit
async def web_github_login(
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> dict[str, str]:
    """Initiate GitHub OAuth login (web)."""
    state = secrets.token_urlsafe(32)

    await github_oauth_service.cache_oauth_state(state, {
        "origin": "web_github_login",
        "timestamp": str(secrets.token_urlsafe(16)),
    })

    authorization_url = github_oauth_service.get_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.get("/github/callback")
@auth_rate_limit
async def web_github_callback(
        code: str,
        state: str,
        response: Response,
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Handle GitHub OAuth callback (web)."""
    try:
        cached_state = await github_oauth_service.get_cached_oauth_state(state)
        if not cached_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state parameter"
            )

        access_token = await github_oauth_service.exchange_code_for_token(code)
        github_user_info = await github_oauth_service.get_user_info(access_token)
        user, tokens = await user_service.authenticate_with_github(github_user_info)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user.model_dump()
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication failed")


@router.post("/github/token")
@auth_rate_limit
async def web_github_token_auth(
        token_request: GitHubTokenRequest,
        response: Response,
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Authenticate with GitHub using authorization code (web)."""
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
        user, tokens = await user_service.authenticate_with_github(github_user_info)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user.model_dump()
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/github/link", response_model=User)
@strict_rate_limit
async def web_link_github_account(
        link_request: GitHubAccountLinkRequest,
        current_user: User = Depends(get_current_user),
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Link GitHub account to current user (web)."""
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
async def web_unlink_github_account(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Unlink GitHub account from current user (web)."""
    success = await user_service.unlink_github_account(current_user.id)
    if success:
        return {"message": "GitHub account unlinked successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to unlink GitHub account"
        )

# GitHub OAuth endpoints for web
@router.get("/github/login")
@auth_rate_limit
async def web_github_login(
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
) -> dict[str, str]:
    """Initiate GitHub OAuth login (web)."""
    state = secrets.token_urlsafe(32)

    await github_oauth_service.cache_oauth_state(state, {
        "origin": "web_github_login",
        "timestamp": str(secrets.token_urlsafe(16)),
    })

    authorization_url = github_oauth_service.get_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.get("/github/callback")
@auth_rate_limit
async def web_github_callback(
        code: str,
        state: str,
        response: Response,
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Handle GitHub OAuth callback (web)."""
    try:
        cached_state = await github_oauth_service.get_cached_oauth_state(state)
        if not cached_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state parameter"
            )

        access_token = await github_oauth_service.exchange_code_for_token(code)
        github_user_info = await github_oauth_service.get_user_info(access_token)
        user, tokens = await user_service.authenticate_with_github(github_user_info)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user.model_dump()
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication failed")


@router.post("/github/token")
@auth_rate_limit
async def web_github_token_auth(
        token_request: GitHubTokenRequest,
        response: Response,
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Authenticate with GitHub using authorization code (web)."""
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
        user, tokens = await user_service.authenticate_with_github(github_user_info)

        # Set refresh token as HttpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=tokens["refresh_expires_in"],
            path="/api/v1/auth"
        )

        return {
            "access_token": tokens["access_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"],
            "user": user.model_dump()
        }

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/github/link", response_model=User)
@strict_rate_limit
async def web_link_github_account(
        link_request: GitHubAccountLinkRequest,
        current_user: User = Depends(get_current_user),
        github_oauth_service: GitHubOAuthService = Depends(get_github_oauth_service),
        user_service: UserService = Depends(get_user_service),
) -> User:
    """Link GitHub account to current user (web)."""
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
async def web_unlink_github_account(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Unlink GitHub account from current user (web)."""
    success = await user_service.unlink_github_account(current_user.id)
    if success:
        return {"message": "GitHub account unlinked successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to unlink GitHub account"
        )


@router.get("/me", response_model=User)
async def web_get_current_user_info(
        current_user: User = Depends(get_current_user)
) -> User:
    """Get current user information (web)."""
    return current_user


@router.get("/health")
async def web_auth_health_check() -> dict[str, str]:
    """Health check endpoint for web auth service."""
    return {"status": "healthy", "service": "web_auth"}