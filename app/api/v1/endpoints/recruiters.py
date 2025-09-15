from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from uuid import UUID

from requests import Request

from app.middleware.rate_limiter import rate_limit, strict_rate_limit
from app.schemas.recruiter import (
    Recruiter, RecruiterCreate, RecruiterUpdate, RecruiterApproval,
    RecruiterPermissions, RecruiterInvitationRequest,
)
from app.schemas.user import User
from app.models.recruiter import RecruiterStatus
from app.services.company_service import CompanyService
from app.core.dependencies import (
    get_current_user,
    get_current_superuser,
    get_company_service,
)

router = APIRouter()


# ============================================================================
# CURRENT USER RECRUITER ENDPOINTS
# ============================================================================

@router.get("/me", response_model=Optional[Recruiter])
@rate_limit
async def get_my_recruiter_profile(
        request: Request,
        company_service: CompanyService = Depends(get_company_service),
) -> Optional[Recruiter]:
    """
    Get current user's recruiter profile

    Returns the recruiter profile for the authenticated user,
    or null if the user is not a recruiter.
    """
    current_user = get_current_user(request)
    recruiter = await company_service.get_recruiter_by_user_id(current_user.id)
    return recruiter


@router.post("/me", response_model=Recruiter)
@rate_limit
async def create_my_recruiter_profile(
        recruiter_data: RecruiterCreate,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Recruiter:
    """
    Create recruiter profile for current user

    Applies to join a company as a recruiter. The application will be pending
    until approved by someone with recruiter approval permissions.
    """
    try:
        recruiter = await company_service.create_recruiter_profile(recruiter_data, current_user.id)
        return recruiter
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/me", response_model=Recruiter)
@rate_limit
async def update_my_recruiter_profile(
        recruiter_data: RecruiterUpdate,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Recruiter:
    """
    Update current user's recruiter profile

    Users can update their own recruiter profile information.
    """
    # First get current recruiter profile
    current_recruiter = await company_service.get_recruiter_by_user_id(current_user.id)
    if not current_recruiter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter profile not found"
        )

    try:
        recruiter = await company_service.update_recruiter_profile(
            current_recruiter.id, recruiter_data, current_user.id
        )
        return recruiter
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/me")
@strict_rate_limit
async def deactivate_my_recruiter_profile(
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Deactivate current user's recruiter profile

    Users can deactivate their own recruiter profile.
    """
    current_recruiter = await company_service.get_recruiter_by_user_id(current_user.id)
    if not current_recruiter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recruiter profile not found"
        )

    try:
        success = await company_service.deactivate_recruiter(current_recruiter.id, current_user.id)
        if success:
            return {"message": "Recruiter profile deactivated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recruiter not found"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# COMPANY RECRUITER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/company/{company_id}", response_model=dict)
@rate_limit
async def get_company_recruiters(
        company_id: UUID,
        status_filter: Optional[RecruiterStatus] = Query(None, description="Filter by recruiter status"),
        skip: int = Query(0, ge=0, description="Number of recruiters to skip"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of recruiters to return"),
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get recruiters for a company

    Returns list of recruiters for the specified company.
    User must have access to the company.
    """
    try:
        recruiters, total = await company_service.get_company_recruiters(
            company_id=company_id,
            requesting_user_id=current_user.id,
            status=status_filter,
            skip=skip,
            limit=limit
        )

        return {
            "recruiters": recruiters,
            "total": total,
            "company_id": str(company_id),
            "status_filter": status_filter,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/company/{company_id}/invite")
@strict_rate_limit
async def invite_recruiter_to_company(
        company_id: UUID,
        invitation_data: RecruiterInvitationRequest,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Invite a recruiter to join company

    Sends an invitation to join the company as a recruiter.
    User must have recruiter approval permissions.
    """
    try:
        result = await company_service.invite_recruiter(
            company_id, invitation_data, current_user.id
        )
        return result
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/company/{company_id}/pending", response_model=dict)
@rate_limit
async def get_company_pending_recruiters(
        company_id: UUID,
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get pending recruiter applications for a company

    Returns recruiters waiting for approval in the specified company.
    User must have recruiter approval permissions.
    """
    try:
        recruiters, total = await company_service.get_pending_recruiters(
            requesting_user_id=current_user.id,
            company_id=company_id,
            skip=skip,
            limit=limit
        )

        return {
            "pending_recruiters": recruiters,
            "total": total,
            "company_id": str(company_id),
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/company/{company_id}/stats", response_model=dict)
@rate_limit
async def get_company_recruiter_stats(
        company_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get recruiter statistics for a company

    Returns detailed statistics about recruiters in the company.
    """
    try:
        # Verify access permission
        await company_service._verify_company_access_permission(company_id, current_user.id)

        # Get department stats
        department_stats = await company_service.get_company_department_stats(company_id, current_user.id)

        # Get general stats from recruiter repository
        recruiter_repo = company_service.recruiter_repo
        general_stats = await recruiter_repo.get_company_stats(company_id)

        return {
            "company_id": str(company_id),
            "general_stats": general_stats,
            "department_stats": department_stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# INDIVIDUAL RECRUITER MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/{recruiter_id}", response_model=Recruiter)
@rate_limit
async def get_recruiter_by_id(
        recruiter_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Recruiter:
    """
    Get recruiter by ID

    Returns detailed recruiter information. User must have access to the company
    or be the recruiter themselves.
    """
    try:
        # Get recruiter from repository with relations
        recruiter_repo = company_service.recruiter_repo
        recruiter = await recruiter_repo.get_by_id_with_relations(recruiter_id)

        if not recruiter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recruiter not found"
            )

        # Check if user owns this profile or has company access
        if recruiter.user_id != current_user.id:
            await company_service._verify_company_access_permission(recruiter.company_id, current_user.id)

        return Recruiter.model_validate(recruiter)
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{recruiter_id}", response_model=Recruiter)
@rate_limit
async def update_recruiter_by_id(
        recruiter_id: UUID,
        recruiter_data: RecruiterUpdate,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Recruiter:
    """
    Update recruiter by ID

    Updates recruiter profile. User must own the profile or have 
    company management permissions.
    """
    try:
        recruiter = await company_service.update_recruiter_profile(
            recruiter_id, recruiter_data, current_user.id
        )
        return recruiter
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{recruiter_id}/approve", response_model=Recruiter)
@strict_rate_limit
async def approve_or_reject_recruiter(
        recruiter_id: UUID,
        approval_data: RecruiterApproval,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Recruiter:
    """
    Approve or reject recruiter application

    Approves or rejects a pending recruiter application.
    User must have recruiter approval permissions in the company.
    """
    try:
        recruiter = await company_service.approve_recruiter(
            recruiter_id, approval_data, current_user.id
        )
        return recruiter
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{recruiter_id}/permissions", response_model=Recruiter)
@strict_rate_limit
async def update_recruiter_permissions(
        recruiter_id: UUID,
        permissions: RecruiterPermissions,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Recruiter:
    """
    Update recruiter permissions

    Updates permissions for a recruiter. Only company administrators
    can modify recruiter permissions.
    """
    try:
        recruiter = await company_service.update_recruiter_permissions(
            recruiter_id, permissions, current_user.id
        )
        return recruiter
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{recruiter_id}")
@strict_rate_limit
async def deactivate_recruiter_by_id(
        recruiter_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Deactivate recruiter by ID

    Deactivates a recruiter. User must own the profile or have
    company management permissions.
    """
    try:
        success = await company_service.deactivate_recruiter(recruiter_id, current_user.id)
        if success:
            return {"message": "Recruiter deactivated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recruiter not found"
            )
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{recruiter_id}/activate")
@strict_rate_limit
async def activate_recruiter_by_id(
        recruiter_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Activate recruiter by ID

    Reactivates a previously deactivated recruiter.
    User must have company management permissions.
    """
    try:
        # Get recruiter to verify company access
        recruiter_repo = company_service.recruiter_repo
        recruiter = await recruiter_repo.get_by_id(recruiter_id)

        if not recruiter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recruiter not found"
            )

        # Verify user has company management permission
        await company_service.verify_company_management_permission(recruiter.company_id, current_user.id)

        success = await recruiter_repo.activate(recruiter_id)
        if success:
            return {"message": "Recruiter activated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recruiter not found"
            )
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# SEARCH AND BULK OPERATIONS ENDPOINTS
# ============================================================================

@router.get("/search", response_model=dict)
@rate_limit
async def search_recruiters(
        current_user: User = Depends(get_current_user),
        company_id: Optional[UUID] = Query(None, description="Filter by company ID"),
        search_term: Optional[str] = Query(None, description="Search in name, email, position"),
        status: Optional[RecruiterStatus] = Query(None, description="Filter by status"),
        department: Optional[str] = Query(None, description="Filter by department"),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Search recruiters with various filters

    Allows searching recruiters across companies (if user has access)
    or within a specific company.
    """
    try:
        recruiters, total = await company_service.search_recruiters(
            requesting_user_id=current_user.id,
            company_id=company_id,
            search_term=search_term,
            status=status,
            department=department,
            skip=skip,
            limit=limit
        )

        return {
            "recruiters": recruiters,
            "total": total,
            "filters": {
                "company_id": str(company_id) if company_id else None,
                "search_term": search_term,
                "status": status,
                "department": department
            },
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/bulk/approve")
@strict_rate_limit
async def bulk_approve_recruiters(
        recruiter_ids: List[UUID],
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Bulk approve multiple recruiters

    Approves multiple recruiter applications at once.
    User must have approval permissions for all recruiters' companies.
    """
    try:
        result = await company_service.bulk_approve_recruiters(
            recruiter_ids, current_user.id
        )
        return result
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/bulk/permissions")
@strict_rate_limit
async def bulk_update_recruiter_permissions(
        recruiter_ids: List[UUID],
        permissions: RecruiterPermissions,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Bulk update recruiter permissions

    Updates permissions for multiple recruiters at once.
    User must have company management permissions for all recruiters.
    """
    try:
        # Verify permissions for all recruiters
        recruiter_repo = company_service.recruiter_repo
        for recruiter_id in recruiter_ids:
            recruiter = await recruiter_repo.get_by_id(recruiter_id)
            if recruiter:
                await company_service._verify_company_management_permission(
                    recruiter.company_id, current_user.id
                )

        # Bulk update permissions
        updated_count = await recruiter_repo.bulk_update_permissions(
            recruiter_ids, permissions
        )

        return {
            "updated": updated_count,
            "total_requested": len(recruiter_ids),
            "permissions": permissions.model_dump()
        }
    except Exception as e:
        if "authorization" in str(e).lower() or "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# ADMIN ONLY ENDPOINTS
# ============================================================================

@router.get("/admin/global-stats", response_model=dict)
@rate_limit
async def get_global_recruiter_stats(
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get global recruiter statistics (admin only)

    Returns platform-wide statistics about recruiters.
    """
    recruiter_repo = company_service.recruiter_repo
    stats = await recruiter_repo.get_global_stats()

    return {
        "global_recruiter_stats": stats,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/admin/pending-all", response_model=dict)
@rate_limit
async def get_all_pending_recruiters(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get all pending recruiter applications across all companies (admin only)

    Returns all pending recruiter applications platform-wide.
    """
    recruiters, total = await company_service.get_pending_recruiters(
        requesting_user_id=current_user.id,
        company_id=None,  # All companies
        skip=skip,
        limit=limit
    )

    return {
        "pending_recruiters": recruiters,
        "total": total,
        "skip": skip,
        "limit": limit
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def recruiter_service_health_check() -> dict:
    """Health check endpoint for recruiter service."""
    return {
        "status": "healthy",
        "service": "recruiters",
        "timestamp": datetime.now().isoformat()
    }