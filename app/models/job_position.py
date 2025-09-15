from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum
from typing import Dict, List, Optional

from app.core.database import Base



class JobLevel(enum.Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


class JobType(enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"


class WorkingType(enum.Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"


class SalaryPeriod(enum.Enum):
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    HOURLY = "hourly"


class EducationLevel(enum.Enum):
    NONE = "none"
    HIGH_SCHOOL = "high_school"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class JobStatus(enum.Enum):
    DRAFT = "draft"  # Черновик
    PENDING_REVIEW = "pending"  # Ожидает модерации
    ACTIVE = "active"  # Активная
    PAUSED = "paused"  # Приостановлена
    FILLED = "filled"  # Закрыта (нанят кандидат)
    CANCELLED = "cancelled"  # Отменена
    FLAGGED = "flagged"  # Подозрение на ghost job
    BLACKLISTED = "blacklisted"  # Заблокирована модератором


class VerificationLevel(enum.Enum):
    NONE = "none"  # Без верификации
    BASIC = "basic"  # Email verification
    STANDARD = "standard"  # Company + contact verification
    PREMIUM = "premium"  # Full verification + manual review


class Job(Base):
    __tablename__ = 'job_postings'

    # Primary fields
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Basic Job Information
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    company_id = Column(UUID(as_uuid=True), nullable=False)
    company_name = Column(String(200), nullable=False)

    # Job Details
    department = Column(String(100))
    level = Column(String(20), nullable=False)  # JobLevel enum values
    type = Column(String(20), nullable=False)  # JobType enum values
    location = Column(String(200))

    # Application
    applications = relationship("Application", back_populates="job")

    # Location coordinates
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))
    timezone = Column(String(50))

    # Compensation
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(3), default='USD')  # ISO currency codes
    equity = Column(String(100))
    benefits = Column(JSON)  # Stored as JSON array

    # Requirements
    requirements = Column(JSON, nullable=False)  # JSON array
    preferred_skills = Column(JSON)  # JSON array
    experience_years = Column(Integer, nullable=True)
    education_level = Column(String(20), nullable=False)  # EducationLevel enum values

    # Ghost Job Prevention Fields
    status = Column(String(20), nullable=False, default=JobStatus.DRAFT.value)
    verification_level = Column(String(20), nullable=False, default=VerificationLevel.NONE.value)

    # Hiring Pipeline Tracking
    applications_count = Column(Integer, default=0)
    screened_count = Column(Integer, default=0)
    interviewed_count = Column(Integer, default=0)
    offered_count = Column(Integer, default=0)
    hired_count = Column(Integer, default=0)
    last_activity = Column(DateTime(timezone=True), nullable=True)

    # Timeline Management
    posted_at = Column(DateTime(timezone=True), nullable=True)
    application_deadline = Column(DateTime(timezone=True), nullable=True)
    expected_start_date = Column(DateTime(timezone=True), nullable=True)
    estimated_fill_date = Column(DateTime(timezone=True), nullable=True)
    actual_fill_date = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closure_reason = Column(String(500))

    # Contact verification
    hr_contact_email = Column(String(255), nullable=False)
    hr_contact_phone = Column(String(50))
    contact_verified = Column(Boolean, default=False)
    contact_verified_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<JobPosting(id={self.id}, title='{self.title}', company_id={self.company_id})>"

    # Business logic methods
    def is_active(self) -> bool:
        """Check if job posting is active and posted"""
        return self.status == JobStatus.ACTIVE.value and self.posted_at is not None

    def days_live(self) -> int:
        """Calculate days since posting"""
        if self.posted_at is None:
            return 0
        return (datetime.utcnow() - self.posted_at).days

    def has_suspicious_activity(self) -> bool:
        """Check for ghost job red flags"""
        days_since_posted = self.days_live()

        # Red flags for ghost jobs
        if (days_since_posted > 90 and
                self.interviewed_count == 0 and
                self.applications_count > 20):
            return True

        if (self.applications_count > 100 and
                self.screened_count == 0 and
                days_since_posted > 30):
            return True

        if self.ghost_job_score is not None and self.ghost_job_score > 0.8:
            return True

        # No activity for long time
        if (self.last_activity is not None and
                (datetime.utcnow() - self.last_activity).days > 30):
            return True

        return False

    def calculate_conversion_rates(self) -> Dict[str, float]:
        """Calculate hiring funnel conversion rates"""
        rates = {}

        if self.applications_count > 0:
            rates["application_to_screen"] = self.screened_count / self.applications_count
            rates["application_to_interview"] = self.interviewed_count / self.applications_count
            rates["application_to_hire"] = self.hired_count / self.applications_count

        if self.screened_count > 0:
            rates["screen_to_interview"] = self.interviewed_count / self.screened_count

        if self.interviewed_count > 0:
            rates["interview_to_hire"] = self.hired_count / self.interviewed_count

        return rates

    def validate(self) -> List[str]:
        """Validate job posting data"""
        errors = []

        if not self.title or len(self.title) < 10 or len(self.title) > 200:
            errors.append("title must be between 10 and 200 characters")

        if not self.description or len(self.description) < 100:
            errors.append("description must be at least 100 characters")

        if not self.company_id:
            errors.append("company_id is required")

        if not self.requirements or len(self.requirements) < 3:
            errors.append("at least 3 requirements needed")

        if not self.hr_contact_email:
            errors.append("hr_contact_email is required")

        return errors

    # Property helpers for enum fields
    @property
    def job_level(self) -> Optional[JobLevel]:
        """Get JobLevel enum from string value"""
        try:
            return JobLevel(self.level) if self.level else None
        except ValueError:
            return None

    @job_level.setter
    def job_level(self, value: JobLevel):
        """Set level from JobLevel enum"""
        self.level = value.value if value else None

    @property
    def job_type(self) -> Optional[JobType]:
        """Get JobType enum from string value"""
        try:
            return JobType(self.type) if self.type else None
        except ValueError:
            return None

    @job_type.setter
    def job_type(self, value: JobType):
        """Set type from JobType enum"""
        self.type = value.value if value else None

    @property
    def job_status(self) -> Optional[JobStatus]:
        """Get JobStatus enum from string value"""
        try:
            return JobStatus(self.status) if self.status else None
        except ValueError:
            return None

    @job_status.setter
    def job_status(self, value: JobStatus):
        """Set status from JobStatus enum"""
        self.status = value.value if value else None

    @property
    def education_level_enum(self) -> Optional[EducationLevel]:
        """Get EducationLevel enum from string value"""
        try:
            return EducationLevel(self.education_level) if self.education_level else None
        except ValueError:
            return None

    @education_level_enum.setter
    def education_level_enum(self, value: EducationLevel):
        """Set education_level from EducationLevel enum"""
        self.education_level = value.value if value else None

    @property
    def verification_level_enum(self) -> Optional[VerificationLevel]:
        """Get VerificationLevel enum from string value"""
        try:
            return VerificationLevel(self.verification_level) if self.verification_level else None
        except ValueError:
            return None

    @verification_level_enum.setter
    def verification_level_enum(self, value: VerificationLevel):
        """Set verification_level from VerificationLevel enum"""
        self.verification_level = value.value if value else None


