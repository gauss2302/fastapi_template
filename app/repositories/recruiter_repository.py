# app/repositories/recruiter_repository.py - Only recruiter-related operations
from datetime import datetime, timedelta
from sqlalchemy import and_, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError
from app.models.company import Company, CompanyStatus
from app.models.recruiter import Recruiter, RecruiterStatus
from app.schemas.recruiter import (
    RecruiterCreate, RecruiterUpdate, RecruiterApproval, RecruiterPermissions
)


class RecruiterRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, recruiter_data: RecruiterCreate, user_id: UUID) -> Recruiter:
        """Create a new recruiter profile"""
        # Check if user already has a recruiter profile
        existing_recruiter = await self.get_by_user_id(user_id)
        if existing_recruiter:
            raise ConflictError("User already has a recruiter profile")

        # Verify company exists and is verified
        company_result = await self.db.execute(
            select(Company).where(
                and_(
                    Company.id == recruiter_data.company_id,
                    Company.is_active == True,
                    Company.status == CompanyStatus.VERIFIED
                )
            )
        )
        company = company_result.scalar_one_or_none()
        if not company:
            raise NotFoundError("Company not found or not verified")

        recruiter_dict = recruiter_data.model_dump()
        recruiter_dict['user_id'] = user_id

        db_recruiter = Recruiter(**recruiter_dict)
        self.db.add(db_recruiter)
        await self.db.flush()
        await self.db.refresh(db_recruiter)

        return db_recruiter

    async def get_by_id(self, recruiter_id: UUID) -> Optional[Recruiter]:
        """Get recruiter by ID"""
        result = await self.db.execute(
            select(Recruiter).where(Recruiter.id == recruiter_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(self, recruiter_id: UUID) -> Optional[Recruiter]:
        """Get recruiter by ID with user and company loaded"""
        result = await self.db.execute(
            select(Recruiter)
            .options(
                selectinload(Recruiter.user),
                selectinload(Recruiter.company)
            )
            .where(Recruiter.id == recruiter_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> Optional[Recruiter]:
        """Get recruiter by user ID"""
        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.company))
            .where(Recruiter.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id_with_relations(self, user_id: UUID) -> Optional[Recruiter]:
        """Get recruiter by user ID with all relations loaded"""
        result = await self.db.execute(
            select(Recruiter)
            .options(
                selectinload(Recruiter.user),
                selectinload(Recruiter.company)
            )
            .where(Recruiter.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_company_recruiters(
            self,
            company_id: UUID,
            status: Optional[RecruiterStatus] = None,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Recruiter], int]:
        """Get recruiters for a company"""
        query = (
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(Recruiter.company_id == company_id)
        )

        if status:
            query = query.where(Recruiter.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Get paginated results
        query = query.order_by(Recruiter.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        recruiters = result.scalars().all()

        return list(recruiters), total

    async def get_company_admins(self, company_id: UUID) -> List[Recruiter]:
        """Get all company administrators"""
        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.can_manage_company == True,
                    Recruiter.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    async def get_recruiters_with_approval_rights(self, company_id: UUID) -> List[Recruiter]:
        """Get recruiters who can approve other recruiters"""
        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.can_approve_recruiters == True,
                    Recruiter.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    async def update(self, recruiter_id: UUID, recruiter_data: RecruiterUpdate) -> Recruiter:
        """Update recruiter profile"""
        recruiter = await self.get_by_id(recruiter_id)
        if not recruiter:
            raise NotFoundError("Recruiter not found")

        update_data = recruiter_data.model_dump(exclude_unset=True)
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = (
                update(Recruiter)
                .where(Recruiter.id == recruiter_id)
                .values(**update_data)
            )
            await self.db.execute(stmt)
            await self.db.refresh(recruiter)

        return recruiter

    async def approve_or_reject(
            self,
            recruiter_id: UUID,
            approval_data: RecruiterApproval,
            approved_by_recruiter_id: UUID
    ) -> Recruiter:
        """Approve or reject recruiter"""
        recruiter = await self.get_by_id(recruiter_id)
        if not recruiter:
            raise NotFoundError("Recruiter not found")

        update_data = {
            "status": approval_data.status,
            "updated_at": datetime.utcnow()
        }

        if approval_data.status == RecruiterStatus.APPROVED:
            update_data["approved_by"] = approved_by_recruiter_id
            update_data["approved_at"] = datetime.utcnow()
            update_data["rejection_reason"] = None  # Clear any previous rejection reason
        elif approval_data.status == RecruiterStatus.REJECTED:
            update_data["rejection_reason"] = approval_data.rejection_reason
            update_data["approved_by"] = None
            update_data["approved_at"] = None

        stmt = (
            update(Recruiter)
            .where(Recruiter.id == recruiter_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        await self.db.refresh(recruiter)

        return recruiter

    async def update_permissions(
            self,
            recruiter_id: UUID,
            permissions: RecruiterPermissions
    ) -> Recruiter:
        """Update recruiter permissions"""
        recruiter = await self.get_by_id(recruiter_id)
        if not recruiter:
            raise NotFoundError("Recruiter not found")

        update_data = permissions.model_dump()
        update_data["updated_at"] = datetime.utcnow()

        stmt = (
            update(Recruiter)
            .where(Recruiter.id == recruiter_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        await self.db.refresh(recruiter)

        return recruiter

    async def update_last_activity(self, recruiter_id: UUID) -> None:
        """Update recruiter's last activity timestamp"""
        stmt = (
            update(Recruiter)
            .where(Recruiter.id == recruiter_id)
            .values(last_activity_at=datetime.utcnow())
        )
        await self.db.execute(stmt)

    async def update_last_activity_by_user_id(self, user_id: UUID) -> None:
        """Update recruiter's last activity by user ID"""
        stmt = (
            update(Recruiter)
            .where(Recruiter.user_id == user_id)
            .values(last_activity_at=datetime.utcnow())
        )
        await self.db.execute(stmt)

    async def can_approve_recruiters(self, recruiter_id: UUID, company_id: UUID) -> bool:
        """Check if recruiter can approve other recruiters in the company"""
        result = await self.db.execute(
            select(Recruiter).where(
                and_(
                    Recruiter.id == recruiter_id,
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.can_approve_recruiters == True,
                    Recruiter.is_active == True
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def can_manage_company(self, recruiter_id: UUID, company_id: UUID) -> bool:
        """Check if recruiter can manage company"""
        result = await self.db.execute(
            select(Recruiter).where(
                and_(
                    Recruiter.id == recruiter_id,
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.can_manage_company == True,
                    Recruiter.is_active == True
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def has_company_access(self, user_id: UUID, company_id: UUID) -> bool:
        """Check if user has access to company as recruiter"""
        result = await self.db.execute(
            select(Recruiter).where(
                and_(
                    Recruiter.user_id == user_id,
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.is_active == True
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def deactivate(self, recruiter_id: UUID) -> bool:
        """Deactivate recruiter"""
        recruiter = await self.get_by_id(recruiter_id)
        if not recruiter:
            return False

        stmt = (
            update(Recruiter)
            .where(Recruiter.id == recruiter_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await self.db.execute(stmt)
        return True

    async def activate(self, recruiter_id: UUID) -> bool:
        """Activate recruiter"""
        recruiter = await self.get_by_id(recruiter_id)
        if not recruiter:
            return False

        stmt = (
            update(Recruiter)
            .where(Recruiter.id == recruiter_id)
            .values(is_active=True, updated_at=datetime.utcnow())
        )
        await self.db.execute(stmt)
        return True

    async def deactivate_company_recruiters(self, company_id: UUID) -> int:
        """Deactivate all recruiters for a company"""
        stmt = (
            update(Recruiter)
            .where(Recruiter.company_id == company_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        return result.rowcount

    async def get_company_stats(self, company_id: UUID) -> Dict[str, Any]:
        """Get recruiter statistics for a company"""
        result = await self.db.execute(
            select(
                func.count(Recruiter.id).label('total'),
                func.count().filter(Recruiter.status == RecruiterStatus.APPROVED).label('approved'),
                func.count().filter(Recruiter.status == RecruiterStatus.PENDING).label('pending'),
                func.count().filter(Recruiter.status == RecruiterStatus.REJECTED).label('rejected'),
                func.count().filter(
                    and_(
                        Recruiter.is_active == True,
                        Recruiter.status == RecruiterStatus.APPROVED
                    )
                ).label('active')
            )
            .where(Recruiter.company_id == company_id)
        )
        stats = result.first()

        return {
            "total_recruiters": stats.total or 0,
            "approved_recruiters": stats.approved or 0,
            "pending_recruiters": stats.pending or 0,
            "rejected_recruiters": stats.rejected or 0,
            "active_recruiters": stats.active or 0,
        }

    async def get_global_stats(self) -> Dict[str, Any]:
        """Get global recruiter statistics"""
        result = await self.db.execute(
            select(
                func.count(Recruiter.id).label('total'),
                func.count().filter(Recruiter.status == RecruiterStatus.APPROVED).label('approved'),
                func.count().filter(Recruiter.status == RecruiterStatus.PENDING).label('pending'),
                func.count().filter(Recruiter.is_active == True).label('active'),
                func.count().filter(Recruiter.can_manage_company == True).label('admins')
            )
        )
        stats = result.first()

        return {
            "total_recruiters": stats.total or 0,
            "approved_recruiters": stats.approved or 0,
            "pending_recruiters": stats.pending or 0,
            "active_recruiters": stats.active or 0,
            "admin_recruiters": stats.admins or 0,
        }

    async def get_pending_recruiters(
            self,
            company_id: Optional[UUID] = None,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Recruiter], int]:
        """Get pending recruiter applications"""
        query = (
            select(Recruiter)
            .options(
                selectinload(Recruiter.user),
                selectinload(Recruiter.company)
            )
            .where(Recruiter.status == RecruiterStatus.PENDING)
        )

        if company_id:
            query = query.where(Recruiter.company_id == company_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Get paginated results
        query = query.order_by(Recruiter.created_at).offset(skip).limit(limit)
        result = await self.db.execute(query)
        recruiters = result.scalars().all()

        return list(recruiters), total

    async def get_recent_activity(
            self,
            company_id: UUID,
            days: int = 30,
            limit: int = 50
    ) -> List[Recruiter]:
        """Get recruiters with recent activity"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.is_active == True,
                    or_(
                        Recruiter.last_activity_at >= cutoff_date,
                        Recruiter.last_activity_at.is_(None)  # Include those with no activity yet
                    )
                )
            )
            .order_by(Recruiter.last_activity_at.desc().nullslast())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def get_inactive_recruiters(
            self,
            company_id: UUID,
            inactive_days: int = 30,
            limit: int = 50
    ) -> List[Recruiter]:
        """Get recruiters who have been inactive"""
        cutoff_date = datetime.utcnow() - timedelta(days=inactive_days)

        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.is_active == True,
                    or_(
                        Recruiter.last_activity_at < cutoff_date,
                        Recruiter.last_activity_at.is_(None)
                    )
                )
            )
            .order_by(Recruiter.last_activity_at.asc().nullsfirst())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def search_recruiters(
            self,
            company_id: Optional[UUID] = None,
            search_term: Optional[str] = None,
            status: Optional[RecruiterStatus] = None,
            department: Optional[str] = None,
            has_permissions: Optional[List[str]] = None,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Recruiter], int]:
        """Search recruiters with various filters"""
        query = (
            select(Recruiter)
            .options(
                selectinload(Recruiter.user),
                selectinload(Recruiter.company)
            )
        )

        # Apply filters
        filters = []

        if company_id:
            filters.append(Recruiter.company_id == company_id)

        if status:
            filters.append(Recruiter.status == status)

        if department:
            filters.append(Recruiter.department.ilike(f"%{department}%"))

        if search_term:
            # Search in user name, email, position, or bio
            search_filter = or_(
                Recruiter.position.ilike(f"%{search_term}%"),
                Recruiter.bio.ilike(f"%{search_term}%"),
                Recruiter.contact_email.ilike(f"%{search_term}%")
            )
            filters.append(search_filter)

        if has_permissions:
            permission_filters = []
            for permission in has_permissions:
                if permission == "approve_recruiters":
                    permission_filters.append(Recruiter.can_approve_recruiters == True)
                elif permission == "post_jobs":
                    permission_filters.append(Recruiter.can_post_jobs == True)
                elif permission == "view_analytics":
                    permission_filters.append(Recruiter.can_view_analytics == True)
                elif permission == "manage_company":
                    permission_filters.append(Recruiter.can_manage_company == True)

            if permission_filters:
                filters.append(and_(*permission_filters))

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Get paginated results
        query = query.order_by(Recruiter.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        recruiters = result.scalars().all()

        return list(recruiters), total

    async def bulk_update_status(
            self,
            recruiter_ids: List[UUID],
            status: RecruiterStatus,
            approved_by_recruiter_id: Optional[UUID] = None
    ) -> int:
        """Bulk update recruiter status"""
        if not recruiter_ids:
            return 0

        update_data = {
            "status": status,
            "updated_at": datetime.utcnow()
        }

        if status == RecruiterStatus.APPROVED and approved_by_recruiter_id:
            update_data["approved_by"] = approved_by_recruiter_id
            update_data["approved_at"] = datetime.utcnow()

        stmt = (
            update(Recruiter)
            .where(Recruiter.id.in_(recruiter_ids))
            .values(**update_data)
        )

        result = await self.db.execute(stmt)
        return result.rowcount

    async def bulk_update_permissions(
            self,
            recruiter_ids: List[UUID],
            permissions: RecruiterPermissions
    ) -> int:
        """Bulk update recruiter permissions"""
        if not recruiter_ids:
            return 0

        update_data = permissions.model_dump()
        update_data["updated_at"] = datetime.utcnow()

        stmt = (
            update(Recruiter)
            .where(Recruiter.id.in_(recruiter_ids))
            .values(**update_data)
        )

        result = await self.db.execute(stmt)
        return result.rowcount

    async def get_recruiters_by_permission(
            self,
            company_id: UUID,
            permission: str,
            active_only: bool = True
    ) -> List[Recruiter]:
        """Get recruiters with specific permission"""
        filters = [
            Recruiter.company_id == company_id,
            Recruiter.status == RecruiterStatus.APPROVED
        ]

        if active_only:
            filters.append(Recruiter.is_active == True)

        # Add permission filter
        if permission == "approve_recruiters":
            filters.append(Recruiter.can_approve_recruiters == True)
        elif permission == "post_jobs":
            filters.append(Recruiter.can_post_jobs == True)
        elif permission == "view_analytics":
            filters.append(Recruiter.can_view_analytics == True)
        elif permission == "manage_company":
            filters.append(Recruiter.can_manage_company == True)
        else:
            return []

        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(and_(*filters))
            .order_by(Recruiter.created_at)
        )

        return list(result.scalars().all())

    async def transfer_recruiter_approvals(
            self,
            from_recruiter_id: UUID,
            to_recruiter_id: UUID
    ) -> int:
        """Transfer approvals from one recruiter to another (when recruiter leaves)"""
        stmt = (
            update(Recruiter)
            .where(Recruiter.approved_by == from_recruiter_id)
            .values(
                approved_by=to_recruiter_id,
                updated_at=datetime.utcnow()
            )
        )

        result = await self.db.execute(stmt)
        return result.rowcount

    async def get_approval_history(
            self,
            company_id: UUID,
            limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get approval history for a company"""
        result = await self.db.execute(
            select(
                Recruiter.id,
                Recruiter.status,
                Recruiter.approved_at,
                Recruiter.rejection_reason,
                Recruiter.user_id,
                Recruiter.approved_by
            )
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status.in_([RecruiterStatus.APPROVED, RecruiterStatus.REJECTED])
                )
            )
            .order_by(Recruiter.approved_at.desc().nullslast())
            .limit(limit)
        )

        history = []
        for row in result:
            history.append({
                "recruiter_id": row.id,
                "user_id": row.user_id,
                "status": row.status,
                "approved_at": row.approved_at,
                "approved_by": row.approved_by,
                "rejection_reason": row.rejection_reason
            })

        return history

    async def get_department_stats(self, company_id: UUID) -> Dict[str, int]:
        """Get recruiter count by department"""
        result = await self.db.execute(
            select(
                Recruiter.department,
                func.count(Recruiter.id).label('count')
            )
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.is_active == True,
                    Recruiter.department.isnot(None)
                )
            )
            .group_by(Recruiter.department)
            .order_by(func.count(Recruiter.id).desc())
        )

        return {row.department: row.count for row in result}

    async def check_recruiter_exists_for_user(self, user_id: UUID) -> bool:
        """Check if user already has a recruiter profile"""
        result = await self.db.execute(
            select(Recruiter.id).where(Recruiter.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None

    async def get_company_first_recruiter(self, company_id: UUID) -> Optional[Recruiter]:
        """Get the first recruiter (founder) of a company"""
        result = await self.db.execute(
            select(Recruiter)
            .options(selectinload(Recruiter.user))
            .where(Recruiter.company_id == company_id)
            .order_by(Recruiter.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_active_recruiters_by_company(self, company_id: UUID) -> int:
        """Count active recruiters for a company"""
        result = await self.db.execute(
            select(func.count(Recruiter.id))
            .where(
                and_(
                    Recruiter.company_id == company_id,
                    Recruiter.status == RecruiterStatus.APPROVED,
                    Recruiter.is_active == True
                )
            )
        )
        return result.scalar() or 0