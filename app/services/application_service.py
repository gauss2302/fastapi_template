import errno
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from starlette import status

from app.repositories.application_repository import ApplicationRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.recruiter_repository import RecruiterRepository
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate


class ApplicationService:
    def __init__(
        self,
        application_repo: ApplicationRepository,
        recruiter_repo: RecruiterRepository,
        company_repo: CompanyRepository,
    ):
        self.application_repo = application_repo
        self.recruiter_repo = recruiter_repo
        self.company_repo = company_repo

    async def create_application(
        self,
        application_create: ApplicationCreate,
        applicant_id: UUID,
        recruiter_id: Optional[UUID],
        company_id: UUID,
    ) -> ApplicationResponse:
        app = await self.application_repo.create_application(
            application_create=application_create,
            applicant_id=applicant_id,
            recruiter_id=recruiter_id,
            company_id=company_id,
        )
        # Pydantic v2: Config.from_attributes=True в ApplicationResponse
        return ApplicationResponse.model_validate(app)

    async def get_application_by_id(self, application_id: UUID) -> ApplicationResponse:
        result = await self.application_repo.get_application_by_id(application_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return ApplicationResponse.model_validate(result)


    async def update_application(self, application_id: UUID, payload: ApplicationUpdate) -> ApplicationResponse:
        result = await self.application_repo.update_application(application_id, payload)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
        return ApplicationResponse.model_validate(result)
