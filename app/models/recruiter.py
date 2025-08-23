# app/models/recruiter.py - Fixed version
from sqlalchemy import Boolean, Column, DateTime, String, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database import Base


class RecruiterStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class Recruiter(Base):
    __tablename__ = "recruiters"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, unique=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Recruiter details
    position = Column(String(100), nullable=True)  # HR Manager, Senior Recruiter, etc.
    department = Column(String(100), nullable=True)  # HR, Talent Acquisition, etc.
    bio = Column(Text, nullable=True)

    # Status and approval
    status = Column(SQLEnum(RecruiterStatus), default=RecruiterStatus.PENDING, nullable=False, index=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("recruiters.id"),
                         nullable=True)  # Another recruiter who approved
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Permissions
    can_approve_recruiters = Column(Boolean, default=False, nullable=False)  # Can approve other recruiters
    can_post_jobs = Column(Boolean, default=True, nullable=False)
    can_view_analytics = Column(Boolean, default=False, nullable=False)
    can_manage_company = Column(Boolean, default=False, nullable=False)  # Company admin

    # Contact preferences
    contact_email = Column(String(255), nullable=True)  # Work email
    contact_phone = Column(String(50), nullable=True)
    linkedin_profile = Column(String(255), nullable=True)

    # Activity tracking
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships - Fixed to match User model
    user = relationship("User", back_populates="recruiter_profile")
    company = relationship("Company", back_populates="recruiters")
    approved_by_recruiter = relationship("Recruiter", remote_side=[id])

    # Index constraints for better performance
    __table_args__ = (
        # Unique constraint: one user can only be recruiter for one company
        # This is handled by unique=True on user_id column
        # Additional composite indexes for common queries
        {'schema': None}
    )

    def __repr__(self) -> str:
        return f"<Recruiter(id={self.id}, user_id={self.user_id}, company_id={self.company_id}, status={self.status})>"

    @property
    def is_approved(self) -> bool:
        """Check if recruiter is approved and active"""
        return self.status == RecruiterStatus.APPROVED and self.is_active

    @property
    def can_perform_admin_actions(self) -> bool:
        """Check if recruiter can perform administrative actions"""
        return self.is_approved and self.can_manage_company

    @property
    def can_approve_others(self) -> bool:
        """Check if recruiter can approve other recruiters"""
        return self.is_approved and self.can_approve_recruiters

    @property
    def permission_level(self) -> str:
        """Get permission level as string"""
        if self.can_manage_company:
            return "admin"
        elif self.can_approve_recruiters:
            return "senior"
        elif self.can_post_jobs:
            return "recruiter"
        else:
            return "viewer"