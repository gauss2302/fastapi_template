from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, Integer, JSON, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database.database import Base


class JobSearchStatus(str, enum.Enum):
    """Job search status options."""
    ACTIVE = "active"
    PASSIVE = "passive"
    NOT_LOOKING = "not_looking"


class ProfileVisibility(str, enum.Enum):
    """Profile visibility options."""
    PUBLIC = "public"
    RECRUITERS_ONLY = "recruiters_only"
    PRIVATE = "private"


class RemoteWorkPreference(str, enum.Enum):
    """Remote work preference options."""
    REMOTE_ONLY = "remote_only"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    FLEXIBLE = "flexible"


class Applicant(Base):
    """Applicant profile model with modern SQLAlchemy 2.0 syntax."""

    __tablename__ = "applicants"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Foreign key to User
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True
    )

    # Professional Information
    professional_title: Mapped[Optional[str]] = mapped_column(
        String(200),
        index=True
    )
    years_of_experience: Mapped[Optional[str]] = mapped_column(String(50))
    current_location: Mapped[Optional[str]] = mapped_column(
        String(200),
        index=True
    )
    willing_to_relocate: Mapped[bool] = mapped_column(default=False)
    remote_work_preference: Mapped[RemoteWorkPreference] = mapped_column(
        default=RemoteWorkPreference.FLEXIBLE
    )

    # Career Preferences
    desired_job_types: Mapped[List[str]] = mapped_column(
        JSON,
        default=list
    )
    desired_salary_min: Mapped[Optional[int]]
    desired_salary_max: Mapped[Optional[int]]
    desired_salary_currency: Mapped[str] = mapped_column(
        String(3),
        default='USD'
    )
    preferred_industries: Mapped[List[str]] = mapped_column(
        JSON,
        default=list
    )

    # Contact Information
    phone_number: Mapped[Optional[str]] = mapped_column(String(50))
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text)
    github_url: Mapped[Optional[str]] = mapped_column(Text)
    portfolio_url: Mapped[Optional[str]] = mapped_column(Text)

    # Documents
    resume_url: Mapped[Optional[str]] = mapped_column(Text)
    cover_letter_template: Mapped[Optional[str]] = mapped_column(Text)

    # Skills and Education (structured as JSON)
    skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    languages: Mapped[List[Dict[str, str]]] = mapped_column(
        JSON,
        default=list
    )  # [{"language": "English", "level": "Native"}]
    education: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list
    )

    # Profile Settings
    is_actively_looking: Mapped[bool] = mapped_column(
        default=True,
        index=True
    )
    is_open_to_opportunities: Mapped[bool] = mapped_column(default=True)
    job_search_status: Mapped[JobSearchStatus] = mapped_column(
        default=JobSearchStatus.ACTIVE,
        index=True
    )
    profile_visibility: Mapped[ProfileVisibility] = mapped_column(
        default=ProfileVisibility.PUBLIC
    )
    allow_recruiter_contact: Mapped[bool] = mapped_column(default=True)

    # Profile Metrics
    profile_views_count: Mapped[int] = mapped_column(default=0)
    profile_completeness: Mapped[int] = mapped_column(default=0)

    # Additional Information
    additional_info: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now()
    )
    last_profile_update: Mapped[Optional[datetime]]

    # Relationships with type annotations
    user: Mapped["User"] = relationship("User", back_populates="applicant_profile")
    
    applications: Mapped[List["Application"]] = relationship(
        "Application",
        back_populates="applicant",
        cascade="all, delete-orphan",  # При удалении applicant, удаляются и заявки
        lazy="select"
    )

    # Table constraints and indexes
    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_applicants_location_status", "current_location", "job_search_status"),
        Index("ix_applicants_title_status", "professional_title", "is_actively_looking"),
        Index("ix_applicants_visibility_looking", "profile_visibility", "is_actively_looking"),

        # Check constraints
        CheckConstraint(
            "profile_completeness >= 0 AND profile_completeness <= 100",
            name="check_profile_completeness_range"
        ),
        CheckConstraint(
            "profile_views_count >= 0",
            name="check_profile_views_positive"
        ),
        CheckConstraint(
            "desired_salary_min IS NULL OR desired_salary_min >= 0",
            name="check_min_salary_positive"
        ),
        CheckConstraint(
            "desired_salary_max IS NULL OR desired_salary_max >= 0",
            name="check_max_salary_positive"
        ),
        CheckConstraint(
            "desired_salary_min IS NULL OR desired_salary_max IS NULL OR desired_salary_min <= desired_salary_max",
            name="check_salary_range_valid"
        ),
        CheckConstraint(
            "LENGTH(desired_salary_currency) = 3",
            name="check_currency_code_length"
        ),
    )

    def __repr__(self) -> str:
        return (f"<Applicant(id={self.id}, user_id={self.user_id}, "
                f"professional_title='{self.professional_title}')>")

    def calculate_profile_completeness(self) -> int:
        """Calculate profile completeness percentage."""
        total_fields = 15
        completed_fields = 0

        # Required basic fields
        if self.professional_title:
            completed_fields += 1
        if self.years_of_experience:
            completed_fields += 1
        if self.current_location:
            completed_fields += 1
        if self.skills and len(self.skills) >= 3:
            completed_fields += 1
        if self.desired_job_types and len(self.desired_job_types) >= 1:
            completed_fields += 1

        # Contact fields
        if self.phone_number:
            completed_fields += 1
        if self.linkedin_url:
            completed_fields += 1

        # Documents
        if self.resume_url:
            completed_fields += 2  # Resume is worth 2 points
        if self.cover_letter_template:
            completed_fields += 1

        # Education and experience
        if self.education and len(self.education) >= 1:
            completed_fields += 1
        if self.languages and len(self.languages) >= 1:
            completed_fields += 1

        # Preferences
        if self.desired_salary_min or self.desired_salary_max:
            completed_fields += 1
        if self.preferred_industries and len(self.preferred_industries) >= 1:
            completed_fields += 1
        if self.portfolio_url:
            completed_fields += 1

        return min(100, int((completed_fields / total_fields) * 100))

    def update_profile_completeness(self) -> None:
        """Update profile completeness score and last update timestamp."""
        self.profile_completeness = self.calculate_profile_completeness()
        self.last_profile_update = datetime.utcnow()

    def increment_profile_views(self) -> None:
        """Increment profile view count."""
        self.profile_views_count += 1

    def set_salary_range(
            self,
            min_salary: Optional[int] = None,
            max_salary: Optional[int] = None,
            currency: str = "USD"
    ) -> None:
        """Set salary range with validation."""
        if min_salary is not None and min_salary < 0:
            raise ValueError("Minimum salary cannot be negative")
        if max_salary is not None and max_salary < 0:
            raise ValueError("Maximum salary cannot be negative")
        if (min_salary is not None and max_salary is not None and
                min_salary > max_salary):
            raise ValueError("Minimum salary cannot exceed maximum salary")
        if len(currency) != 3:
            raise ValueError("Currency code must be 3 characters")

        self.desired_salary_min = min_salary
        self.desired_salary_max = max_salary
        self.desired_salary_currency = currency.upper()

    def add_skill(self, skill: str) -> None:
        """Add a skill to the skills list."""
        if not skill or not skill.strip():
            raise ValueError("Skill cannot be empty")

        skill = skill.strip().title()
        if skill not in self.skills:
            self.skills = self.skills + [skill]

    def remove_skill(self, skill: str) -> None:
        """Remove a skill from the skills list."""
        if skill in self.skills:
            skills_list = list(self.skills)
            skills_list.remove(skill)
            self.skills = skills_list

    def add_language(self, language: str, level: str) -> None:
        """Add a language with proficiency level."""
        valid_levels = ["Beginner", "Intermediate", "Advanced", "Native", "Professional"]
        if level not in valid_levels:
            raise ValueError(f"Language level must be one of: {', '.join(valid_levels)}")

        # Remove existing entry for this language
        languages_list = [lang for lang in self.languages if lang.get("language") != language]
        languages_list.append({"language": language, "level": level})
        self.languages = languages_list

    def add_education(
            self,
            institution: str,
            degree: str,
            field_of_study: Optional[str] = None,
            start_year: Optional[int] = None,
            end_year: Optional[int] = None,
            gpa: Optional[float] = None
    ) -> None:
        """Add education entry."""
        if not institution or not degree:
            raise ValueError("Institution and degree are required")

        education_entry = {
            "institution": institution,
            "degree": degree,
            "field_of_study": field_of_study,
            "start_year": start_year,
            "end_year": end_year,
            "gpa": gpa
        }

        education_list = list(self.education)
        education_list.append(education_entry)
        self.education = education_list

    def update_job_search_status(self, status: JobSearchStatus) -> None:
        """Update job search status and related flags."""
        self.job_search_status = status

        # Auto-update related flags based on status
        if status == JobSearchStatus.ACTIVE:
            self.is_actively_looking = True
            self.is_open_to_opportunities = True
        elif status == JobSearchStatus.PASSIVE:
            self.is_actively_looking = False
            self.is_open_to_opportunities = True
        elif status == JobSearchStatus.NOT_LOOKING:
            self.is_actively_looking = False
            self.is_open_to_opportunities = False

    # Properties
    @property
    def is_profile_complete(self) -> bool:
        """Check if profile is considered complete (>= 70%)."""
        return self.profile_completeness >= 70

    @property
    def salary_range_formatted(self) -> Optional[str]:
        """Get formatted salary range string."""
        if not self.desired_salary_min and not self.desired_salary_max:
            return None

        if self.desired_salary_min and self.desired_salary_max:
            return (f"{self.desired_salary_currency} {self.desired_salary_min:,} - "
                    f"{self.desired_salary_max:,}")
        elif self.desired_salary_min:
            return f"{self.desired_salary_currency} {self.desired_salary_min:,}+"
        else:
            return f"Up to {self.desired_salary_currency} {self.desired_salary_max:,}"

    @property
    def has_contact_info(self) -> bool:
        """Check if applicant has provided contact information."""
        return bool(self.phone_number or self.linkedin_url or self.github_url)

    @property
    def has_documents(self) -> bool:
        """Check if applicant has uploaded documents."""
        return bool(self.resume_url or self.cover_letter_template)

    @property
    def skill_count(self) -> int:
        """Get number of skills."""
        return len(self.skills) if self.skills else 0

    @property
    def language_count(self) -> int:
        """Get number of languages."""
        return len(self.languages) if self.languages else 0

    @property
    def education_count(self) -> int:
        """Get number of education entries."""
        return len(self.education) if self.education else 0

    # Validation methods
    def can_be_contacted_by_recruiters(self) -> bool:
        """Check if recruiters can contact this applicant."""
        return (self.allow_recruiter_contact and
                self.profile_visibility in [ProfileVisibility.PUBLIC, ProfileVisibility.RECRUITERS_ONLY] and
                self.is_open_to_opportunities)

    def is_visible_to_public(self) -> bool:
        """Check if profile is visible to public."""
        return self.profile_visibility == ProfileVisibility.PUBLIC

    def is_searchable(self) -> bool:
        """Check if profile should appear in search results."""
        return (self.profile_visibility != ProfileVisibility.PRIVATE and
                self.is_open_to_opportunities and
                self.is_profile_complete)