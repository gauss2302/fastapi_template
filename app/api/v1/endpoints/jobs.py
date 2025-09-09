from typing import Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.exceptions import AuthorizationError, NotFoundError
from app.middleware.rate_limiter import strict_rate_limit, api_rate_limit, rate_limit
from app.schemas.job_schema import JobPostingResponse, JobPostingCreate, JobPostingUpdate, JobSearchResponse, \
    JobSearchRequest, CompanyJobsResponse, JobStatus
from app.models.user import User
from app.core.dependencies import get_current_user, get_job_service
from app.services.job_service import JobService

router = APIRouter()


# ============================================================================
# PUBLIC JOB ENDPOINTS (No authentication required)
# ============================================================================


@router.get("/search", response_model=JobSearchResponse)
@rate_limit
async def search_jobs_public(
        query: Optional[str] = Query(None, description="Search in title and description"),
        level: Optional[str] = Query(None, description="Job level filter"),
        type: Optional[str] = Query(None, description="Job type filter"),
        working_type: Optional[str] = Query(None, description="Working type filter"),
        salary_min: Optional[int] = Query(None, ge=0, description="Minimum salary"),
        remote_only: Optional[bool] = Query(None, description="Only remote jobs"),
        location_allowed: Optional[str] = Query(None, description="Must allow this location"),
        page: int = Query(1, ge=1, description="Page number"),
        limit: int = Query(20, ge=1, le=100, description="Items per page"),
        job_service: JobService = Depends(get_job_service),
) -> JobSearchResponse:
    """
    Search jobs (public endpoint)

    This endpoint allows anyone to search for active job postings without authentication.
    Only published/active jobs are returned.
    """
    try:
        # Build search request
        search_params = JobSearchRequest(
            query=query,
            level=[level] if level else None,
            type=[type] if type else None,
            working_type=[working_type] if working_type else None,
            salary_min=salary_min,
            remote_only=remote_only,
            location_allowed=location_allowed,
            page=page,
            limit=limit
        )

        results = await job_service.search_jobs(search_params, viewer_user_id=None)

        return JobSearchResponse(
            jobs=results['jobs'],
            total=results['total'],
            page=results['page'],
            limit=results['limit'],
            pages=results['pages'],
            has_next=results['has_next'],
            has_prev=results['has_prev']
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/slug/{slug}", response_model=JobPostingResponse)
@rate_limit
async def get_job_by_slug_public(
        slug: str,
        job_service: JobService = Depends(get_job_service),
) -> JobPostingResponse:
    """
    Get job by slug (public endpoint)

    Returns job information that can be viewed by anyone.
    Only shows active jobs to non-authenticated users.
    """
    job = await job_service.get_job_by_slug(slug, viewer_user_id=None)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found"
        )

    return job


@router.get("/company/{company_name}", response_model=CompanyJobsResponse)
@rate_limit
async def get_company_jobs_public(
        company_name: str,
        job_service: JobService = Depends(get_job_service),
) -> CompanyJobsResponse:
    """Get all active jobs for a company (public endpoint)"""
    jobs = await job_service.get_company_jobs(
        company_name,
        status=JobStatus.ACTIVE,
        viewer_user_id=None
    )

    active_jobs = [job for job in jobs if job.status == JobStatus.ACTIVE]

    return CompanyJobsResponse(
        company_name=company_name,
        active_jobs=active_jobs,
        total_jobs=len(jobs),
        total_active=len(active_jobs)
    )



# ============================================================================
# AUTHENTICATED USER ENDPOINTS
# ============================================================================
@router.get("/{job_id}", response_model=JobPostingResponse)
@api_rate_limit
async def get_job_by_id(
        job_id: UUID,
        current_user: User = Depends(get_current_user),
        job_service: JobService = Depends(get_job_service),
) -> JobPostingResponse:
    """Get job by ID (authenticated users can see more details)"""
    job = await job_service.get_job_by_id(job_id, viewer_user_id=current_user.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found"
        )

    return job


@router.post("/{job_id}/apply")
@strict_rate_limit
async def apply_to_job(
        job_id: UUID,
        current_user: User = Depends(get_current_user),
        job_service: JobService = Depends(get_job_service),
) -> Dict[str, str]:
    """
    Apply to a job posting

    Users can apply to active job postings. This increments the application counter
    and will eventually store the application details.
    """
    try:
        result = await job_service.apply_to_job(job_id, current_user.id)
        return result
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "not accepting" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Application failed: {str(e)}"
        )


# ============================================================================
# RECRUITER-ONLY ENDPOINTS
# ============================================================================

@router.post("/", response_model=JobPostingResponse)
@strict_rate_limit
async def create_job_posting(
        job_data: JobPostingCreate,
        current_user: User = Depends(get_current_user),
        job_service: JobService = Depends(get_job_service),

) -> JobPostingResponse:
    """
       Create a new job posting (recruiter only)

       Only approved recruiters with job posting permissions can create new jobs.
       The job is created in DRAFT status by default.
       """
    try:
        job = await job_service.create_job_posting(job_data, current_user)
        return job
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{job_id}", response_model=JobPostingResponse)
@api_rate_limit
async def update_job_posting(
        job_id: UUID,
        job_data: JobPostingUpdate,
        current_user: User = Depends(get_current_user),
        job_service: JobService = Depends(get_job_service),

) -> JobPostingResponse:
    """Update job posting (recruiter only)"""
    try:
        job = await job_service.update_job_posting(job_id, job_data, current_user.id)
        return job
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
