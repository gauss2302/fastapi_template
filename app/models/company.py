from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.sql import func
from typing import Optional, List
from datetime import datetime
import uuid
import enum

from app.core.database.database import Base


class CompanyStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class CompanySize(str, enum.Enum):
    STARTUP = "startup"  # 1-10
    SMALL = "small"  # 11-50
    MEDIUM = "medium"  # 51-200
    LARGE = "large"  # 201-1000
    ENTERPRISE = "enterprise"  # 1000+


class Company(Base):
    __tablename__ = "companies"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Basic company info
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )
    legal_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False
    )

    # Company details
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    website: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    company_size: Mapped[Optional[CompanySize]] = mapped_column(
        SQLEnum(CompanySize),
        nullable=True,
        index=True
    )
    founded_year: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    # Contact info
    headquarters: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    # Media
    logo_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    cover_image_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Verification and status
    status: Mapped[CompanyStatus] = mapped_column(
        SQLEnum(CompanyStatus),
        default=CompanyStatus.PENDING,
        nullable=False,
        index=True
    )
    verification_document_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    verification_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    # Social links
    linkedin_url: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    twitter_url: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    github_url: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Settings
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )
    is_hiring: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )
    allow_applications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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

    # Relationships with proper typing
    recruiters: Mapped[List["Recruiter"]] = relationship(
        "Recruiter",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="select"
    )
    verified_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[verified_by],
        lazy="select"
    )
    applications: Mapped[List["Application"]] = relationship(
        "Application",
        back_populates="company",
        lazy="select"
    )
    jobs: Mapped[List["Job"]] = relationship(
        "Job",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name={self.name}, status={self.status})>"

    def __str__(self) -> str:
        return f"{self.name} ({self.status.value})"

    # Business logic properties
    @property
    def is_verified(self) -> bool:
        """Check if company is verified and active"""
        return self.status == CompanyStatus.VERIFIED and self.is_active

    @property
    def can_post_jobs(self) -> bool:
        """Check if company can post jobs"""
        return self.is_verified and self.is_active and self.allow_applications

    @property
    def active_recruiters_count(self) -> int:
        """Get count of active approved recruiters"""
        if not self.recruiters:
            return 0

        from app.models.recruiter import RecruiterStatus
        return sum(
            1 for recruiter in self.recruiters
            if recruiter.status == RecruiterStatus.APPROVED and recruiter.is_active
        )

    @property
    def company_display_size(self) -> str:
        """Get human-readable company size"""
        if not self.company_size:
            return "Size not specified"

        size_map = {
            CompanySize.STARTUP: "1-10 employees",
            CompanySize.SMALL: "11-50 employees",
            CompanySize.MEDIUM: "51-200 employees",
            CompanySize.LARGE: "201-1000 employees",
            CompanySize.ENTERPRISE: "1000+ employees"
        }
        return size_map.get(self.company_size, "Size not specified")

    @property
    def display_name(self) -> str:
        """Get display name (legal name if available, otherwise name)"""
        return self.legal_name if self.legal_name else self.name

    @property
    def verification_status_display(self) -> str:
        """Get human-readable verification status"""
        status_map = {
            CompanyStatus.PENDING: "Pending Verification",
            CompanyStatus.VERIFIED: "Verified",
            CompanyStatus.SUSPENDED: "Suspended",
            CompanyStatus.REJECTED: "Verification Rejected"
        }
        return status_map.get(self.status, self.status.value)

    @property
    def is_social_complete(self) -> bool:
        """Check if social media links are provided"""
        return bool(self.linkedin_url or self.twitter_url or self.github_url)

    @property
    def profile_completeness(self) -> float:
        """Calculate profile completeness percentage (0.0 to 1.0)"""
        total_fields = 12
        completed_fields = 0

        # Required basic fields
        if self.name: completed_fields += 1
        if self.description: completed_fields += 1
        if self.industry: completed_fields += 1
        if self.headquarters: completed_fields += 1
        if self.website: completed_fields += 1

        # Optional but important fields
        if self.company_size: completed_fields += 1
        if self.founded_year: completed_fields += 1
        if self.email: completed_fields += 1
        if self.phone: completed_fields += 1
        if self.logo_url: completed_fields += 1

        # Social presence
        if self.linkedin_url: completed_fields += 1
        if self.twitter_url or self.github_url: completed_fields += 1

        return completed_fields / total_fields

    # Business logic methods
    def can_be_verified(self) -> bool:
        """Check if company meets verification requirements"""
        required_fields = [
            self.name,
            self.description,
            self.industry,
            self.headquarters,
            self.email
        ]
        return all(required_fields) and self.status == CompanyStatus.PENDING

    def verify(self, verified_by_user_id: uuid.UUID, notes: Optional[str] = None) -> None:
        """Mark company as verified"""
        self.status = CompanyStatus.VERIFIED
        self.verified_by = verified_by_user_id
        self.verified_at = datetime.utcnow()
        if notes:
            self.verification_notes = notes

    def reject_verification(self, reason: str) -> None:
        """Reject company verification"""
        self.status = CompanyStatus.REJECTED
        self.verification_notes = reason
        self.verified_at = None
        self.verified_by = None

    def suspend(self, reason: str) -> None:
        """Suspend company"""
        self.status = CompanyStatus.SUSPENDED
        self.verification_notes = reason
        self.is_active = False

    def reactivate(self) -> None:
        """Reactivate suspended company"""
        if self.status == CompanyStatus.SUSPENDED:
            self.status = CompanyStatus.VERIFIED
            self.is_active = True

    def update_hiring_status(self, is_hiring: bool) -> None:
        """Update company hiring status"""
        self.is_hiring = is_hiring

    # Validation methods
    def validate_social_urls(self) -> List[str]:
        """Validate social media URLs format"""
        errors = []

        if self.linkedin_url and not self.linkedin_url.startswith(('http://', 'https://')):
            errors.append("LinkedIn URL must start with http:// or https://")

        if self.twitter_url and not self.twitter_url.startswith(('http://', 'https://')):
            errors.append("Twitter URL must start with http:// or https://")

        if self.github_url and not self.github_url.startswith(('http://', 'https://')):
            errors.append("GitHub URL must start with http:// or https://")

        if self.website and not self.website.startswith(('http://', 'https://')):
            errors.append("Website URL must start with http:// or https://")

        return errors

    def validate_founding_year(self) -> List[str]:
        """Validate founding year"""
        errors = []
        current_year = datetime.now().year

        if self.founded_year:
            if self.founded_year < 1800:
                errors.append("Founded year cannot be before 1800")
            elif self.founded_year > current_year:
                errors.append("Founded year cannot be in the future")

        return errors

    def get_validation_errors(self) -> List[str]:
        """Get all validation errors"""
        errors = []
        errors.extend(self.validate_social_urls())
        errors.extend(self.validate_founding_year())
        return errors

    # Query helpers (for use in repositories)
    @classmethod
    def active_companies_filter(cls):
        """SQLAlchemy filter for active companies"""
        return cls.is_active == True

    @classmethod
    def verified_companies_filter(cls):
        """SQLAlchemy filter for verified companies"""
        return cls.status == CompanyStatus.VERIFIED

    @classmethod
    def hiring_companies_filter(cls):
        """SQLAlchemy filter for companies that are hiring"""
        return cls.is_hiring == True