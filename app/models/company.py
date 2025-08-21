from sqlalchemy import Boolean, Column, DateTime, String, Text, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database import Base


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

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Basic company info
    name = Column(String(255), unique=True, index=True, nullable=False)
    legal_name = Column(String(255), nullable=True)
    slug = Column(String(100), unique=True, index=True, nullable=False)  # URL-friendly name

    # Company details
    description = Column(Text, nullable=True)
    website = Column(String(255), nullable=True)
    industry = Column(String(100), nullable=True, index=True)
    company_size = Column(SQLEnum(CompanySize), nullable=True, index=True)
    founded_year = Column(Integer, nullable=True)

    # Contact info
    headquarters = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Media
    logo_url = Column(Text, nullable=True)
    cover_image_url = Column(Text, nullable=True)

    # Verification and status
    status = Column(SQLEnum(CompanyStatus), default=CompanyStatus.PENDING, nullable=False, index=True)
    verification_document_url = Column(Text, nullable=True)  # Business license, etc.
    verification_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Admin who verified

    # Social links
    linkedin_url = Column(String(255), nullable=True)
    twitter_url = Column(String(255), nullable=True)
    github_url = Column(String(255), nullable=True)

    # Settings
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_hiring = Column(Boolean, default=True, nullable=False, index=True)
    allow_applications = Column(Boolean, default=True, nullable=False)

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

    # Relationships
    recruiters = relationship("Recruiter", back_populates="company", cascade="all, delete-orphan")
    verified_by_user = relationship("User", foreign_keys=[verified_by])

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name={self.name}, status={self.status})>"

    @property
    def is_verified(self) -> bool:
        """Check if company is verified and active"""
        return self.status == CompanyStatus.VERIFIED and self.is_active

    @property
    def active_recruiters_count(self) -> int:
        """Get count of active approved recruiters"""
        from app.models.recruiter import RecruiterStatus  # Import here to avoid circular import
        return len([
            r for r in self.recruiters
            if r.status == RecruiterStatus.APPROVED and r.is_active
        ])

    @property
    def company_display_size(self) -> str:
        """Get human-readable company size"""
        size_map = {
            CompanySize.STARTUP: "1-10 employees",
            CompanySize.SMALL: "11-50 employees",
            CompanySize.MEDIUM: "51-200 employees",
            CompanySize.LARGE: "201-1000 employees",
            CompanySize.ENTERPRISE: "1000+ employees"
        }
        return size_map.get(self.company_size, "Size not specified")