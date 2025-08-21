from datetime import datetime, timedelta
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple
from uuid import UUID
import re

from app.core.exceptions import ConflictError, NotFoundError
from app.models.company import Company, CompanyStatus
from app.schemas.company import (
    CompanyCreate, CompanyUpdate, CompanyVerification, CompanySearchFilters
)


class CompanyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _generate_slug(self, name: str) -> str:
        """Generate URL-friendly slug from company name"""
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')

    async def create(self, company_data: CompanyCreate) -> Company:
        """Create a new company"""
        # Check if company name already exists
        existing_company = await self.get_by_name(company_data.name)
        if existing_company:
            raise ConflictError(f"Company with name '{company_data.name}' already exists")

        # Generate unique slug
        base_slug = self._generate_slug(company_data.name)
        slug = base_slug
        counter = 1
        while await self.get_by_slug(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        company_dict = company_data.model_dump()
        company_dict['slug'] = slug

        db_company = Company(**company_dict)
        self.db.add(db_company)
        await self.db.flush()
        await self.db.refresh(db_company)

        return db_company

    async def get_by_id(self, company_id: UUID) -> Optional[Company]:
        """Get company by ID"""
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_recruiters(self, company_id: UUID) -> Optional[Company]:
        """Get company by ID with recruiters loaded"""
        result = await self.db.execute(
            select(Company)
            .options(selectinload(Company.recruiters))
            .where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Company]:
        """Get company by name (case-insensitive)"""
        result = await self.db.execute(
            select(Company).where(func.lower(Company.name) == name.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Company]:
        """Get company by slug"""
        result = await self.db.execute(
            select(Company).where(Company.slug == slug)
        )
        return result.scalar_one_or_none()

    async def update(self, company_id: UUID, company_data: CompanyUpdate) -> Company:
        """Update company information"""
        company = await self.get_by_id(company_id)
        if not company:
            raise NotFoundError("Company not found")

        # Check name uniqueness if name is being updated
        if company_data.name and company_data.name != company.name:
            existing_company = await self.get_by_name(company_data.name)
            if existing_company:
                raise ConflictError(f"Company with name '{company_data.name}' already exists")

            # Update slug if name changed
            new_slug = self._generate_slug(company_data.name)
            if new_slug != company.slug:
                counter = 1
                while await self.get_by_slug(new_slug):
                    new_slug = f"{self._generate_slug(company_data.name)}-{counter}"
                    counter += 1
                company.slug = new_slug

        update_data = company_data.model_dump(exclude_unset=True)
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = (
                update(Company)
                .where(Company.id == company_id)
                .values(**update_data)
            )
            await self.db.execute(stmt)
            await self.db.refresh(company)

        return company

    async def verify(
            self,
            company_id: UUID,
            verification_data: CompanyVerification,
            verified_by_user_id: UUID
    ) -> Company:
        """Verify or reject company"""
        company = await self.get_by_id(company_id)
        if not company:
            raise NotFoundError("Company not found")

        update_data = {
            "status": verification_data.status,
            "verification_notes": verification_data.verification_notes,
            "verified_by": verified_by_user_id,
            "updated_at": datetime.utcnow()
        }

        if verification_data.status == CompanyStatus.VERIFIED:
            update_data["verified_at"] = datetime.utcnow()

        stmt = (
            update(Company)
            .where(Company.id == company_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        await self.db.refresh(company)

        return company

    async def search(
            self,
            filters: CompanySearchFilters,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Company], int]:
        """Search companies with filters"""
        query = select(Company).where(Company.is_active == True)

        # Apply filters
        if filters.industry:
            query = query.where(Company.industry.ilike(f"%{filters.industry}%"))

        if filters.company_size:
            query = query.where(Company.company_size == filters.company_size)

        if filters.location:
            query = query.where(Company.headquarters.ilike(f"%{filters.location}%"))

        if filters.is_hiring is not None:
            query = query.where(Company.is_hiring == filters.is_hiring)

        if filters.verified_only:
            query = query.where(Company.status == CompanyStatus.VERIFIED)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Get paginated results
        query = query.order_by(Company.name).offset(skip).limit(limit)
        result = await self.db.execute(query)
        companies = result.scalars().all()

        return list(companies), total

    async def get_by_status(
            self,
            status: CompanyStatus,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Company], int]:
        """Get companies by status"""
        query = select(Company).where(Company.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Get paginated results
        query = query.order_by(Company.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        companies = result.scalars().all()

        return list(companies), total

    async def deactivate(self, company_id: UUID) -> bool:
        """Deactivate company"""
        company = await self.get_by_id(company_id)
        if not company:
            return False

        stmt = (
            update(Company)
            .where(Company.id == company_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await self.db.execute(stmt)
        return True

    async def activate(self, company_id: UUID) -> bool:
        """Activate company"""
        company = await self.get_by_id(company_id)
        if not company:
            return False

        stmt = (
            update(Company)
            .where(Company.id == company_id)
            .values(is_active=True, updated_at=datetime.utcnow())
        )
        await self.db.execute(stmt)
        return True

    async def update_hiring_status(self, company_id: UUID, is_hiring: bool) -> bool:
        """Update company hiring status"""
        company = await self.get_by_id(company_id)
        if not company:
            return False

        stmt = (
            update(Company)
            .where(Company.id == company_id)
            .values(is_hiring=is_hiring, updated_at=datetime.utcnow())
        )
        await self.db.execute(stmt)
        return True

    async def get_company_industries(self) -> List[str]:
        """Get all unique industries from companies"""
        result = await self.db.execute(
            select(Company.industry)
            .where(
                Company.industry.isnot(None),
                Company.is_active == True,
                Company.status == CompanyStatus.VERIFIED
            )
            .distinct()
            .order_by(Company.industry)
        )
        industries = result.scalars().all()
        return [industry for industry in industries if industry]

    async def get_company_locations(self) -> List[str]:
        """Get all unique locations from companies"""
        result = await self.db.execute(
            select(Company.headquarters)
            .where(
                Company.headquarters.isnot(None),
                Company.is_active == True,
                Company.status == CompanyStatus.VERIFIED
            )
            .distinct()
            .order_by(Company.headquarters)
        )
        locations = result.scalars().all()
        return [location for location in locations if location]

    async def get_stats(self) -> dict:
        """Get company statistics"""
        result = await self.db.execute(
            select(
                func.count(Company.id).label('total'),
                func.count().filter(Company.status == CompanyStatus.VERIFIED).label('verified'),
                func.count().filter(Company.status == CompanyStatus.PENDING).label('pending'),
                func.count().filter(Company.is_active == True).label('active'),
                func.count().filter(Company.is_hiring == True).label('hiring')
            )
        )
        stats = result.first()

        return {
            "total_companies": stats.total or 0,
            "verified_companies": stats.verified or 0,
            "pending_companies": stats.pending or 0,
            "active_companies": stats.active or 0,
            "hiring_companies": stats.hiring or 0,
        }

    async def check_name_availability(self, name: str, exclude_company_id: Optional[UUID] = None) -> bool:
        """Check if company name is available"""
        query = select(Company).where(func.lower(Company.name) == name.lower())

        if exclude_company_id:
            query = query.where(Company.id != exclude_company_id)

        result = await self.db.execute(query)
        existing_company = result.scalar_one_or_none()

        return existing_company is None

    async def check_slug_availability(self, slug: str, exclude_company_id: Optional[UUID] = None) -> bool:
        """Check if company slug is available"""
        query = select(Company).where(Company.slug == slug)

        if exclude_company_id:
            query = query.where(Company.id != exclude_company_id)

        result = await self.db.execute(query)
        existing_company = result.scalar_one_or_none()

        return existing_company is None

    async def get_companies_needing_verification(self, limit: int = 50) -> List[Company]:
        """Get companies that need verification (pending for more than 24 hours)"""
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        result = await self.db.execute(
            select(Company)
            .where(
                Company.status == CompanyStatus.PENDING,
                Company.created_at <= cutoff_time
            )
            .order_by(Company.created_at)
            .limit(limit)
        )

        return list(result.scalars().all())

    async def bulk_update_status(self, company_ids: List[UUID], status: CompanyStatus) -> int:
        """Bulk update company status"""
        if not company_ids:
            return 0

        stmt = (
            update(Company)
            .where(Company.id.in_(company_ids))
            .values(status=status, updated_at=datetime.utcnow())
        )

        result = await self.db.execute(stmt)
        return result.rowcount