from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, ForeignKey, Integer, JSON, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import uuid
import enum


from app.core.database.database import Base

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
    """Application model with modern SQLAlchemy 2.0 syntax."""

    __tablename__ = "applications"

    # Primary key
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
        index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_postings.id"),
        index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        index=True
    )
    recruiter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recruiters.id"),
        index=True
    )

    # Application content
    cover_letter: Mapped[Optional[str]] = mapped_column(Text)
    resume_url: Mapped[Optional[str]] = mapped_column(Text)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Application metadata
    source: Mapped[ApplicationSource] = mapped_column(
        default=ApplicationSource.WEBSITE,
        index=True
    )
    referrer_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id")
    )

    # Custom application data (JSON field for flexibility)
    additional_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Status and timeline
    status: Mapped[ApplicationStatus] = mapped_column(
        default=ApplicationStatus.PENDING,
        index=True
    )
    applied_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        index=True
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now()
    )
    status_updated_at: Mapped[Optional[datetime]]

    # Recruiter actions and notes
    recruiter_notes: Mapped[Optional[str]] = mapped_column(Text)
    internal_rating: Mapped[Optional[int]] = mapped_column(Integer)
    viewed_at: Mapped[Optional[datetime]]

    # Interview and process tracking
    interview_scheduled_at: Mapped[Optional[datetime]]
    interview_completed_at: Mapped[Optional[datetime]]
    technical_test_sent_at: Mapped[Optional[datetime]]
    technical_test_completed_at: Mapped[Optional[datetime]]

    # Offer and final decision
    offer_sent_at: Mapped[Optional[datetime]]
    offer_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    offer_expires_at: Mapped[Optional[datetime]]

    # Rejection details
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(500))
    rejected_at: Mapped[Optional[datetime]]

    # System fields
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships with type annotations
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="applications"
    )
    job: Mapped["Job"] = relationship("Job", back_populates="applications")
    company: Mapped["Company"] = relationship("Company", back_populates="applications")
    recruiter: Mapped[Optional["Recruiter"]] = relationship(
        "Recruiter",
        back_populates="applications"
    )
    referrer: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[referrer_user_id]
    )

    # Table constraints and indexes
    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_applications_status_applied_at", "status", "applied_at"),
        Index("ix_applications_company_status", "company_id", "status"),
        Index("ix_applications_recruiter_status", "recruiter_id", "status"),
        Index("ix_applications_user_status", "user_id", "status"),

        # Check constraints
        CheckConstraint(
            "internal_rating >= 1 AND internal_rating <= 5",
            name="check_rating_range"
        ),
        CheckConstraint(
            "offer_expires_at > offer_sent_at",
            name="check_offer_expiry"
        ),
        CheckConstraint(
            "interview_scheduled_at > applied_at",
            name="check_interview_after_application"
        ),
    )

    def __repr__(self) -> str:
        return (f"<Application(id={self.id}, user_id={self.user_id}, "
                f"job_id={self.job_id}, status={self.status})>")

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
        return (self.interview_scheduled_at is not None and
                self.interview_scheduled_at > datetime.utcnow())

    @property
    def is_offer_pending(self) -> bool:
        """Check if offer is pending response."""
        return (self.status == ApplicationStatus.OFFERED and
                self.offer_expires_at and
                self.offer_expires_at > datetime.utcnow())

    # Business logic methods
    def update_status(
            self,
            new_status: ApplicationStatus,
            notes: Optional[str] = None,
            reason: Optional[str] = None
    ) -> None:
        """Update application status with timestamp."""
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
        if interview_datetime <= datetime.utcnow():
            raise ValueError("Interview cannot be scheduled in the past")

        self.interview_scheduled_at = interview_datetime
        if self.status == ApplicationStatus.PENDING:
            self.update_status(ApplicationStatus.SCREENING)

    def complete_interview(
            self,
            rating: Optional[int] = None,
            notes: Optional[str] = None
    ) -> None:
        """Mark interview as completed."""
        if rating is not None and (rating < 1 or rating > 5):
            raise ValueError("Rating must be between 1 and 5")

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

    def make_offer(
            self,
            offer_details: Dict[str, Any],
            expires_in_days: int = 7
    ) -> None:
        """Make job offer to candidate."""
        if expires_in_days <= 0:
            raise ValueError("Offer expiry must be positive")

        self.offer_details = offer_details
        self.offer_sent_at = datetime.utcnow()
        self.offer_expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        self.update_status(ApplicationStatus.OFFERED)

    def accept_offer(self) -> None:
        """Accept job offer."""
        if self.status != ApplicationStatus.OFFERED:
            raise ValueError("Can only accept an offered application")
        self.update_status(ApplicationStatus.ACCEPTED)

    def reject_offer(self, reason: Optional[str] = None) -> None:
        """Reject job offer."""
        self.update_status(ApplicationStatus.REJECTED, reason=reason)

    def withdraw_application(self, reason: Optional[str] = None) -> None:
        """Withdraw application (candidate action)."""
        if self.is_closed:
            raise ValueError("Cannot withdraw a closed application")
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

    def can_send_technical_test(self) -> bool:
        """Check if technical test can be sent."""
        return self.status in [ApplicationStatus.SCREENING, ApplicationStatus.INTERVIEWED]

