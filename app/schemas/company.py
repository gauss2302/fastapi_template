from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum

from app.models.company import CompanyStatus, CompanySize


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    website: Optional[HttpUrl] = None
    industry: Optional[str] = Field(None, max_length=100)
    company_size: Optional[CompanySize] = None
    founded_year: Optional[int] = Field(None, ge=1800, le=2024)
    headquarters: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    linkedin_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None


class CompanyCreate(CompanyBase):
    verification_document_url: Optional[str] = None

    @field_validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Company name cannot be empty')
        return v.strip()


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    website: Optional[HttpUrl] = None
    industry: Optional[str] = Field(None, max_length=100)
    company_size: Optional[CompanySize] = None
    founded_year: Optional[int] = Field(None, ge=1800, le=2024)
    headquarters: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    linkedin_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    is_hiring: Optional[bool] = None
    allow_applications: Optional[bool] = None


class CompanyVerification(BaseModel):
    status: CompanyStatus
    verification_notes: Optional[str] = Field(None, max_length=1000)


class Company(CompanyBase):
    id: UUID
    slug: str
    status: CompanyStatus
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_active: bool
    is_hiring: bool
    allow_applications: bool
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CompanyPublic(BaseModel):
    """Public company information for job seekers"""
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    website: Optional[HttpUrl] = None
    industry: Optional[str] = None
    company_size: Optional[CompanySize] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_hiring: bool
    linkedin_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None

    class Config:
        from_attributes = True


class CompanySearchFilters(BaseModel):
    """Search filters for companies"""
    industry: Optional[str] = None
    company_size: Optional[CompanySize] = None
    location: Optional[str] = None
    is_hiring: Optional[bool] = None
    verified_only: bool = True


class CompanyStats(BaseModel):
    """Company statistics"""
    # Company stats
    total_companies: Optional[int] = None
    verified_companies: Optional[int] = None
    pending_companies: Optional[int] = None
    active_companies: Optional[int] = None
    hiring_companies: Optional[int] = None

    # Recruiter stats (from recruiter repository)
    total_recruiters: Optional[int] = None
    active_recruiters: Optional[int] = None
    approved_recruiters: Optional[int] = None
    pending_recruiters: Optional[int] = None

    class Config:
        from_attributes = True


class CompanyRegistrationRequest(CompanyCreate):
    """Request to register a new company"""
    terms_accepted: bool = Field(..., description="Must accept terms and conditions")

    @field_validator('terms_accepted')
    def validate_terms(cls, v):
        if not v:
            raise ValueError('Terms and conditions must be accepted')
        return v


# Response models for API
class CompanyListResponse(BaseModel):
    """Response for company list endpoints"""
    companies: list[Company]
    total: int
    skip: int
    limit: int


class CompanyPublicListResponse(BaseModel):
    """Response for public company list endpoints"""
    companies: list[CompanyPublic]
    total: int
    skip: int
    limit: int