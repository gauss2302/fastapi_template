from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class ApplicantBase(BaseModel):
    """Базовая схема профиля соискателя"""
    professional_title: Optional[str] = Field(None, max_length=200)
    years_of_experience: Optional[str] = Field(None, max_length=50)
    current_location: Optional[str] = Field(None, max_length=200)
    willing_to_relocate: bool = False
    remote_work_preference: Optional[str] = Field(None, regex="^(remote_only|hybrid|onsite|flexible)$")

    # Карьерные предпочтения
    desired_job_types: Optional[List[str]] = Field(default_factory=list)
    desired_salary_min: Optional[str] = Field(None, max_length=100)
    desired_salary_max: Optional[str] = Field(None, max_length=100)
    preferred_industries: Optional[List[str]] = Field(default_factory=list)

    # Контакты
    phone_number: Optional[str] = Field(None, max_length=50)
    linkedin_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None

    # Документы
    resume_url: Optional[str] = None
    cover_letter_template: Optional[str] = Field(None, max_length=2000)

    # Навыки
    skills: Optional[List[str]] = Field(default_factory=list, max_items=50)
    languages: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    education: Optional[List[Dict[str, str]]] = Field(default_factory=list)

    # Настройки
    is_actively_looking: bool = True
    is_open_to_opportunities: bool = True
    job_search_status: str = Field(default="active", regex="^(active|passive|not_looking)$")
    profile_visibility: str = Field(default="public", regex="^(public|recruiters_only|private)$")
    allow_recruiter_contact: bool = True

    additional_info: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ApplicantCreate(ApplicantBase):
    """Создание профиля соискателя"""
    # user_id будет определен автоматически из auth middleware
    pass


class ApplicantUpdate(ApplicantBase):
    """Обновление профиля соискателя"""
    professional_title: Optional[str] = Field(None, max_length=200)
    years_of_experience: Optional[str] = Field(None, max_length=50)
    current_location: Optional[str] = Field(None, max_length=200)
    willing_to_relocate: Optional[bool] = None
    remote_work_preference: Optional[str] = Field(None, regex="^(remote_only|hybrid|onsite|flexible)$")

    desired_job_types: Optional[List[str]] = None
    desired_salary_min: Optional[str] = Field(None, max_length=100)
    desired_salary_max: Optional[str] = Field(None, max_length=100)
    preferred_industries: Optional[List[str]] = None

    phone_number: Optional[str] = Field(None, max_length=50)
    linkedin_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None

    resume_url: Optional[str] = None
    cover_letter_template: Optional[str] = Field(None, max_length=2000)

    skills: Optional[List[str]] = Field(None, max_items=50)
    languages: Optional[List[Dict[str, str]]] = None
    education: Optional[List[Dict[str, str]]] = None

    is_actively_looking: Optional[bool] = None
    is_open_to_opportunities: Optional[bool] = None
    job_search_status: Optional[str] = Field(None, regex="^(active|passive|not_looking)$")
    profile_visibility: Optional[str] = Field(None, regex="^(public|recruiters_only|private)$")
    allow_recruiter_contact: Optional[bool] = None

    additional_info: Optional[Dict[str, Any]] = None


class ApplicantResponse(ApplicantBase):
    """Полный ответ с профилем соискателя"""
    id: UUID
    user_id: UUID
    profile_completeness: float = Field(..., ge=0.0, le=1.0)
    is_profile_complete: bool
    created_at: datetime
    updated_at: datetime
    last_profile_update: Optional[datetime] = None

    # Встроенная информация о пользователе
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    user_avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class ApplicantPublicProfile(BaseModel):
    """Публичный профиль соискателя (для рекрутеров)"""
    id: UUID
    professional_title: Optional[str] = None
    years_of_experience: Optional[str] = None
    current_location: Optional[str] = None
    willing_to_relocate: bool = False
    remote_work_preference: Optional[str] = None

    skills: Optional[List[str]] = Field(default_factory=list)
    preferred_industries: Optional[List[str]] = Field(default_factory=list)

    # Контакты (только если разрешено)
    linkedin_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None

    # Минимальная информация о пользователе
    display_name: str
    profile_completeness: float

    class Config:
        from_attributes = True
