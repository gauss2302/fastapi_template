from typing import Optional, Dict, Any, List

from app.repositories.company_repository import CompanyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.recruiter_repository import RecruiterRepository
from app.schemas.job_schema import JobPostingCreate, JobPostingResponse, JobStatus, JobStatusUpdate, JobSearchRequest, \
    JobPostingListItem
from app.models.recruiter import RecruiterStatus
from app.core.exceptions.exceptions import AuthorizationError, NotFoundError, ValidationError

from uuid import UUID


class JobService:
    def __init__(
            self,
            job_repo: JobRepository,
            company_repo: CompanyRepository,
            recruiter_repo: RecruiterRepository
    ):
        self.job_repo = job_repo
        self.company_repo = company_repo
        self.recruiter_repo = recruiter_repo

    # ============================================================================
    # JOB CREATION AND MANAGEMENT (RECRUITER ONLY)
    # ============================================================================

    async def create_job_posting(self, job_data: JobPostingCreate, created_by_user_id: UUID) -> JobPostingResponse:
        recruiter = await self.recruiter_repo.get_by_user_id(created_by_user_id)
        if not recruiter:
            raise AuthorizationError("Only recruiters can create job postings")

        if recruiter.status != RecruiterStatus.APPROVED or not recruiter.can_post_jobs:
            raise AuthorizationError("Insufficient permissions to post jobs")

        company = await self.company_repo.get_by_id(recruiter.company_id)
        if not company:
            raise NotFoundError("Company not found")

        job_data.company_name = company.name

        db_job = await self.job_repo.create(job_data)

        await self.recruiter_repo.update(recruiter.id)

        return JobPostingResponse.model_validate(db_job)

    async def update_job_posting(self, job_id: UUID, job_data: JobPostingCreate,
                                 updated_by_user_id: UUID) -> JobPostingResponse:
        db_job = await self.job_repo.get_by_id(job_id)
        if not db_job:
            raise NotFoundError("Job posting not found")

        await self._verify_job_update_permission(job_id, updated_by_user_id)

        updated_job = await self.job_repo.update(job_id, job_data)

        recruiter = await self.recruiter_repo.get_by_user_id(updated_by_user_id)
        if recruiter:
            await self.recruiter_repo.update_last_activity(recruiter.id)

        return JobPostingResponse.model_validate(updated_job)

    async def publish_job_posting(self, job_id: UUID, published_by_user_id: UUID) -> JobPostingResponse:
        await self._verify_job_update_permission(job_id, published_by_user_id)

        published_job = await self.job_repo.update_status(job_id, JobStatus.ACTIVE, "Published by Recruiter")
        return JobPostingResponse.model_validate(published_job)

    async def update_job_status(self, job_id: UUID, status_update: JobStatusUpdate,
                                updated_by_user_id: UUID) -> JobPostingResponse:
        await self._verify_job_update_permission(job_id, updated_by_user_id)

        updated_job = await self.job_repo.update_status(job_id, status_update.status, status_update.reason)

        return JobPostingResponse.model_validate(updated_job)

    async def delete_job_posting(self, job_id: UUID, deleted_by_user_id: UUID) -> bool:
        await self._verify_job_update_permission(job_id, deleted_by_user_id)
        return await self.job_repo.soft_delete(job_id)

    # ============================================================================
    # JOB VIEWING AND SEARCH (PUBLIC)
    # ============================================================================

    async def get_job_by_id(self, job_id: UUID, viewer_user_id: Optional[UUID]) -> Optional[JobPostingResponse]:
        db_job = await self.job_repo.get_by_id(job_id)
        if not db_job:
            return None

        if not viewer_user_id or not await self._is_recruiter_for_job(job_id, viewer_user_id):
            if db_job.status != JobStatus.ACTIVE.value:
                return None

        if db_job.status == JobStatus.ACTIVE.value and viewer_user_id:
            await self.job_repo.increment_views(job_id)

        return JobPostingResponse.model_validate(job_id)

    async def get_job_by_slug(self, slug: str, viewer_user_id: Optional[UUID] = None) -> Optional[JobPostingResponse]:
        db_job = await self.job_repo.get_by_slug(slug)
        if not db_job:
            return None

        if not viewer_user_id or not await self._is_recruiter_for_job(db_job.id, viewer_user_id):
            if db_job.status != JobStatus.ACTIVE.value:
                return None

        if db_job.status == JobStatus.ACTIVE.value and viewer_user_id:
            await self.job_repo.increment_views(db_job.id)

        return JobPostingResponse.model_validate(db_job)

    async def search_jobs(
            self,
            search_params: JobSearchRequest,
            viewer_user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Search jobs with filters"""
        # Public search only shows active jobs
        if not viewer_user_id or not await self._user_is_recruiter(viewer_user_id):
            # Force status to ACTIVE for public searches
            search_params.query = search_params.query or ""

        results = await self.job_repo.search(search_params)

        # Convert jobs to list items
        job_items = [
            JobPostingListItem.model_validate(job)
            for job in results['jobs']
        ]

        return {
            'jobs': job_items,
            'total': results['total'],
            'page': results['page'],
            'limit': results['limit'],
            'pages': results['pages'],
            'has_next': results['has_next'],
            'has_prev': results['has_prev']
        }

    async def get_company_jobs(
            self,
            company_name: str,
            status: Optional[JobStatus] = None,
            viewer_user_id: Optional[UUID] = None
    ) -> List[JobPostingListItem]:
        if not viewer_user_id or not await self._user_is_recruiter(viewer_user_id):
            status = JobStatus.ACTIVE

        db_jobs = await self.job_repo.get_company_jobs(company_name, status)
        return [JobPostingListItem.model_validate(job) for job in db_jobs]

    # ============================================================================
    # JOB APPLICATIONS (USER ACTIONS)
    # ============================================================================

    async def apply_to_job(
            self,
            job_id: UUID,
            applicant_user_id: UUID,
            application_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:

        db_job = await self.job_repo.get_by_id(job_id)

        if not db_job:
            raise NotFoundError("Job not found")

        if db_job.status != JobStatus.ACTIVE.value:
            raise ValidationError("Job posting is not accepting applications")

        await self.job_repo.increment_applications(job_id)

        # TODO: Store application in applications table
        # TODO: Send notification to recruiter
        # TODO: Send confirmation email to applicant

        return {
            "message": "Application submitted successfully",
            "job_title": db_job.title,
            "company_name": db_job.company_name
        }

    # PERMISSION HELPERS

    async def _verify_job_update_permission(self, job_id: UUID, user_id: UUID) -> None:
        db_job = await self.job_repo.get_by_id(job_id)
        if not db_job:
            raise NotFoundError("Job Posting Not Found")

        recruiter = await self.recruiter_repo.get_by_user_id(user_id)
        if not recruiter:
            raise AuthorizationError("Only Recruiters can make job postings")

        company = await self.company_repo.get_by_name(db_job.company_name)
        if not company or company.id != recruiter.company_id:
            raise AuthorizationError("No permission to modify this job posting")

        if recruiter.status != RecruiterStatus.APPROVED:
            raise AuthorizationError("Recruiter account not approved")

    async def _is_recruiter_for_job(self, job_id: UUID, user_id: UUID) -> bool:
        """Check if user is recruiter for this job's company"""
        try:
            await self._verify_job_update_permission(job_id, user_id)
            return True
        except(AuthorizationError, NotFoundError):
            return False

    async def _user_is_recruiter(self, user_id: UUID) -> bool:
        """Check if user is a recruiter"""
        recruiter = await self.recruiter_repo.get_by_user_id(user_id)
        return recruiter is not None and recruiter.status == RecruiterStatus.APPROVED
