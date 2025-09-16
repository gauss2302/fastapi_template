from uuid import UUID
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions.exceptions import ConflictError, NotFoundError
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.models.application import Application as ApplicationModel  # ORM-класс

class ApplicationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_application_by_id(self, application_id: UUID) -> Optional[ApplicationModel]:
        result = await self.db.execute(
            select(ApplicationModel).where(ApplicationModel.id == application_id)
        )
        return result.scalar_one_or_none()

    async def get_all_applications_for_job(self, job_id: UUID) -> List[ApplicationModel]:
        result = await self.db.execute(
            select(ApplicationModel)
            .where(ApplicationModel.job_id == job_id)
            .order_by(ApplicationModel.applied_at.desc())
        )
        return result.scalars().all()
    
    async def get_all_applications_by_userID(self, user_id: UUID) -> List[ApplicationModel]:
        result = await self.db.execute(
            select(ApplicationModel).where(ApplicationModel.user_id == user_id)
        )
        apps = result.scalars().all()
        if not apps:
            raise NotFoundError(f"No applications found for user {user_id}")
        
        return apps
        

    async def create_application(
        self,
        application_create: ApplicationCreate,
        applicant_id: UUID,
        recruiter_id: Optional[UUID],
        company_id: UUID,
    ) -> ApplicationModel:
        # проверка уникальности (пример)
        existing = await self.db.execute(
            select(ApplicationModel).where(
                ApplicationModel.user_id == applicant_id,
                ApplicationModel.job_id == application_create.job_id,
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
        await self.db.flush()  # получим id до commit из DI
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

    async def delete_application(self, application_id: UUID) -> bool:
        app = await self.get_application_by_id(application_id)
        if not app:
            return False
        await self.db.delete(app)
        await self.db.flush()
        return True
    
    async def get_all_applications_of_recruiter(self, recruiter_id: UUID) -> List[ApplicationModel]:
        result = await self.db.execute(
            select(ApplicationModel).where(ApplicationModel.recruiter_id == recruiter_id)
        )
        
        apps = result.scalars().all()
        if not apps:
            raise NotFoundError(f"No applicaitons found for recruiter {recruiter_id}")
        
        return apps