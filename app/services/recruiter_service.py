from uuid import UUID

from app.models.recruiter import Recruiter
from app.repositories.company_repository import CompanyRepository
from app.repositories.recruiter_repository import RecruiterRepository
from app.schemas.recruiter import RecruiterCreate


class RecruiterService:
    def __init__(
            self,
            company_repo: CompanyRepository,
            recruiter_repo: RecruiterRepository
    ):
        self.recruiter_repo = recruiter_repo,
        self.company_repo = company_repo,


async def create_recruiter(self, recruiter: RecruiterCreate, recruiter_id: UUID) -> Recruiter:
    db_recruiter = await self.recruiter_repo.create_recruiter(recruiter, recruiter_id)
    return Recruiter.model_validate(db_recruiter)

async def get_recruiter_by_id(self, recruiter_id: UUID) -> Recruiter:
    db_recruiter = await self.recruiter_repo.get_recruiter_by_id(recruiter_id)