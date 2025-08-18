import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Any

from app.schemas.user import (
    Token,
    GoogleTokenRequest,
    GoogleAccountLinkRequest,
    RefreshTokenRequest,
    UserRegister,
    UserLogin,
    UserPasswordUpdate,
    User,
)
from app.services.user_service import UserService
from app.services.auth_service import GoogleOAuthService
from app.utils.validators import PasswordValidator
from app.core.dependencies import (
    get_user_service,
    get_google_oauth_service,
    get_current_user,
    rate_limit_auth,
)
from app.core.exceptions import AuthenticationError, ConflictError

router = APIRouter()


@router.post("/register", response_model=User)
async def register(
    user_data: UserRegister,
    user_service: UserService = Depends(get_user_service),
        # SET RATE LIMITTING!!!!
    _: Any = Depends(rate_limit_auth),
) -> User:
    """Register a new user with email and password."""
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
async def login(
        login_data: UserLogin,
        request: Request,
        user_service: UserService = Depends(get_user_service),
        _: None = Depends(rate_limit_auth),
) -> Token:
    """Login with email and password."""
    try:
        user, token = await user_service.authenticate_user(login_data)
        return token
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# @router.post("/password/check-strength", response_model=PasswordStrengthResponse)
# async def check_password_strength(
#         password_check: PasswordStrengthCheck,
#         request: Request,
#         _: None = Depends(rate_limit_auth),
# ) -> PasswordStrengthResponse:
#     """Check password strength and get recommendations."""
#     is_valid, errors = PasswordValidator.validate_password_strength(password_check.password)
#     score, description = PasswordValidator.get_password_strength_score(password_check.password)
#
#     return PasswordStrengthResponse(
#         score=score,
#         description=description,
#         is_valid=is_valid,
#         errors=errors
#     )


@router.put("/password")
async def update_password(
        password_data: UserPasswordUpdate,
        request: Request,
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
        _: None = Depends(rate_limit_auth),
) -> dict[str, str]:
    """Update user password."""
    try:
        await user_service.update_password(current_user.id, password_data)
        return {"message": "Password updated successfully"}
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/google/login")
async def google_login(
        request: Request,
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        _: None = Depends(rate_limit_auth),
) -> dict[str, str]:
    """Initiate Google OAuth login."""
    state = secrets.token_urlsafe(32)

    await google_oauth_service.cache_oauth_state(state, {
        "origin": str(request.url_for("google_login")),
        "timestamp": str(request.state._state.get("timestamp", "")),
    })

    authorization_url = google_oauth_service.get_authorization_url(state)
    return {"authorization_url": authorization_url, "state": state}


@router.get("/google/callback")
async def google_callback(
        code: str,
        state: str,
        request: Request,
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
        _: None = Depends(rate_limit_auth),
) -> Token:
    """Handle Google OAuth callback."""
    try:
        cached_state = await google_oauth_service.get_cached_oauth_state(state)
        if not cached_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state parameter"
            )

        access_token = await google_oauth_service.exchange_code_for_token(code)
        google_user_info = await google_oauth_service.get_user_info(access_token)
        user, token = await user_service.authenticate_with_google(google_user_info)

        return token

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication failed")


@router.post("/google/token")
async def google_token_auth(
        token_request: GoogleTokenRequest,
        request: Request,
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
        _: None = Depends(rate_limit_auth),
) -> Token:
    """Authenticate with Google using authorization code."""
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
        user, token = await user_service.authenticate_with_google(google_user_info)

        return token

    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/google/link", response_model=User)
async def link_google_account(
        link_request: GoogleAccountLinkRequest,
        request: Request,
        current_user: User = Depends(get_current_user),
        google_oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
        user_service: UserService = Depends(get_user_service),
        _: None = Depends(rate_limit_auth),
) -> User:
    """Link Google account to current user."""
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
async def refresh_token(
        refresh_request: RefreshTokenRequest,
        request: Request,
        user_service: UserService = Depends(get_user_service),
        _: None = Depends(rate_limit_auth),
) -> Token:
    """Refresh access token."""
    try:
        return await user_service.refresh_token(refresh_request.refresh_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout")
async def logout(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    """Logout current user."""
    await user_service.logout(current_user.id)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> User:
    """Get current user information."""
    return current_user


@router.get("/health")
async def auth_health_check() -> dict[str, str]:
    """Health check endpoint for auth service."""
    return {"status": "healthy", "service": "auth"}