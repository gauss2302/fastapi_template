from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any
from uuid import UUID

from app.schemas.user import UserUpdate, User
from app.services.user_service import UserService
from app.core.dependencies import (
    get_current_user,
    rate_limit_api,
    get_user_service,
    get_current_superuser,
)
router = APIRouter()


@router.get("/me", response_model=User)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    _: Any = Depends(rate_limit_api),
) -> User:
    """Get current user profile."""
    return current_user

@router.put("/me", response_model=User)
async def update_my_profile(
        user_update: UserUpdate,
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
        _: Any = Depends(rate_limit_api),
) -> User:
    try:
        updated_user = await user_service.update_user(current_user.id, user_update)
        return updated_user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/me")
async def delete_my_account(
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service),
        _: Any = Depends(rate_limit_api),
) -> dict[str, str]:
    success = await user_service.delete_user(current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete account"
        )

    return {"message": "Account successfully deleted"}


# Admin endpoints
@router.get("/{user_id}", response_model=User)
async def get_user_by_id(
        user_id: UUID,
        user_service: UserService = Depends(get_user_service),
        _: User = Depends(get_current_superuser),
        __: Any = Depends(rate_limit_api),
) -> User:
    """Get user by ID (admin only)."""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.put("/{user_id}", response_model=User)
async def update_user_by_id(
        user_id: UUID,
        user_update: UserUpdate,
        user_service: UserService = Depends(get_user_service),
        _: User = Depends(get_current_superuser),
        __: Any = Depends(rate_limit_api),
) -> User:
    """Update user by ID (admin only)."""
    try:
        updated_user = await user_service.update_user(user_id, user_update)
        return updated_user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{user_id}/activate")
async def activate_user(
        user_id: UUID,
        user_service: UserService = Depends(get_user_service),
        _: User = Depends(get_current_superuser),
        __: Any = Depends(rate_limit_api),
) -> dict[str, str]:
    """Activate user account (admin only)."""
    success = await user_service.activate_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {"message": "User account activated"}


@router.post("/{user_id}/deactivate")
async def deactivate_user(
        user_id: UUID,
        user_service: UserService = Depends(get_user_service),
        _: User = Depends(get_current_superuser),
        __: Any = Depends(rate_limit_api),
) -> dict[str, str]:
    """Deactivate user account (admin only)."""
    success = await user_service.deactivate_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {"message": "User account deactivated"}


@router.delete("/{user_id}")
async def delete_user_by_id(
        user_id: UUID,
        user_service: UserService = Depends(get_user_service),
        _: User = Depends(get_current_superuser),
        __: Any = Depends(rate_limit_api),
) -> dict[str, str]:
    """Delete user by ID (admin only)."""
    success = await user_service.delete_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {"message": "User successfully deleted"}


@router.get("/stats/overview")
async def get_user_stats(
    user_service: UserService = Depends(get_user_service),
    _: User = Depends(get_current_superuser),
    __: Any = Depends(rate_limit_api),
) -> dict[str, Any]:
    """Get user statistics (admin only)."""
    stats = await user_service.get_user_stats()
    return stats