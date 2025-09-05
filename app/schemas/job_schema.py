from pydantic import BaseModel, Field, EmailStr, validator, HttpUrl
from typing import Optional, List
from datetime import datetime
import uuid
from enum import Enum


class JobLevel(str, Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class JobType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"


class WorkingType(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class JobStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    FILLED = "filled"
    CANCELLED = "cancelled"


# Base schema
class JobPostingBase(BaseModel):
    """Базовая схема для удаленной работы"""
    title: str = Field(..., min_length=10, max_length=200, description="Job title")
    description: str = Field(..., min_length=100, description="Detailed job description")
    company_name: str = Field(..., min_length=2, max_length=100, description="Company name")

    level: JobLevel = Field(..., description="Job level/seniority")
    type: JobType = Field(..., description="Employment type")
    working_type: WorkingType = Field(default=WorkingType.REMOTE, description="Remote/hybrid/onsite")

    # Location & Remote Work
    timezone: Optional[str] = Field(None, max_length=50, description="Preferred timezone, e.g. 'UTC+3', 'PST'")
    location_restrictions: Optional[List[str]] = Field(
        default_factory=list,
        max_items=10,
        description="Countries/regions where candidates must be located"
    )

    # Compensation
    salary_min: Optional[int] = Field(None, ge=0, le=1000000, description="Minimum salary")
    salary_max: Optional[int] = Field(None, ge=0, le=1000000, description="Maximum salary")
    salary_currency: str = Field(default="USD", max_length=3, description="ISO currency code")

    # Core requirements
    requirements: List[str] = Field(
        ...,
        min_items=3,
        max_items=15,
        description="List of job requirements"
    )
    skills: List[str] = Field(
        default_factory=list,
        max_items=20,
        description="Required or preferred skills"
    )
    experience_years: Optional[int] = Field(None, ge=0, le=20, description="Years of experience required")

    # Contact
    contact_email: EmailStr = Field(..., description="Contact email for applications")
    apply_url: Optional[HttpUrl] = Field(None, description="External application URL")

    @validator('salary_max')
    def validate_salary_range(cls, v, values):
        if v and 'salary_min' in values and values['salary_min']:
            if v < values['salary_min']:
                raise ValueError('salary_max must be >= salary_min')
            # Check for unrealistic ranges
            if v > values['salary_min'] * 5:
                raise ValueError('salary_max cannot be more than 5x salary_min')
        return v

    @validator('requirements')
    def validate_requirements(cls, v):
        if not v:
            raise ValueError('Requirements cannot be empty')

        for req in v:
            if not req.strip():
                raise ValueError('Requirements cannot contain empty strings')
            if len(req) > 200:
                raise ValueError('Each requirement must be ≤ 200 characters')

        # Check for duplicates
        if len(set(v)) != len(v):
            raise ValueError('Requirements cannot contain duplicates')

        return v

    @validator('skills')
    def validate_skills(cls, v):
        if v:
            for skill in v:
                if not skill.strip():
                    raise ValueError('Skills cannot contain empty strings')
                if len(skill) > 50:
                    raise ValueError('Each skill must be ≤ 50 characters')

            # Check for duplicates
            if len(set(v)) != len(v):
                raise ValueError('Skills cannot contain duplicates')

        return v

    @validator('location_restrictions')
    def validate_location_restrictions(cls, v):
        if v:
            for location in v:
                if not location.strip():
                    raise ValueError('Location restrictions cannot contain empty strings')
                if len(location) > 100:
                    raise ValueError('Each location must be ≤ 100 characters')
        return v

    @validator('title')
    def validate_title(cls, v):
        if not v.strip():
            raise ValueError('Title cannot be empty or whitespace only')

        # Check for spam patterns
        spam_indicators = ['$$$', '!!!', 'URGENT!!!', 'EARN $', 'MAKE MONEY']
        title_upper = v.upper()
        for indicator in spam_indicators:
            if indicator in title_upper:
                raise ValueError(f'Title contains spam pattern: {indicator}')

        return v.strip()


class JobPostingCreate(JobPostingBase):
    """Создание новой вакансии"""

    class Config:
        schema_extra = {
            "example": {
                "title": "Senior Python Developer",
                "description": "We are looking for an experienced Python developer to join our remote team. You will work on building scalable web applications using Django/FastAPI, collaborate with our product team, and mentor junior developers. Our tech stack includes Python, PostgreSQL, Redis, and AWS. This is a fully remote position with flexible working hours.",
                "company_name": "TechCorp Inc",
                "level": "senior",
                "type": "full_time",
                "working_type": "remote",
                "timezone": "UTC-5 to UTC+3",
                "location_restrictions": ["USA", "Canada", "EU", "UK"],
                "salary_min": 80000,
                "salary_max": 120000,
                "salary_currency": "USD",
                "requirements": [
                    "5+ years of Python development experience",
                    "Strong experience with Django or FastAPI",
                    "Proficiency with PostgreSQL and Redis",
                    "Experience with AWS or similar cloud platforms",
                    "Excellent English communication skills"
                ],
                "skills": ["Python", "Django", "FastAPI", "PostgreSQL", "Redis", "AWS", "Docker"],
                "experience_years": 5,
                "contact_email": "jobs@techcorp.com",
                "apply_url": "https://techcorp.com/careers/python-developer"
            }
        }


class JobPostingUpdate(BaseModel):
    """Обновление вакансии - все поля опциональные"""
    title: Optional[str] = Field(None, min_length=10, max_length=200)
    description: Optional[str] = Field(None, min_length=100)
    company_name: Optional[str] = Field(None, min_length=2, max_length=100)

    level: Optional[JobLevel] = None
    type: Optional[JobType] = None
    working_type: Optional[WorkingType] = None

    timezone: Optional[str] = Field(None, max_length=50)
    location_restrictions: Optional[List[str]] = Field(None, max_items=10)

    salary_min: Optional[int] = Field(None, ge=0, le=1000000)
    salary_max: Optional[int] = Field(None, ge=0, le=1000000)
    salary_currency: Optional[str] = Field(None, max_length=3)

    requirements: Optional[List[str]] = Field(None, min_items=3, max_items=15)
    skills: Optional[List[str]] = Field(None, max_items=20)
    experience_years: Optional[int] = Field(None, ge=0, le=20)

    contact_email: Optional[EmailStr] = None
    apply_url: Optional[HttpUrl] = None

    # Same validators as create but for optional fields
    @validator('salary_max')
    def validate_salary_range(cls, v, values):
        if v and 'salary_min' in values and values['salary_min']:
            if v < values['salary_min']:
                raise ValueError('salary_max must be >= salary_min')
            if v > values['salary_min'] * 5:
                raise ValueError('salary_max cannot be more than 5x salary_min')
        return v


class JobPostingResponse(JobPostingBase):
    """Полный ответ с информацией о вакансии"""
    id: uuid.UUID
    slug: str = Field(..., description="SEO-friendly URL slug")
    created_at: datetime
    updated_at: datetime
    status: JobStatus = JobStatus.DRAFT
    posted_at: Optional[datetime] = None

    # Статистика
    views_count: int = Field(default=0, ge=0, description="Number of views")
    applications_count: int = Field(default=0, ge=0, description="Number of applications")

    class Config:
        from_attributes = True


class JobPostingListItem(BaseModel):
    """Краткая информация для списков вакансий"""
    id: uuid.UUID
    slug: str
    title: str
    company_name: str
    level: JobLevel
    type: JobType
    working_type: WorkingType

    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: str

    location_restrictions: List[str]
    skills: List[str]

    posted_at: Optional[datetime]
    views_count: int = 0

    class Config:
        from_attributes = True


class JobSearchRequest(BaseModel):
    """Параметры поиска удаленной работы"""
    # Text search
    query: Optional[str] = Field(None, max_length=200, description="Search in title and description")

    # Filters
    level: Optional[List[JobLevel]] = Field(None, max_items=5)
    type: Optional[List[JobType]] = Field(None, max_items=4)
    working_type: Optional[List[WorkingType]] = Field(None, max_items=3)

    company_name: Optional[str] = Field(None, max_length=100, description="Filter by company name")

    # Salary filters
    salary_min: Optional[int] = Field(None, ge=0, description="Minimum salary requirement")
    salary_max: Optional[int] = Field(None, ge=0, description="Maximum salary expectation")
    salary_currency: Optional[str] = Field(None, max_length=3, description="Salary currency")

    # Skills and experience
    skills: Optional[List[str]] = Field(None, max_items=10, description="Required skills")
    experience_max: Optional[int] = Field(None, ge=0, le=20, description="Maximum experience required")

    # Location filters
    timezone: Optional[str] = Field(None, max_length=50)
    location_allowed: Optional[str] = Field(None, max_length=100, description="Must allow this location")

    # Date filters
    posted_after: Optional[datetime] = Field(None, description="Posted after this date")
    posted_before: Optional[datetime] = Field(None, description="Posted before this date")

    # Special filters
    has_salary: Optional[bool] = Field(None, description="Only jobs with salary information")
    remote_only: Optional[bool] = Field(None, description="Only remote jobs")

    # Pagination
    page: int = Field(default=1, ge=1, description="Page number")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")

    # Sorting
    sort_by: str = Field(
        default="posted_at",
        regex="^(posted_at|created_at|salary_min|title|views_count|applications_count)$",
        description="Sort field"
    )
    sort_order: str = Field(default="desc", regex="^(asc|desc)$", description="Sort direction")

    @validator('posted_before')
    def validate_date_range(cls, v, values):
        if v and 'posted_after' in values and values['posted_after']:
            if v <= values['posted_after']:
                raise ValueError('posted_before must be after posted_after')
        return v


class JobSearchResponse(BaseModel):
    """Результаты поиска с пагинацией"""
    jobs: List[JobPostingListItem]
    total: int = Field(..., ge=0, description="Total number of jobs matching criteria")
    page: int = Field(..., ge=1, description="Current page")
    limit: int = Field(..., ge=1, description="Items per page")
    pages: int = Field(..., ge=0, description="Total number of pages")
    has_next: bool = Field(..., description="Whether there are more pages")
    has_prev: bool = Field(..., description="Whether there are previous pages")


class JobStatusUpdate(BaseModel):
    """Изменение статуса вакансии"""
    status: JobStatus = Field(..., description="New job status")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for status change")


class JobStats(BaseModel):
    """Статистика по вакансии"""
    id: uuid.UUID
    title: str
    company_name: str
    status: JobStatus

    views_count: int = Field(..., ge=0)
    applications_count: int = Field(..., ge=0)

    days_live: int = Field(..., ge=0, description="Days since posting")
    posted_at: Optional[datetime]

    # Conversion metrics
    view_to_application_rate: Optional[float] = Field(None, ge=0, le=1, description="Applications per view")


class CompanyJobsResponse(BaseModel):
    """Все вакансии компании"""
    company_name: str
    active_jobs: List[JobPostingListItem]
    total_jobs: int = Field(..., ge=0)
    total_active: int = Field(..., ge=0)


class JobPostingPublish(BaseModel):
    """Параметры для публикации вакансии"""
    publish_immediately: bool = Field(default=True, description="Publish job immediately")
    scheduled_date: Optional[datetime] = Field(None, description="Schedule publication for later")

    @validator('scheduled_date')
    def validate_scheduled_date(cls, v, values):
        if not values.get('publish_immediately') and not v:
            raise ValueError('scheduled_date is required when publish_immediately is False')

        if v and v <= datetime.utcnow():
            raise ValueError('scheduled_date must be in the future')

        return v


class JobPostingClone(BaseModel):
    """Параметры для клонирования вакансии"""
    new_title: Optional[str] = Field(None, min_length=10, max_length=200, description="New title for cloned job")
    new_company_name: Optional[str] = Field(None, min_length=2, max_length=100, description="New company name")

    # Fields to modify during cloning
    modify_level: Optional[JobLevel] = None
    modify_type: Optional[JobType] = None
    modify_salary_min: Optional[int] = Field(None, ge=0)
    modify_salary_max: Optional[int] = Field(None, ge=0)

    copy_as_draft: bool = Field(default=True, description="Clone as draft (recommended)")


class JobValidationError(BaseModel):
    """Ошибка валидации"""
    field: str = Field(..., description="Field name with error")
    message: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code for programmatic handling")


class JobValidationResponse(BaseModel):
    """Результат валидации вакансии"""
    is_valid: bool = Field(..., description="Whether job posting is valid")
    errors: List[JobValidationError] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list, description="Non-critical issues")

    # Quality metrics
    title_quality_score: Optional[float] = Field(None, ge=0, le=1, description="Title quality (0-1)")
    description_quality_score: Optional[float] = Field(None, ge=0, le=1, description="Description quality (0-1)")
    overall_quality_score: Optional[float] = Field(None, ge=0, le=1, description="Overall quality (0-1)")


class BulkJobOperation(BaseModel):
    """Массовые операции над вакансиями"""
    job_ids: List[uuid.UUID] = Field(..., min_items=1, max_items=50, description="Job IDs to operate on")
    operation: str = Field(..., regex="^(delete|publish|pause|activate|archive)$", description="Operation to perform")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for bulk operation")


class BulkOperationResult(BaseModel):
    """Результат массовой операции"""
    success_count: int = Field(..., ge=0)
    error_count: int = Field(..., ge=0)
    errors: List[str] = Field(default_factory=list, description="Error messages for failed operations")
    processed_ids: List[uuid.UUID] = Field(default_factory=list, description="Successfully processed job IDs")


# Export all schemas
__all__ = [
    # Enums
    "JobLevel", "JobType", "WorkingType", "JobStatus",

    # Main schemas
    "JobPostingBase", "JobPostingCreate", "JobPostingUpdate",
    "JobPostingResponse", "JobPostingListItem",

    # Search
    "JobSearchRequest", "JobSearchResponse",

    # Operations
    "JobStatusUpdate", "JobPostingPublish", "JobPostingClone",

    # Analytics
    "JobStats", "CompanyJobsResponse",

    # Validation
    "JobValidationError", "JobValidationResponse",

    # Bulk operations
    "BulkJobOperation", "BulkOperationResult"
]