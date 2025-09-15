from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.core.exceptions.exceptions import ConflictError
from app.schemas.application import ApplicationCreate, ApplicationResponse, Application, ApplicationUpdate
from app.models.application import ApplicationModel


class ApplicationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_application(
            self,
            application_create: ApplicationCreate,
            applicant_id: UUID,
            recruiter_id: Optional[UUID],
            company_id: UUID) -> ApplicationModel:
        existing = self.db.execute(
            select(ApplicationModel).where(
                ApplicationModel.user_id == applicant_id,
                ApplicationModel.job_id == application_create.job_id
            )
        )

        if existing.scalar_one_or_none():
            raise ConflictError("Application already exists for this applicant and job")

        app = ApplicationModel(
            user_id=applicant_id,
            recruiter_id=recruiter_id,
            company_id=company_id,
            job_id=application_create.job_id,
            cover_letter=application_create.cover_letter,
            source=application_create.source,
            additional_data=application_create.additional_data,
        )

        self.db.add(app)
        await self.db.flush()
        return app


async def update_application(
        self,
        application_id: UUID,
        payload: ApplicationUpdate,
) -> Optional[ApplicationModel]:
    app = await self.get_application_by_id(application_id)
    if not app:
        return None

    if payload.status is not None:
        app.status = payload.status
    if payload.recruiter_notes is not None:
        app.recruiter_notes = payload.recruiter_notes
    if payload.interview_scheduled_at is not None:
        app.interview_scheduled_at = payload.interview_scheduled_at
    if payload.rejection_reason is not None:
        app.rejection_reason = payload.rejection_reason
    if payload.offer_details is not None:
        app.offer_details = payload.offer_details

    await self.db.flush()
    return app


async def get_application_by_id(self, application_id: UUID) -> Optional[ApplicationModel]:
    """Получить заявку по ID"""
    result = await self.db.execute(
        select(ApplicationModel).where(ApplicationModel.id == application_id)
    )

    return result.scalar_one_or_none()


async def get_all_applications_for_job(self, job_id: UUID) -> List[ApplicationModel]:
    query = select(Application).where(Application.job_id == job_id)
    result = await self.db.execute(
        select(ApplicationModel).where(ApplicationModel.job_id == job_id).order_by(ApplicationModel.applied_at.desc())
    )
    return result.scalars().all()


async def delete_application(self, application_id: UUID) -> bool:
    app = await self.get_application_by_id(application_id)
    if not app:
        return None
    await self.db.delete(app)
    await self.db.flush()
    return True