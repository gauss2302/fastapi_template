from sqlalchemy import Boolean, Column, DateTime, String, Text, ForeignKey, Integer, Enum as SQLEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import uuid
import enum

from app.core.database import Base


class ApplicationStatus(str, enum.Enum):
    """Application status enum."""
    PENDING = "pending"
    SCREENING = "screening"
    INTERVIEWED = "interviewed"
    TECHNICAL_TEST = "technical_test"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationSource(str, enum.Enum):
    """How the application was submitted."""
    WEBSITE = "website"
    MOBILE_APP = "mobile_app"
    REFERRAL = "referral"
    LINKEDIN = "linkedin"
    EMAIL = "email"


class Application(Base):
    __tablename__ = "applications"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    recruiter_id = Column(UUID(as_uuid=True), ForeignKey("recruiters.id"), nullable=True, index=True)

    # Application content
    cover_letter = Column(Text, nullable=True)
    resume_url = Column(Text, nullable=True)
    portfolio_url = Column(String(500), nullable=True)

    # Application metadata
    source = Column(SQLEnum(ApplicationSource), default=ApplicationSource.WEBSITE, nullable=False, index=True)
    referrer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Custom application data (JSON field for flexibility)
    additional_data = Column(JSON, nullable=True)

    # Status and timeline
    status = Column(SQLEnum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False, index=True)
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    status_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Recruiter actions and notes
    recruiter_notes = Column(Text, nullable=True)
    internal_rating = Column(Integer, nullable=True)  # 1-5 rating
    viewed_at = Column(DateTime(timezone=True), nullable=True)

    # Interview and process tracking
    interview_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    interview_completed_at = Column(DateTime(timezone=True), nullable=True)
    technical_test_sent_at = Column(DateTime(timezone=True), nullable=True)
    technical_test_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Offer and final decision
    offer_sent_at = Column(DateTime(timezone=True), nullable=True)
    offer_details = Column(JSON, nullable=True)  # Salary, benefits, etc.
    offer_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Rejection details
    rejection_reason = Column(String(500), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)

    # System fields
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="applications")
    job = relationship("Job", back_populates="applications")
    company = relationship("Company", back_populates="applications")
    recruiter = relationship("Recruiter", back_populates="applications")
    referrer = relationship("User", foreign_keys=[referrer_user_id])

    # Composite indexes for better query performance
    __table_args__ = (
        # Most common queries
        {'schema': None}
    )

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, user_id={self.user_id}, job_id={self.job_id}, status={self.status})>"

    # Business logic properties
    @property
    def days_since_applied(self) -> int:
        """Number of days since application was submitted."""
        return (datetime.utcnow() - self.applied_at).days

    @property
    def days_since_last_update(self) -> int:
        """Number of days since last status update."""
        return (datetime.utcnow() - self.last_updated_at).days

    @property
    def is_recent(self) -> bool:
        """Check if application was submitted in last 7 days."""
        return self.days_since_applied <= 7

    @property
    def is_stale(self) -> bool:
        """Check if application hasn't been updated in 30+ days."""
        return self.days_since_last_update >= 30

    @property
    def is_in_progress(self) -> bool:
        """Check if application is in an active state."""
        return self.status in [
            ApplicationStatus.PENDING,
            ApplicationStatus.SCREENING,
            ApplicationStatus.INTERVIEWED,
            ApplicationStatus.TECHNICAL_TEST,
            ApplicationStatus.OFFERED
        ]

    @property
    def is_closed(self) -> bool:
        """Check if application is in a final state."""
        return self.status in [
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN
        ]

    @property
    def has_interview_scheduled(self) -> bool:
        """Check if interview is scheduled."""
        return self.interview_scheduled_at is not None and self.interview_scheduled_at > datetime.utcnow()

    @property
    def is_offer_pending(self) -> bool:
        """Check if offer is pending response."""
        return (self.status == ApplicationStatus.OFFERED and
                self.offer_expires_at and
                self.offer_expires_at > datetime.utcnow())

    # Business logic methods
    def update_status(self, new_status: ApplicationStatus, notes: str = None, reason: str = None) -> None:
        """Update application status with timestamp."""
        old_status = self.status
        self.status = new_status
        self.status_updated_at = datetime.utcnow()
        self.last_updated_at = datetime.utcnow()

        if notes:
            self.recruiter_notes = notes

        # Set specific fields based on status
        if new_status == ApplicationStatus.REJECTED:
            self.rejected_at = datetime.utcnow()
            if reason:
                self.rejection_reason = reason

        elif new_status == ApplicationStatus.OFFERED:
            self.offer_sent_at = datetime.utcnow()
            # Set default offer expiry (7 days)
            self.offer_expires_at = datetime.utcnow() + timedelta(days=7)

    def mark_as_viewed(self) -> None:
        """Mark application as viewed by recruiter."""
        if not self.viewed_at:
            self.viewed_at = datetime.utcnow()

    def schedule_interview(self, interview_datetime: datetime) -> None:
        """Schedule interview for application."""
        self.interview_scheduled_at = interview_datetime
        if self.status == ApplicationStatus.PENDING:
            self.update_status(ApplicationStatus.SCREENING)

    def complete_interview(self, rating: int = None, notes: str = None) -> None:
        """Mark interview as completed."""
        self.interview_completed_at = datetime.utcnow()
        if rating:
            self.internal_rating = rating
        if notes:
            self.recruiter_notes = notes

    def send_technical_test(self) -> None:
        """Send technical test to candidate."""
        self.technical_test_sent_at = datetime.utcnow()
        self.update_status(ApplicationStatus.TECHNICAL_TEST)

    def complete_technical_test(self) -> None:
        """Mark technical test as completed."""
        self.technical_test_completed_at = datetime.utcnow()

    def make_offer(self, offer_details: dict, expires_in_days: int = 7) -> None:
        """Make job offer to candidate."""
        self.offer_details = offer_details
        self.offer_sent_at = datetime.utcnow()
        self.offer_expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        self.update_status(ApplicationStatus.OFFERED)

    def accept_offer(self) -> None:
        """Accept job offer."""
        self.update_status(ApplicationStatus.ACCEPTED)

    def reject_offer(self, reason: str = None) -> None:
        """Reject job offer."""
        self.update_status(ApplicationStatus.REJECTED, reason=reason)

    def withdraw_application(self, reason: str = None) -> None:
        """Withdraw application (candidate action)."""
        self.update_status(ApplicationStatus.WITHDRAWN, reason=reason)

    # Validation methods
    def can_be_updated_by_recruiter(self) -> bool:
        """Check if recruiter can still update this application."""
        return self.is_active and not self.is_closed

    def can_schedule_interview(self) -> bool:
        """Check if interview can be scheduled."""
        return self.status in [ApplicationStatus.PENDING, ApplicationStatus.SCREENING]

    def can_make_offer(self) -> bool:
        """Check if offer can be made."""
        return self.status in [ApplicationStatus.INTERVIEWED, ApplicationStatus.TECHNICAL_TEST]

