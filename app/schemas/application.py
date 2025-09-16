from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class ApplicationStatus(str, Enum):
    """Application status enum."""
    PENDING = "pending"
    SCREENING = "screening"
    INTERVIEWED = "interviewed"
    TECHNICAL_TEST = "technical_test"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationSource(str, Enum):
    """How the application was submitted."""
    WEBSITE = "website"
    MOBILE_APP = "mobile_app"
    REFERRAL = "referral"
    LINKEDIN = "linkedin"
    EMAIL = "email"


class ApplicationBase(BaseModel):
    """Base application schema."""
    # Core IDs - using UUID instead of str for consistency with your project
    job_id: UUID = Field(..., description="ID of the job being applied to")

    # Optional fields that may be set during creation
    cover_letter: Optional[str] = Field(None, max_length=2000, description="Applicant's cover letter")
    resume_url: Optional[str] = Field(None, description="URL to uploaded resume")
    portfolio_url: Optional[str] = Field(None, description="Portfolio or personal website URL")

    # Application source tracking
    source: ApplicationSource = Field(default=ApplicationSource.WEBSITE, description="How application was submitted")
    referrer_user_id: Optional[UUID] = Field(None, description="User ID who referred this applicant")

    # Additional data (flexible field for custom questions, etc.)
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom application data")

    @field_validator('cover_letter')
    @classmethod
    def validate_cover_letter(cls, v):
        if v and len(v.strip()) < 50:
            raise ValueError('Cover letter must be at least 50 characters')
        return v

    @field_validator('additional_data')
    @classmethod
    def validate_additional_data(cls, v):
        if v and len(str(v)) > 5000:  # Limit JSON size
            raise ValueError('Additional data too large')
        return v


class Application(ApplicationBase):
    """Полная заявка (модель для хранения в БД)."""

    application_id: UUID = Field(..., description="ID самой заявки")
    applicant_id: UUID = Field(..., description="ID соискателя")
    company_id: UUID = Field(..., description="ID компании")
    recruiter_id: Optional[UUID] = Field(None, description="ID рекрутера")

    # Текущий статус заявки
    status: ApplicationStatus = Field(default=ApplicationStatus.PENDING, description="Статус заявки")

    # Служебные поля
    applied_at: datetime = Field(default_factory=datetime.utcnow, description="Дата подачи заявки")
    last_updated_at: datetime = Field(default_factory=datetime.utcnow, description="Когда последний раз обновляли")

    # Доп. инфо от рекрутера
    recruiter_notes: Optional[str] = Field(None, max_length=1000, description="Заметки рекрутера")
    interview_scheduled_at: Optional[datetime] = Field(None, description="Назначенное интервью")
    rejection_reason: Optional[str] = Field(None, max_length=500, description="Причина отказа")
    offer_details: Optional[Dict[str, Any]] = Field(None, description="Детали оффера")

    class Config:
        from_attributes = True


class ApplicationCreate(BaseModel):
    """Создание заявки (applicant_id определится автоматически)"""
    job_id: UUID = Field(..., description="ID вакансии")
    cover_letter: Optional[str] = Field(None, max_length=2000)
    source: ApplicationSource = Field(default=ApplicationSource.WEBSITE)
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ApplicationUpdate(BaseModel):
    """Schema for updating application (recruiter use)."""
    status: Optional[ApplicationStatus] = None
    recruiter_notes: Optional[str] = Field(None, max_length=1000)
    interview_scheduled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = Field(None, max_length=500)
    offer_details: Optional[Dict[str, Any]] = None


class ApplicationResponse(BaseModel):
    """Полный ответ с заявкой"""
    id: UUID
    applicant_id: UUID
    job_id: UUID
    company_id: UUID
    recruiter_id: Optional[UUID] = None

    # Информация о соискателе (встроенная)
    applicant_name: str
    applicant_email: str
    applicant_professional_title: Optional[str] = None
    applicant_phone: Optional[str] = None
    applicant_resume_url: Optional[str] = None

    # Информация о вакансии (встроенная)
    job_title: str
    job_company_name: str
    job_level: str
    job_type: str

    # Детали заявки
    cover_letter: Optional[str] = None
    source: ApplicationSource
    status: ApplicationStatus
    applied_at: datetime
    last_updated_at: datetime

    # Процесс обработки
    recruiter_notes: Optional[str] = None
    viewed_at: Optional[datetime] = None
    interview_scheduled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApplicationListItem(BaseModel):
    """Simplified application for lists."""
    id: UUID
    job_id: UUID
    job_title: str
    job_company_name: str
    status: ApplicationStatus
    applied_at: datetime
    last_updated_at: datetime

    # For recruiter view
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None

    class Config:
        from_attributes = True


class UserApplicationResponse(ApplicationResponse):
    """Application response for user (applicant) view."""
    # Hide sensitive recruiter information
    recruiter_notes: Optional[str] = Field(None, exclude=True)

    # Only show basic status info
    status: ApplicationStatus
    status_message: Optional[str] = None  # User-friendly status message


class RecruiterApplicationResponse(ApplicationResponse):
    """Application response for recruiter view with applicant details."""
    # Applicant information
    applicant_name: str
    applicant_email: str
    applicant_avatar_url: Optional[str] = None

    # Resume and portfolio
    resume_url: Optional[str] = None
    portfolio_url: Optional[str] = None

    # Full recruiter information
    recruiter_notes: Optional[str] = None
    internal_rating: Optional[int] = Field(None, ge=1, le=5)


class ApplicationStats(BaseModel):
    """Application statistics."""
    total_applications: int
    by_status: Dict[ApplicationStatus, int]
    by_source: Dict[ApplicationSource, int]
    recent_applications: int  # Last 30 days
    conversion_rates: Dict[str, float]


class ApplicationFilters(BaseModel):
    """Filters for searching applications."""
    status: Optional[List[ApplicationStatus]] = None
    source: Optional[List[ApplicationSource]] = None
    job_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    recruiter_id: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    has_cover_letter: Optional[bool] = None
    has_portfolio: Optional[bool] = None


class ApplicationSearchRequest(BaseModel):
    """Search request for applications."""
    filters: Optional[ApplicationFilters] = None
    search_query: Optional[str] = Field(None, max_length=200)  # Search in name, email, cover letter
    sort_by: str = Field(default="applied_at", pattern="^(applied_at|last_updated_at|status)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class ApplicationSearchResponse(BaseModel):
    """Search response with pagination."""
    applications: List[ApplicationListItem]
    total: int
    page: int
    limit: int
    pages: int
    has_next: bool
    has_prev: bool


class ApplicationStatusUpdate(BaseModel):
    """Schema for updating application status."""
    status: ApplicationStatus
    notes: Optional[str] = Field(None, max_length=1000)
    reason: Optional[str] = Field(None, max_length=500)  # For rejections

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v, values):
        if values.get('status') == ApplicationStatus.REJECTED and not v:
            raise ValueError('Rejection reason is required')
        return v


class BulkApplicationUpdate(BaseModel):
    """Schema for bulk operations on applications."""
    application_ids: List[UUID] = Field(..., min_items=1, max_items=50)
    action: str = Field(..., pattern="^(reject|move_to_screening|move_to_interview|archive)$")
    notes: Optional[str] = Field(None, max_length=1000)
    reason: Optional[str] = Field(None, max_length=500)


class ApplicationNotification(BaseModel):
    """Notification about application status change."""
    application_id: UUID
    job_title: str
    company_name: str
    old_status: ApplicationStatus
    new_status: ApplicationStatus
    message: str
    sent_at: datetime
