from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import List, Optional
from uuid import UUID

from app.middleware.rate_limiter.rate_limiter import rate_limit, strict_rate_limit
from app.schemas.company import (
    Company, CompanyUpdate, CompanyVerification, CompanyStats,
    CompanyRegistrationRequest, CompanySearchFilters, CompanyPublic
)
from app.schemas.user import User
from app.models.company import CompanyStatus
from app.services.company_service import CompanyService
from app.core.deps.dependencies import (
    get_current_user,
    get_current_superuser,
    get_company_service,
)
router = APIRouter()


# ============================================================================
# PUBLIC COMPANY ENDPOINTS (No authentication required)
# ============================================================================

@router.get("/search", response_model=dict)
@rate_limit
async def search_companies(
        industry: Optional[str] = Query(None, description="Filter by industry"),
        company_size: Optional[str] = Query(None, description="Filter by company size"),
        location: Optional[str] = Query(None, description="Filter by location"),
        is_hiring: Optional[bool] = Query(None, description="Filter by hiring status"),
        verified_only: bool = Query(True, description="Show only verified companies"),
        skip: int = Query(0, ge=0, description="Number of companies to skip"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of companies to return"),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Search companies (public endpoint)

    This endpoint allows anyone to search for companies without authentication.
    Only verified and active companies are returned by default.
    """
    try:
        filters = CompanySearchFilters(
            industry=industry,
            company_size=company_size,
            location=location,
            is_hiring=is_hiring,
            verified_only=verified_only
        )

        companies, total = await company_service.search_companies(filters, skip, limit)

        # Convert to public format (hide sensitive data)
        public_companies = [CompanyPublic.model_validate(company) for company in companies]

        return {
            "companies": public_companies,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/slug/{slug}", response_model=CompanyPublic)
@rate_limit
async def get_company_by_slug(
        slug: str,
        company_service: CompanyService = Depends(get_company_service),
) -> CompanyPublic:
    """
    Get company by slug (public endpoint)

    Returns public company information that can be viewed by anyone.
    """
    company = await company_service.get_company_by_slug(slug)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )

    # Only show if company is verified and active
    if company.status != CompanyStatus.VERIFIED or not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )

    return CompanyPublic.model_validate(company)


@router.get("/industries", response_model=List[str])
@rate_limit
async def get_company_industries(
        company_service: CompanyService = Depends(get_company_service),
) -> List[str]:
    """Get all available industries (public endpoint)"""
    return await company_service.get_company_industries()


@router.get("/locations", response_model=List[str])
@rate_limit
async def get_company_locations(
        company_service: CompanyService = Depends(get_company_service),
) -> List[str]:
    """Get all available company locations (public endpoint)"""
    return await company_service.get_company_locations()


# ============================================================================
# AUTHENTICATED COMPANY ENDPOINTS
# ============================================================================


@router.post("/register", response_model=Company)
# @strict_rate_limit()
async def register_company(
        reg_data: CompanyRegistrationRequest,
        request: Request,
        company_service: CompanyService = Depends(get_company_service)
) -> Company:
    """
      Register a new company

      Creates a new company and automatically makes the current user
      the first recruiter with admin permissions.
      """
    try:
        current_user = get_current_user(request)
        company = await company_service.register_company(reg_data, current_user.id)
        return company
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{company_id}", response_model=Company)
# @rate_limit
async def get_company_by_id(
        company_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Company:
    """
    Get company by ID

    Returns full company information. User must have access to the company.
    """
    try:
        # This will verify user has access to the company
        company = await company_service.get_company_by_id(company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )

        # Verify user has access (will be checked in service layer)
        await company_service._verify_company_access_permission(company_id, current_user.id)

        return company
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


@router.put("/{company_id}", response_model=Company)
@rate_limit
async def update_company(
        company_id: UUID,
        company_data: CompanyUpdate,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> Company:
    """
    Update company information

    Only company administrators can update company information.
    """
    try:
        company = await company_service.update_company(
            company_id, company_data, current_user.id
        )
        return company
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


@router.get("/{company_id}/stats", response_model=CompanyStats)
@rate_limit
async def get_company_stats(
        company_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> CompanyStats:
    """
    Get company statistics

    Returns detailed statistics about the company including recruiter counts,
    job postings, applications, etc. Only accessible to company members.
    """
    try:
        stats = await company_service.get_company_stats(company_id, current_user.id)
        return stats
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


@router.post("/{company_id}/hiring-status")
@rate_limit
async def update_hiring_status(
        company_id: UUID,
        is_hiring: bool,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Update company hiring status

    Toggle whether the company is actively hiring.
    """
    try:
        # Verify user has management permission
        await company_service.verify_company_management_permission(company_id, current_user.id)

        # Update hiring status using company repository
        company_repo = company_service.company_repo
        success = await company_repo.update_hiring_status(company_id, is_hiring)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )

        return {
            "message": f"Company hiring status updated to {'hiring' if is_hiring else 'not hiring'}",
            "is_hiring": is_hiring
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


@router.delete("/{company_id}")
@strict_rate_limit
async def deactivate_company(
        company_id: UUID,
        current_user: User = Depends(get_current_user),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Deactivate company

    Deactivates the company and all associated recruiters.
    Only company administrators can perform this action.
    """
    try:
        success = await company_service.deactivate_company(company_id, current_user.id)
        if success:
            return {"message": "Company deactivated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
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
# ADMIN ONLY ENDPOINTS
# ============================================================================

@router.get("/admin/pending", response_model=dict)
@rate_limit
async def get_pending_companies(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get pending companies for verification (admin only)

    Returns companies that are waiting for admin verification.
    """
    companies, total = await company_service.get_companies_by_status(
        CompanyStatus.PENDING, skip, limit
    )

    return {
        "companies": companies,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/admin/by-status", response_model=dict)
@rate_limit
async def get_companies_by_status(
        company_status: CompanyStatus = Query(..., description="Company status to filter by"),
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get companies by status (admin only)

    Returns companies filtered by their verification status.
    """
    companies, total = await company_service.get_companies_by_status(
        company_status, skip, limit
    )

    return {
        "companies": companies,
        "total": total,
        "status": company_status,
        "skip": skip,
        "limit": limit
    }


@router.post("/{company_id}/verify", response_model=Company)
@strict_rate_limit
async def verify_company(
        company_id: UUID,
        verification_data: CompanyVerification,
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> Company:
    """
    Verify or reject company (admin only)

    Approves or rejects a company's verification request.
    """
    try:
        company = await company_service.verify_company(
            company_id, verification_data, current_user.id
        )
        return company
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{company_id}/activate")
@strict_rate_limit
async def activate_company(
        company_id: UUID,
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Activate company (admin only)

    Reactivates a previously deactivated company.
    """
    company_repo = company_service.company_repo
    success = await company_repo.activate(company_id)

    if success:
        return {"message": "Company activated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )


@router.get("/admin/stats/global", response_model=dict)
@rate_limit
async def get_global_company_stats(
        current_user: User = Depends(get_current_superuser),
        company_service: CompanyService = Depends(get_company_service),
) -> dict:
    """
    Get global company statistics (admin only)

    Returns overall platform statistics about companies.
    """
    company_repo = company_service.company_repo
    stats = await company_repo.get_stats()

    return {
        "company_stats": stats,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def company_service_health_check() -> dict:
    """Health check endpoint for company service."""
    return {
        "status": "healthy",
        "service": "companies",
        "timestamp": datetime.now().isoformat()
    }
