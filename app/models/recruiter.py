from sqlalchemy import Boolean, DateTime, String, Text, ForeignKey, Enum as SQLEnum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.sql import func
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import enum

from app.core.database.database import Base


class RecruiterStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class PermissionLevel(str, enum.Enum):
    VIEWER = "viewer"
    RECRUITER = "recruiter"
    SENIOR = "senior"
    ADMIN = "admin"


class Recruiter(Base):
    __tablename__ = "recruiters"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        unique=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    # Recruiter profile information
    position: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )  # HR Manager, Senior Recruiter, etc.
    department: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )  # HR, Talent Acquisition, etc.
    bio: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Status and approval workflow
    status: Mapped[RecruiterStatus] = mapped_column(
        SQLEnum(RecruiterStatus),
        default=RecruiterStatus.PENDING,
        nullable=False,
        index=True
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recruiters.id"),
        nullable=True
    )  # Recruiter who approved this application
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Permission system (granular permissions)
    can_approve_recruiters: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )  # Can approve other recruiters
    can_post_jobs: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )  # Can create and manage job postings
    can_view_analytics: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )  # Can view company analytics
    can_manage_company: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )  # Company admin privileges
    can_view_applications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )  # Can view job applications
    can_manage_applications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )  # Can update application status
    can_schedule_interviews: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )  # Can schedule interviews

    # Contact information
    contact_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )  # Work email
    contact_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    linkedin_profile: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Activity and engagement tracking
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    jobs_posted_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    applications_reviewed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # RELATIONSHIPS with proper typing
    user: Mapped["User"] = relationship(
        "User",
        back_populates="recruiter_profile",
        lazy="select"
    )
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="recruiters",
        lazy="select"
    )
    approved_by_recruiter: Mapped[Optional["Recruiter"]] = relationship(
        "Recruiter",
        remote_side=[id],
        lazy="select"
    )

    # Jobs created by this recruiter
    created_jobs: Mapped[List["Job"]] = relationship(
        "Job",
        back_populates="created_by_recruiter",
        foreign_keys="Job.created_by_recruiter_id",
        lazy="select"
    )

    # Applications assigned to this recruiter
    applications: Mapped[List["Application"]] = relationship(
        "Application",
        back_populates="recruiter",
        lazy="select"
    )

    # Recruiters approved by this recruiter
    approved_recruiters: Mapped[List["Recruiter"]] = relationship(
        "Recruiter",
        foreign_keys=[approved_by],
        back_populates="approved_by_recruiter",
        overlaps="approved_by_recruiter",  # Исправляет предупреждение SQLAlchemy
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Recruiter(id={self.id}, user_id={self.user_id}, company_id={self.company_id}, status={self.status})>"

    def __str__(self) -> str:
        user_name = self.user.display_name if self.user else "Unknown"
        return f"{user_name} - {self.position or 'Recruiter'} ({self.status.value})"

    # Status properties
    @property
    def is_approved(self) -> bool:
        """Check if recruiter is approved and active"""
        return self.status == RecruiterStatus.APPROVED and self.is_active

    @property
    def is_pending(self) -> bool:
        """Check if recruiter application is pending"""
        return self.status == RecruiterStatus.PENDING

    @property
    def is_rejected(self) -> bool:
        """Check if recruiter application was rejected"""
        return self.status == RecruiterStatus.REJECTED

    @property
    def is_suspended(self) -> bool:
        """Check if recruiter is suspended"""
        return self.status == RecruiterStatus.SUSPENDED

    # Permission properties
    @property
    def can_perform_admin_actions(self) -> bool:
        """Check if recruiter can perform administrative actions"""
        return self.is_approved and self.can_manage_company

    @property
    def can_approve_others(self) -> bool:
        """Check if recruiter can approve other recruiters"""
        return self.is_approved and self.can_approve_recruiters

    @property
    def can_recruit_effectively(self) -> bool:
        """Check if recruiter has minimum permissions to recruit"""
        return (
            self.is_approved and
            self.can_post_jobs and
            self.can_view_applications
        )

    @property
    def permission_level(self) -> PermissionLevel:
        """Get permission level as enum"""
        if self.can_manage_company:
            return PermissionLevel.ADMIN
        elif self.can_approve_recruiters:
            return PermissionLevel.SENIOR
        elif self.can_post_jobs:
            return PermissionLevel.RECRUITER
        else:
            return PermissionLevel.VIEWER

    @property
    def permission_level_display(self) -> str:
        """Get human-readable permission level"""
        level_map = {
            PermissionLevel.ADMIN: "Company Administrator",
            PermissionLevel.SENIOR: "Senior Recruiter",
            PermissionLevel.RECRUITER: "Recruiter",
            PermissionLevel.VIEWER: "Viewer"
        }
        return level_map.get(self.permission_level, "Unknown")

    @property
    def permissions_list(self) -> List[str]:
        """Get list of granted permissions"""
        permissions = []
        if self.can_manage_company:
            permissions.append("manage_company")
        if self.can_approve_recruiters:
            permissions.append("approve_recruiters")
        if self.can_post_jobs:
            permissions.append("post_jobs")
        if self.can_view_analytics:
            permissions.append("view_analytics")
        if self.can_view_applications:
            permissions.append("view_applications")
        if self.can_manage_applications:
            permissions.append("manage_applications")
        if self.can_schedule_interviews:
            permissions.append("schedule_interviews")
        return permissions

    # Activity properties
    @property
    def days_since_last_activity(self) -> Optional[int]:
        """Days since last activity"""
        if self.last_activity_at:
            return (datetime.utcnow() - self.last_activity_at).days
        return None

    @property
    def is_recently_active(self) -> bool:
        """Was recruiter active in last 7 days"""
        days_since = self.days_since_last_activity
        return days_since is not None and days_since <= 7

    @property
    def is_stale(self) -> bool:
        """Has recruiter been inactive for more than 30 days"""
        days_since = self.days_since_last_activity
        return days_since is not None and days_since > 30

    @property
    def approval_duration_days(self) -> Optional[int]:
        """Days from creation to approval"""
        if self.approved_at:
            return (self.approved_at - self.created_at).days
        return None

    # Performance metrics
    @property
    def average_jobs_per_month(self) -> float:
        """Average jobs posted per month"""
        months_active = max(1, (datetime.utcnow() - self.created_at).days / 30)
        return self.jobs_posted_count / months_active

    @property
    def average_applications_per_month(self) -> float:
        """Average applications reviewed per month"""
        months_active = max(1, (datetime.utcnow() - self.created_at).days / 30)
        return self.applications_reviewed_count / months_active

    # Business logic methods
    def approve(
        self,
        approved_by_recruiter_id: uuid.UUID,
        notes: Optional[str] = None
    ) -> None:
        """Approve recruiter application"""
        self.status = RecruiterStatus.APPROVED
        self.approved_by = approved_by_recruiter_id
        self.approved_at = datetime.utcnow()
        self.rejection_reason = None  # Clear any previous rejection reason

    def reject(self, reason: str) -> None:
        """Reject recruiter application"""
        self.status = RecruiterStatus.REJECTED
        self.rejection_reason = reason
        self.approved_by = None
        self.approved_at = None

    def suspend(self, reason: str) -> None:
        """Suspend recruiter"""
        self.status = RecruiterStatus.SUSPENDED
        self.rejection_reason = reason
        self.is_active = False

    def reactivate(self) -> None:
        """Reactivate suspended recruiter"""
        if self.status == RecruiterStatus.SUSPENDED:
            self.status = RecruiterStatus.APPROVED
            self.is_active = True
            self.rejection_reason = None

    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity_at = datetime.utcnow()

    def increment_jobs_posted(self) -> None:
        """Increment jobs posted counter"""
        self.jobs_posted_count += 1
        self.update_activity()

    def increment_applications_reviewed(self) -> None:
        """Increment applications reviewed counter"""
        self.applications_reviewed_count += 1
        self.update_activity()

    def update_permissions(
        self,
        can_approve_recruiters: Optional[bool] = None,
        can_post_jobs: Optional[bool] = None,
        can_view_analytics: Optional[bool] = None,
        can_manage_company: Optional[bool] = None,
        can_view_applications: Optional[bool] = None,
        can_manage_applications: Optional[bool] = None,
        can_schedule_interviews: Optional[bool] = None
    ) -> None:
        """Update recruiter permissions"""
        if can_approve_recruiters is not None:
            self.can_approve_recruiters = can_approve_recruiters
        if can_post_jobs is not None:
            self.can_post_jobs = can_post_jobs
        if can_view_analytics is not None:
            self.can_view_analytics = can_view_analytics
        if can_manage_company is not None:
            self.can_manage_company = can_manage_company
        if can_view_applications is not None:
            self.can_view_applications = can_view_applications
        if can_manage_applications is not None:
            self.can_manage_applications = can_manage_applications
        if can_schedule_interviews is not None:
            self.can_schedule_interviews = can_schedule_interviews

    def set_permission_level(self, level: PermissionLevel) -> None:
        """Set permissions based on level"""
        # Reset all permissions first
        self.can_approve_recruiters = False
        self.can_post_jobs = False
        self.can_view_analytics = False
        self.can_manage_company = False
        self.can_view_applications = False
        self.can_manage_applications = False
        self.can_schedule_interviews = False

        # Set permissions based on level
        if level == PermissionLevel.VIEWER:
            self.can_view_applications = True
        elif level == PermissionLevel.RECRUITER:
            self.can_post_jobs = True
            self.can_view_applications = True
            self.can_manage_applications = True
            self.can_schedule_interviews = True
        elif level == PermissionLevel.SENIOR:
            self.can_post_jobs = True
            self.can_view_applications = True
            self.can_manage_applications = True
            self.can_schedule_interviews = True
            self.can_approve_recruiters = True
            self.can_view_analytics = True
        elif level == PermissionLevel.ADMIN:
            self.can_post_jobs = True
            self.can_view_applications = True
            self.can_manage_applications = True
            self.can_schedule_interviews = True
            self.can_approve_recruiters = True
            self.can_view_analytics = True
            self.can_manage_company = True

    # Validation methods
    def validate_permissions(self) -> List[str]:
        """Validate permission combinations"""
        errors = []

        # Company admin should have all permissions
        if self.can_manage_company:
            required_permissions = [
                self.can_approve_recruiters,
                self.can_post_jobs,
                self.can_view_analytics,
                self.can_view_applications,
                self.can_manage_applications
            ]
            if not all(required_permissions):
                errors.append("Company admin should have all permissions")

        # Can't manage applications without viewing them
        if self.can_manage_applications and not self.can_view_applications:
            errors.append("Cannot manage applications without viewing permission")

        # Can't schedule interviews without managing applications
        if self.can_schedule_interviews and not self.can_manage_applications:
            errors.append("Cannot schedule interviews without application management permission")

        return errors

    def validate_contact_info(self) -> List[str]:
        """Validate contact information"""
        errors = []

        if self.contact_email:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, self.contact_email):
                errors.append("Invalid contact email format")

        if self.linkedin_profile:
            if not self.linkedin_profile.startswith(('http://', 'https://')):
                errors.append("LinkedIn profile must be a valid URL")

        return errors

    def get_validation_errors(self) -> List[str]:
        """Get all validation errors"""
        errors = []
        errors.extend(self.validate_permissions())
        errors.extend(self.validate_contact_info())
        return errors

    # Authorization helpers
    def can_access_company_data(self, company_id: uuid.UUID) -> bool:
        """Check if recruiter can access company data"""
        return self.is_approved and self.company_id == company_id

    def can_approve_recruiter_for_company(self, company_id: uuid.UUID) -> bool:
        """Check if can approve recruiters for specific company"""
        return (
            self.is_approved and
            self.company_id == company_id and
            self.can_approve_recruiters
        )

    def can_manage_job(self, job_company_id: uuid.UUID) -> bool:
        """Check if can manage jobs for company"""
        return (
            self.is_approved and
            self.company_id == job_company_id and
            self.can_post_jobs
        )

    # Query helpers
    @classmethod
    def approved_recruiters_filter(cls):
        """Filter for approved recruiters"""
        return (cls.status == RecruiterStatus.APPROVED) & (cls.is_active == True)

    @classmethod
    def pending_recruiters_filter(cls):
        """Filter for pending recruiters"""
        return cls.status == RecruiterStatus.PENDING

    @classmethod
    def company_recruiters_filter(cls, company_id: uuid.UUID):
        """Filter for company recruiters"""
        return cls.company_id == company_id

    @classmethod
    def active_recruiters_filter(cls):
        """Filter for active recruiters"""
        return cls.is_active == True

    @classmethod
    def recent_activity_filter(cls, days: int = 30):
        """Filter for recruiters with recent activity"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return cls.last_activity_at >= cutoff_date