# Example usage and helper functions
def create_job_posting(
        title: str,
        description: str,
        company_id: uuid.UUID,
        hr_contact_email: str,
        level: JobLevel = JobLevel.MID,
        job_type: JobType = JobType.FULL_TIME,
        **kwargs
) -> Job:
    """Helper function to create a new job posting"""
    job = Job(
        title=title,
        description=description,
        company_id=company_id,
        hr_contact_email=hr_contact_email,
        level=level.value,
        type=job_type.value,
        education_level=EducationLevel.BACHELOR.value,
        **kwargs
    )
    return job


# Database indexes (add these as migrations)
"""
Recommended indexes for PostgreSQL:

CREATE INDEX idx_job_postings_company_id ON job_postings(company_id);
CREATE INDEX idx_job_postings_status ON job_postings(status);
CREATE INDEX idx_job_postings_posted_at ON job_postings(posted_at);
CREATE INDEX idx_job_postings_location ON job_postings(city, state, country);
CREATE INDEX idx_job_postings_level ON job_postings(level);
CREATE INDEX idx_job_postings_type ON job_postings(type);
CREATE INDEX idx_job_postings_salary ON job_postings(salary_min, salary_max);
CREATE INDEX idx_job_postings_ghost_score ON job_postings(ghost_job_score);
CREATE INDEX idx_job_postings_verification ON job_postings(verification_level);
CREATE INDEX idx_job_postings_active ON job_postings(status, posted_at) WHERE status = 'active';

-- For JSON queries
CREATE INDEX idx_job_postings_requirements_gin ON job_postings USING gin(requirements);
CREATE INDEX idx_job_postings_benefits_gin ON job_postings USING gin(benefits);
"""