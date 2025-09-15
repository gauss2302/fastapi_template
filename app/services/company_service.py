from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID

from app.repositories.company_repository import CompanyRepository
from app.repositories.recruiter_repository import RecruiterRepository
from app.repositories.user_repository import UserRepository

from app.schemas.company import (
    Company, CompanyCreate, CompanyUpdate, CompanyVerification, CompanyStats,
    CompanySearchFilters, CompanyRegistrationRequest
)
from app.schemas.recruiter import (
    Recruiter, RecruiterCreate, RecruiterUpdate, RecruiterApproval, RecruiterPermissions,
    RecruiterInvitationRequest
)
from app.models.company import CompanyStatus
from app.models.recruiter import RecruiterStatus
from app.core.exceptions.exceptions import NotFoundError, ConflictError, AuthorizationError


class CompanyService:
    def __init__(
            self,
            company_repo: CompanyRepository,
            recruiter_repo: RecruiterRepository,
            user_repo: UserRepository
    ):
        self.company_repo = company_repo
        self.recruiter_repo = recruiter_repo
        self.user_repo = user_repo

    # Company management methods
    async def register_company(
            self,
            registration_data: CompanyRegistrationRequest,
            created_by_user_id: UUID
    ) -> Company:
        """Register a new company and create first recruiter"""
        # Create company
        company_data = CompanyCreate(**registration_data.model_dump(exclude={'terms_accepted'}))
        db_company = await self.company_repo.create(company_data)

        # Create recruiter profile for the user who registered the company
        recruiter_data = RecruiterCreate(
            company_id=db_company.id,
            position="Company Admin",
            department="Administration"
        )

        # First recruiter gets special permissions and auto-approval
        db_recruiter = await self.recruiter_repo.create(recruiter_data, created_by_user_id)

        # Auto-approve first recruiter with admin permissions
        approval_data = RecruiterApproval(status=RecruiterStatus.APPROVED)
        await self.recruiter_repo.approve_or_reject(
            db_recruiter.id,
            approval_data,
            db_recruiter.id  # Self-approval for first recruiter
        )

        # Grant admin permissions
        admin_permissions = RecruiterPermissions(
            can_approve_recruiters=True,
            can_post_jobs=True,
            can_view_analytics=True,
            can_manage_company=True
        )
        await self.recruiter_repo.update_permissions(db_recruiter.id, admin_permissions)

        # TODO: Send email notification to admins for company verification
        # await self.email_service.send_company_registration_notification(db_company)

        return Company.model_validate(db_company)

    async def get_company_by_id(self, company_id: UUID) -> Optional[Company]:
        """Get company by ID"""
        db_company = await self.company_repo.get_by_id(company_id)
        if db_company:
            return Company.model_validate(db_company)
        return None

    async def get_company_by_slug(self, slug: str) -> Optional[Company]:
        """Get company by slug"""
        db_company = await self.company_repo.get_by_slug(slug)
        if db_company:
            return Company.model_validate(db_company)
        return None

    async def update_company(
            self,
            company_id: UUID,
            company_data: CompanyUpdate,
            updated_by_user_id: UUID
    ) -> Company:
        """Update company information"""
        # Verify user has permission to update company
        await self.verify_company_management_permission(company_id, updated_by_user_id)

        db_company = await self.company_repo.update(company_id, company_data)
        return Company.model_validate(db_company)

    async def verify_company(
            self,
            company_id: UUID,
            verification_data: CompanyVerification,
            verified_by_user_id: UUID
    ) -> Company:
        """Verify or reject company (admin only)"""
        db_company = await self.company_repo.verify(
            company_id,
            verification_data,
            verified_by_user_id
        )

        # Send notification email
        if verification_data.status == CompanyStatus.VERIFIED:
            await self.email_service.send_company_verification_success(db_company)
        elif verification_data.status == CompanyStatus.REJECTED:
            await self.email_service.send_company_verification_rejection(
                db_company,
                verification_data.verification_notes
            )

        return Company.model_validate(db_company)

    async def search_companies(
            self,
            filters: CompanySearchFilters,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Company], int]:
        """Search companies with filters"""
        db_companies, total = await self.company_repo.search(filters, skip, limit)
        companies = [Company.model_validate(company) for company in db_companies]
        return companies, total

    async def get_companies_by_status(
            self,
            status: CompanyStatus,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Company], int]:
        """Get companies by status (admin only)"""
        db_companies, total = await self.company_repo.get_by_status(status, skip, limit)
        companies = [Company.model_validate(company) for company in db_companies]
        return companies, total

    async def get_company_stats(self, company_id: UUID, user_id: UUID) -> CompanyStats:
        """Get company statistics"""
        # Verify user has permission
        await self._verify_company_access_permission(company_id, user_id)

        # Get stats from both repositories
        company_stats = await self.company_repo.get_stats()
        recruiter_stats = await self.recruiter_repo.get_company_stats(company_id)

        # Combine stats
        combined_stats = {**company_stats, **recruiter_stats}
        return CompanyStats(**combined_stats)

    async def deactivate_company(self, company_id: UUID, deactivated_by_user_id: UUID) -> bool:
        """Deactivate company and all its recruiters"""
        # Verify user has permission
        await self.verify_company_management_permission(company_id, deactivated_by_user_id)

        # Deactivate company
        company_deactivated = await self.company_repo.deactivate(company_id)

        if company_deactivated:
            # Deactivate all recruiters
            await self.recruiter_repo.deactivate_company_recruiters(company_id)

        return company_deactivated

    async def get_company_industries(self) -> List[str]:
        """Get all unique industries"""
        return await self.company_repo.get_company_industries()

    async def get_company_locations(self) -> List[str]:
        """Get all unique locations"""
        return await self.company_repo.get_company_locations()

    # Recruiter management methods

    async def invite_recruiter(
            self,
            company_id: UUID,
            invitation_data: RecruiterInvitationRequest,
            invited_by_user_id: UUID
    ) -> dict:
        """Invite a recruiter to join company"""
        # Verify user has permission to invite recruiters
        await self._verify_recruiter_approval_permission(company_id, invited_by_user_id)

        # Check if user with this email exists
        user = await self.user_repo.get_by_email(invitation_data.email)

        if user:
            # User exists, check if they already have recruiter profile
            existing_recruiter = await self.recruiter_repo.get_by_user_id(user.id)
            if existing_recruiter:
                raise ConflictError("User already has a recruiter profile")

            # Create recruiter profile with PENDING status
            recruiter_data = RecruiterCreate(
                company_id=company_id,
                position=invitation_data.position
            )
            db_recruiter = await self.recruiter_repo.create(recruiter_data, user.id)

            # TODO: Send invitation email
            # await self.email_service.send_recruiter_invitation_existing_user(
            #     user, db_recruiter, invitation_data.personal_message
            # )

            return {"status": "invited", "recruiter_id": db_recruiter.id}
        else:
            # TODO: User doesn't exist, send signup invitation
            # await self.email_service.send_recruiter_invitation_new_user(
            #     invitation_data.email, company_id, invitation_data.personal_message
            # )

            return {"status": "signup_invitation_sent", "email": invitation_data.email}

    async def approve_recruiter(
            self,
            recruiter_id: UUID,
            approval_data: RecruiterApproval,
            approved_by_user_id: UUID
    ) -> Recruiter:
        """Approve or reject recruiter application"""
        # Get recruiter to verify company
        recruiter = await self.recruiter_repo.get_by_id(recruiter_id)
        if not recruiter:
            raise NotFoundError("Recruiter not found")

        # Verify user has permission to approve recruiters
        await self._verify_recruiter_approval_permission(recruiter.company_id, approved_by_user_id)

        # Get approver's recruiter profile
        approver_recruiter = await self.recruiter_repo.get_by_user_id(approved_by_user_id)
        if not approver_recruiter:
            raise AuthorizationError("Only recruiters can approve other recruiters")

        db_recruiter = await self.recruiter_repo.approve_or_reject(
            recruiter_id,
            approval_data,
            approver_recruiter.id
        )

        # TODO: Send notification email
        # if approval_data.status == RecruiterStatus.APPROVED:
        #     await self.email_service.send_recruiter_approval_success(db_recruiter)
        # elif approval_data.status == RecruiterStatus.REJECTED:
        #     await self.email_service.send_recruiter_approval_rejection(
        #         db_recruiter, approval_data.rejection_reason
        #     )

        return Recruiter.model_validate(db_recruiter)

    async def get_company_recruiters(
            self,
            company_id: UUID,
            requesting_user_id: UUID,
            status: Optional[RecruiterStatus] = None,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Recruiter], int]:
        """Get recruiters for a company"""
        # Verify user has access to company
        await self._verify_company_access_permission(company_id, requesting_user_id)

        db_recruiters, total = await self.recruiter_repo.get_company_recruiters(
            company_id, status, skip, limit
        )
        recruiters = [Recruiter.model_validate(recruiter) for recruiter in db_recruiters]
        return recruiters, total

    async def update_recruiter_profile(
            self,
            recruiter_id: UUID,
            recruiter_data: RecruiterUpdate,
            updated_by_user_id: UUID
    ) -> Recruiter:
        """Update recruiter profile"""
        # Get recruiter to verify ownership or company access
        recruiter = await self.recruiter_repo.get_by_id(recruiter_id)
        if not recruiter:
            raise NotFoundError("Recruiter not found")

        # Check if user owns this profile or has company management permission
        if recruiter.user_id != updated_by_user_id:
            await self.verify_company_management_permission(recruiter.company_id, updated_by_user_id)

        db_recruiter = await self.recruiter_repo.update(recruiter_id, recruiter_data)
        return Recruiter.model_validate(db_recruiter)

    async def update_recruiter_permissions(
            self,
            recruiter_id: UUID,
            permissions: RecruiterPermissions,
            updated_by_user_id: UUID
    ) -> Recruiter:
        """Update recruiter permissions (company admin only)"""
        # Get recruiter to verify company
        recruiter = await self.recruiter_repo.get_by_id(recruiter_id)
        if not recruiter:
            raise NotFoundError("Recruiter not found")

        # Verify user has company management permission
        await self.verify_company_management_permission(recruiter.company_id, updated_by_user_id)

        db_recruiter = await self.recruiter_repo.update_permissions(recruiter_id, permissions)
        return Recruiter.model_validate(db_recruiter)

    async def get_recruiter_by_user_id(self, user_id: UUID) -> Optional[Recruiter]:
        """Get recruiter profile by user ID"""
        db_recruiter = await self.recruiter_repo.get_by_user_id(user_id)
        if db_recruiter:
            return Recruiter.model_validate(db_recruiter)
        return None

    async def deactivate_recruiter(
            self,
            recruiter_id: UUID,
            deactivated_by_user_id: UUID
    ) -> bool:
        """Deactivate recruiter"""
        # Get recruiter to verify company
        recruiter = await self.recruiter_repo.get_by_id(recruiter_id)
        if not recruiter:
            return False

        # Check if user owns this profile or has company management permission
        if recruiter.user_id != deactivated_by_user_id:
            await self.verify_company_management_permission(recruiter.company_id, deactivated_by_user_id)

        return await self.recruiter_repo.deactivate(recruiter_id)

    async def search_recruiters(
            self,
            requesting_user_id: UUID,
            company_id: Optional[UUID] = None,
            search_term: Optional[str] = None,
            status: Optional[RecruiterStatus] = None,
            department: Optional[str] = None,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Recruiter], int]:
        """Search recruiters with filters"""
        # If company_id is specified, verify access
        if company_id:
            await self._verify_company_access_permission(company_id, requesting_user_id)

        db_recruiters, total = await self.recruiter_repo.search_recruiters(
            company_id=company_id,
            search_term=search_term,
            status=status,
            department=department,
            skip=skip,
            limit=limit
        )

        recruiters = [Recruiter.model_validate(recruiter) for recruiter in db_recruiters]
        return recruiters, total

    async def get_pending_recruiters(
            self,
            requesting_user_id: UUID,
            company_id: Optional[UUID] = None,
            skip: int = 0,
            limit: int = 20
    ) -> Tuple[List[Recruiter], int]:
        """Get pending recruiter applications"""
        # If company_id is specified, verify approval permission
        if company_id:
            await self._verify_recruiter_approval_permission(company_id, requesting_user_id)

        db_recruiters, total = await self.recruiter_repo.get_pending_recruiters(
            company_id, skip, limit
        )

        recruiters = [Recruiter.model_validate(recruiter) for recruiter in db_recruiters]
        return recruiters, total

    async def get_company_department_stats(self, company_id: UUID, user_id: UUID) -> Dict[str, int]:
        """Get recruiter statistics by department"""
        await self._verify_company_access_permission(company_id, user_id)
        return await self.recruiter_repo.get_department_stats(company_id)

    async def bulk_approve_recruiters(
            self,
            recruiter_ids: List[UUID],
            approved_by_user_id: UUID
    ) -> Dict[str, Any]:
        """Bulk approve recruiters"""
        if not recruiter_ids:
            return {"approved": 0, "errors": []}

        # Get approver's recruiter profile
        approver_recruiter = await self.recruiter_repo.get_by_user_id(approved_by_user_id)
        if not approver_recruiter:
            raise AuthorizationError("Only recruiters can approve other recruiters")

        # Verify all recruiters belong to the same company and user has permission
        for recruiter_id in recruiter_ids:
            recruiter = await self.recruiter_repo.get_by_id(recruiter_id)
            if recruiter:
                await self._verify_recruiter_approval_permission(recruiter.company_id, approved_by_user_id)

        # Bulk approve
        approved_count = await self.recruiter_repo.bulk_update_status(
            recruiter_ids,
            RecruiterStatus.APPROVED,
            approver_recruiter.id
        )

        return {
            "approved": approved_count,
            "total_requested": len(recruiter_ids)
        }

    # Permission verification helpers
    async def _verify_company_access_permission(self, company_id: UUID, user_id: UUID) -> None:
        """Verify user has access to company data"""
        has_access = await self.recruiter_repo.has_company_access(user_id, company_id)
        if not has_access:
            raise AuthorizationError("No access to this company")

    async def verify_company_management_permission(self, company_id: UUID, user_id: UUID) -> None:
        """Verify user can manage company"""
        recruiter = await self.recruiter_repo.get_by_user_id(user_id)
        if not recruiter or recruiter.company_id != company_id:
            raise AuthorizationError("No access to this company")

        can_manage = await self.recruiter_repo.can_manage_company(recruiter.id, company_id)
        if not can_manage:
            raise AuthorizationError("Insufficient permissions to manage company")

    async def _verify_recruiter_approval_permission(self, company_id: UUID, user_id: UUID) -> None:
        """Verify user can approve recruiters"""
        recruiter = await self.recruiter_repo.get_by_user_id(user_id)
        if not recruiter or recruiter.company_id != company_id:
            raise AuthorizationError("No access to this company")

        can_approve = await self.recruiter_repo.can_approve_recruiters(recruiter.id, company_id)
        if not can_approve:
            raise AuthorizationError("Insufficient permissions to approve recruiters")

    async def update_recruiter_activity(self, user_id: UUID) -> None:
        """Update recruiter's last activity (call this on authenticated requests)"""
        try:
            # Проверяем, является ли пользователь рекрутером
            recruiter = await self.recruiter_repo.get_by_user_id(user_id)
            if recruiter:
                await self.recruiter_repo.update_last_activity_by_user_id(user_id)
        except Exception:
            # Игнорируем ошибки - это не критично для основного функционала
            pass
