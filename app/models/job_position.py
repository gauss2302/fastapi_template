from sqlalchemy import String, Integer, Float, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import enum
import re

from app.core.database.database import Base


class JobLevel(str, enum.Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


class JobType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"


class WorkingType(str, enum.Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"


class JobStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FLAGGED = "flagged"
    BLACKLISTED = "blacklisted"


class EducationLevel(str, enum.Enum):
    NONE = "none"
    HIGH_SCHOOL = "high_school"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class Job(Base):
    __tablename__ = 'job_postings'

    # Primary fields
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    # Basic Job Information
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # Company relationship
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )
    company_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True
    )  # Denormalized for performance

    # Creator relationship
    created_by_recruiter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recruiters.id"),
        nullable=True,
        index=True
    )

    # Job Details
    department: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    level: Mapped[JobLevel] = mapped_column(
        SQLEnum(JobLevel),
        nullable=False,
        index=True
    )
    type: Mapped[JobType] = mapped_column(
        SQLEnum(JobType),
        nullable=False,
        index=True
    )
    working_type: Mapped[WorkingType] = mapped_column(
        SQLEnum(WorkingType),
        nullable=False,
        index=True
    )

    # Location information
    location: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        index=True
    )
    latitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    state: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    timezone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    is_remote_allowed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )

    # Compensation
    salary_min: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )
    salary_max: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )
    salary_currency: Mapped[str] = mapped_column(
        String(3),
        default='USD',
        nullable=False,
        index=True
    )
    salary_period: Mapped[str] = mapped_column(
        String(20),
        default='yearly',
        nullable=False
    )  # yearly, monthly, hourly
    equity: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    benefits: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )

    # Requirements and Skills
    requirements: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False
    )
    preferred_skills: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True
    )
    required_skills: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True
    )
    experience_years_min: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )
    experience_years_max: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    education_level: Mapped[EducationLevel] = mapped_column(
        SQLEnum(EducationLevel),
        default=EducationLevel.BACHELOR,
        nullable=False
    )

    # Status Management
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus),
        default=JobStatus.DRAFT,
        nullable=False,
        index=True
    )

    # Analytics & Tracking
    applications_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True
    )
    views_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True
    )
    saves_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # Timeline Management
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    application_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    closure_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    # Contact and Application Information
    hr_contact_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    hr_contact_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    apply_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )  # External application URL
    application_instructions: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # SEO and URL
    slug: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        index=True,
        nullable=False
    )

    # Priority and Featured
    is_featured: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    is_urgent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    priority_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True
    )

    # RELATIONSHIPS with proper typing
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="jobs",
        lazy="select"
    )
    created_by_recruiter: Mapped[Optional["Recruiter"]] = relationship(
        "Recruiter",
        back_populates="created_jobs",
        lazy="select"
    )
    applications: Mapped[List["Application"]] = relationship(
        "Application",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', company_id={self.company_id})>"

    def __str__(self) -> str:
        return f"{self.title} at {self.company_name} ({self.status.value})"

    # Status properties
    @property
    def is_active(self) -> bool:
        """Check if job posting is active and accepting applications"""
        return (
                self.status == JobStatus.ACTIVE and
                self.posted_at is not None and
                not self.is_expired and
                not self.is_deleted
        )

    @property
    def is_published(self) -> bool:
        """Check if job is published (visible to public)"""
        return self.posted_at is not None and not self.is_deleted

    @property
    def is_deleted(self) -> bool:
        """Check if job is soft deleted"""
        return self.deleted_at is not None

    @property
    def is_expired(self) -> bool:
        """Check if job has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        if self.application_deadline:
            return datetime.utcnow() > self.application_deadline
        return False

    @property
    def is_draft(self) -> bool:
        """Check if job is in draft status"""
        return self.status == JobStatus.DRAFT

    @property
    def is_closed(self) -> bool:
        """Check if job is closed (filled, cancelled, etc.)"""
        return self.status in [JobStatus.FILLED, JobStatus.CANCELLED, JobStatus.EXPIRED]

    # Time-based properties
    @property
    def days_live(self) -> int:
        """Calculate days since posting"""
        if self.posted_at is None:
            return 0
        return (datetime.utcnow() - self.posted_at).days

    @property
    def days_until_deadline(self) -> Optional[int]:
        """Days until application deadline"""
        if self.application_deadline:
            delta = self.application_deadline - datetime.utcnow()
            return max(0, delta.days)
        return None

    @property
    def days_until_expiry(self) -> Optional[int]:
        """Days until job expires"""
        if self.expires_at:
            delta = self.expires_at - datetime.utcnow()
            return max(0, delta.days)
        return None

    @property
    def is_recent(self) -> bool:
        """Check if job was posted recently (last 7 days)"""
        return self.days_live <= 7

    @property
    def is_stale(self) -> bool:
        """Check if job has been live for too long (>90 days)"""
        return self.days_live > 90

    # Application properties
    @property
    def can_accept_applications(self) -> bool:
        """Check if job can accept new applications"""
        return (
                self.is_active and
                not self.is_expired and
                (self.application_deadline is None or self.application_deadline > datetime.utcnow())
        )

    @property
    def application_rate(self) -> float:
        """Applications per view ratio"""
        if self.views_count == 0:
            return 0.0
        return self.applications_count / self.views_count

    @property
    def engagement_score(self) -> float:
        """Overall engagement score based on views, applications, saves"""
        if self.views_count == 0:
            return 0.0

        # Weighted score: applications are more valuable than saves
        weighted_engagement = (self.applications_count * 10) + (self.saves_count * 3)
        return weighted_engagement / self.views_count

    # Salary properties
    @property
    def has_salary_info(self) -> bool:
        """Check if job has salary information"""
        return self.salary_min is not None or self.salary_max is not None

    @property
    def salary_range_display(self) -> str:
        """Get human-readable salary range"""
        if not self.has_salary_info:
            return "Salary not disclosed"

        currency_symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(self.salary_currency, self.salary_currency)

        if self.salary_min and self.salary_max:
            return f"{currency_symbol}{self.salary_min:,} - {currency_symbol}{self.salary_max:,}"
        elif self.salary_min:
            return f"{currency_symbol}{self.salary_min:,}+"
        elif self.salary_max:
            return f"Up to {currency_symbol}{self.salary_max:,}"

        return "Salary not disclosed"

    @property
    def salary_midpoint(self) -> Optional[int]:
        """Calculate salary midpoint"""
        if self.salary_min and self.salary_max:
            return (self.salary_min + self.salary_max) // 2
        return self.salary_min or self.salary_max

    # Skills and requirements properties
    @property
    def all_skills(self) -> List[str]:
        """Get all skills (required + preferred)"""
        skills = []
        if self.required_skills:
            skills.extend(self.required_skills)
        if self.preferred_skills:
            skills.extend(self.preferred_skills)
        return list(set(skills))  # Remove duplicates

    @property
    def skill_count(self) -> int:
        """Total number of unique skills"""
        return len(self.all_skills)

    @property
    def experience_range_display(self) -> str:
        """Get human-readable experience range"""
        if self.experience_years_min and self.experience_years_max:
            return f"{self.experience_years_min}-{self.experience_years_max} years"
        elif self.experience_years_min:
            return f"{self.experience_years_min}+ years"
        elif self.experience_years_max:
            return f"Up to {self.experience_years_max} years"
        return "Experience not specified"

    # Location properties
    @property
    def is_remote_job(self) -> bool:
        """Check if job is fully remote"""
        return self.working_type == WorkingType.REMOTE

    @property
    def location_display(self) -> str:
        """Get human-readable location"""
        if self.is_remote_job:
            return "Remote"

        location_parts = []
        if self.city:
            location_parts.append(self.city)
        if self.state:
            location_parts.append(self.state)
        if self.country and self.country != "US":  # Don't show US for brevity
            location_parts.append(self.country)

        if location_parts:
            base_location = ", ".join(location_parts)
            if self.working_type == WorkingType.HYBRID:
                return f"{base_location} (Hybrid)"
            return base_location

        return self.location or "Location not specified"

    # Business logic methods
    def publish(self) -> None:
        """Publish the job posting"""
        if self.status == JobStatus.DRAFT:
            self.status = JobStatus.ACTIVE
            self.posted_at = datetime.utcnow()

            # Set default expiry if not set (90 days)
            if not self.expires_at:
                self.expires_at = datetime.utcnow() + timedelta(days=90)

    def pause(self, reason: Optional[str] = None) -> None:
        """Pause the job posting"""
        self.status = JobStatus.PAUSED
        if reason:
            self.closure_reason = reason

    def close(self, status: JobStatus, reason: Optional[str] = None) -> None:
        """Close the job posting"""
        if status in [JobStatus.FILLED, JobStatus.CANCELLED, JobStatus.EXPIRED]:
            self.status = status
            self.closed_at = datetime.utcnow()
            if reason:
                self.closure_reason = reason

    def reopen(self) -> None:
        """Reopen a closed job"""
        if self.is_closed:
            self.status = JobStatus.ACTIVE
            self.closed_at = None
            self.closure_reason = None

    def soft_delete(self, reason: Optional[str] = None) -> None:
        """Soft delete the job posting"""
        self.deleted_at = datetime.utcnow()
        if reason:
            self.closure_reason = reason

    def restore(self) -> None:
        """Restore a soft-deleted job"""
        self.deleted_at = None

    def increment_views(self) -> None:
        """Increment view counter"""
        self.views_count += 1

    def increment_applications(self) -> None:
        """Increment application counter"""
        self.applications_count += 1

    def increment_saves(self) -> None:
        """Increment saves counter"""
        self.saves_count += 1

    def update_priority(self, score: int) -> None:
        """Update priority score (0-100)"""
        self.priority_score = max(0, min(100, score))

    def make_featured(self, featured: bool = True) -> None:
        """Set featured status"""
        self.is_featured = featured
        if featured:
            self.priority_score = max(self.priority_score, 80)

    def make_urgent(self, urgent: bool = True) -> None:
        """Set urgent status"""
        self.is_urgent = urgent
        if urgent:
            self.priority_score = max(self.priority_score, 90)

    # Validation methods
    def validate_salary_range(self) -> List[str]:
        """Validate salary range"""
        errors = []

        if self.salary_min and self.salary_max:
            if self.salary_min > self.salary_max:
                errors.append("Minimum salary cannot exceed maximum salary")
            if self.salary_max > self.salary_min * 5:
                errors.append("Salary range too wide (max cannot be 5x more than min)")

        if self.salary_min and self.salary_min < 0:
            errors.append("Salary cannot be negative")

        return errors

    def validate_requirements(self) -> List[str]:
        """Validate job requirements"""
        errors = []

        if not self.requirements or len(self.requirements) < 3:
            errors.append("At least 3 requirements are needed")

        if len(self.requirements) > 20:
            errors.append("Too many requirements (max 20)")

        return errors

    def validate_timeline(self) -> List[str]:
        """Validate job timeline"""
        errors = []

        now = datetime.utcnow()

        if self.application_deadline and self.application_deadline <= now:
            errors.append("Application deadline cannot be in the past")

        if self.expires_at and self.expires_at <= now:
            errors.append("Expiry date cannot be in the past")

        if (self.application_deadline and self.expires_at and
                self.application_deadline > self.expires_at):
            errors.append("Application deadline cannot be after expiry date")

        return errors

    def get_validation_errors(self) -> List[str]:
        """Get all validation errors"""
        errors = []
        errors.extend(self.validate_salary_range())
        errors.extend(self.validate_requirements())
        errors.extend(self.validate_timeline())
        return errors

    # Search and filter helpers
    def matches_salary_range(self, min_salary: Optional[int], max_salary: Optional[int]) -> bool:
        """Check if job matches salary range criteria"""
        if not min_salary and not max_salary:
            return True

        job_min = self.salary_min or 0
        job_max = self.salary_max or float('inf')

        if min_salary and job_max < min_salary:
            return False
        if max_salary and job_min > max_salary:
            return False

        return True

    def matches_skills(self, required_skills: List[str]) -> bool:
        """Check if job matches required skills"""
        if not required_skills:
            return True

        job_skills = [skill.lower() for skill in self.all_skills]
        return any(skill.lower() in job_skills for skill in required_skills)

    # Query helpers
    @classmethod
    def active_jobs_filter(cls):
        """Filter for active jobs"""
        return (
                (cls.status == JobStatus.ACTIVE) &
                (cls.posted_at.isnot(None)) &
                (cls.deleted_at.is_(None))
        )

    @classmethod
    def published_jobs_filter(cls):
        """Filter for published jobs"""
        return (cls.posted_at.isnot(None)) & (cls.deleted_at.is_(None))

    @classmethod
    def company_jobs_filter(cls, company_id: uuid.UUID):
        """Filter for company jobs"""
        return cls.company_id == company_id

    @classmethod
    def recent_jobs_filter(cls, days: int = 7):
        """Filter for recent jobs"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return cls.posted_at >= cutoff_date

    @classmethod
    def featured_jobs_filter(cls):
        """Filter for featured jobs"""
        return cls.is_featured == True

    @classmethod
    def remote_jobs_filter(cls):
        """Filter for remote jobs"""
        return cls.working_type == WorkingType.REMOTE