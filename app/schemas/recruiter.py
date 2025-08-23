from pydantic import BaseModel, EmailStr, Field, field_validator, HttpUrl
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from app.models.recruiter import RecruiterStatus


class RecruiterBase(BaseModel):
    position: Optional[str] = Field(None, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    contact_email: Optional[EmailStr] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    linkedin_profile: Optional[HttpUrl] = None


class RecruiterCreate(RecruiterBase):
    company_id: UUID


class RecruiterUpdate(RecruiterBase):
    pass


class RecruiterPermissions(BaseModel):
    can_approve_recruiters: bool = False
    can_post_jobs: bool = True
    can_view_analytics: bool = False
    can_manage_company: bool = False


class RecruiterApproval(BaseModel):
    status: RecruiterStatus
    rejection_reason: Optional[str] = Field(None, max_length=500)

    @field_validator('rejection_reason')
    def validate_rejection_reason(cls, v, values):
        if values.get('status') == RecruiterStatus.REJECTED and not v:
            raise ValueError('Rejection reason is required when rejecting a recruiter')
        return v


class RecruiterInvitationRequest(BaseModel):
    """Request to invite a recruiter to company"""
    email: EmailStr = Field(..., max_length=255)
    position: Optional[str] = Field(None, max_length=100)
    permissions: Optional[RecruiterPermissions] = None
    personal_message: Optional[str] = Field(None, max_length=500)


# Basic user info for embedding in recruiter responses
class UserBasicInfo(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


# Basic company info for embedding in recruiter responses
class CompanyBasicInfo(BaseModel):
    id: UUID
    name: str
    slug: str
    logo_url: Optional[str] = None
    industry: Optional[str] = None

    class Config:
        from_attributes = True


class Recruiter(RecruiterBase):
    id: UUID
    user_id: UUID
    company_id: UUID
    status: RecruiterStatus
    can_approve_recruiters: bool
    can_post_jobs: bool
    can_view_analytics: bool
    can_manage_company: bool
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    is_active: bool
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @property
    def permission_level(self) -> str:
        """Get permission level as string"""
        if self.can_manage_company:
            return "admin"
        elif self.can_approve_recruiters:
            return "senior"
        elif self.can_post_jobs:
            return "recruiter"
        else:
            return "viewer"


class RecruiterWithUser(Recruiter):
    """Recruiter with user information"""
    user: UserBasicInfo

    class Config:
        from_attributes = True


class RecruiterWithCompany(Recruiter):
    """Recruiter with company information"""
    company: CompanyBasicInfo

    class Config:
        from_attributes = True


class RecruiterFull(Recruiter):
    """Recruiter with full user and company information"""
    user: UserBasicInfo
    company: CompanyBasicInfo

    class Config:
        from_attributes = True


class RecruiterSearchFilters(BaseModel):
    """Search filters for recruiters"""
    company_id: Optional[UUID] = None
    search_term: Optional[str] = None
    status: Optional[RecruiterStatus] = None
    department: Optional[str] = None
    position: Optional[str] = None
    has_permissions: Optional[list[str]] = None  # ["approve_recruiters", "manage_company"]


class RecruiterStats(BaseModel):
    """Recruiter statistics"""
    total_recruiters: int
    approved_recruiters: int
    pending_recruiters: int
    rejected_recruiters: int
    active_recruiters: int

    class Config:
        from_attributes = True


class RecruiterDepartmentStats(BaseModel):
    """Recruiter statistics by department"""
    department_stats: Dict[str, int]
    total_departments: int

    class Config:
        from_attributes = True


# Response models for API endpoints
class RecruiterListResponse(BaseModel):
    """Response for recruiter list endpoints"""
    recruiters: list[RecruiterFull]
    total: int
    skip: int
    limit: int
    filters: Optional[Dict[str, Any]] = None


class RecruiterInvitationResponse(BaseModel):
    """Response for recruiter invitation"""
    status: str  # "invited", "signup_invitation_sent"
    recruiter_id: Optional[UUID] = None
    email: Optional[str] = None
    message: str


class RecruiterBulkOperationResponse(BaseModel):
    """Response for bulk recruiter operations"""
    success_count: int
    total_requested: int
    failed_count: Optional[int] = None
    errors: Optional[list[Dict[str, Any]]] = None


# Admin-specific schemas
class RecruiterAdminView(RecruiterFull):
    """Extended recruiter view for admins"""
    approved_by: Optional[UUID] = None
    verification_notes: Optional[str] = None

    class Config:
        from_attributes = True


class GlobalRecruiterStats(BaseModel):
    """Global platform recruiter statistics"""
    total_recruiters: int
    approved_recruiters: int
    pending_recruiters: int
    active_recruiters: int
    admin_recruiters: int
    companies_with_recruiters: int
    average_recruiters_per_company: float

    class Config:
        from_attributes = True


# Activity and audit schemas
class RecruiterActivity(BaseModel):
    """Recruiter activity information"""
    recruiter_id: UUID
    last_activity_at: Optional[datetime] = None
    days_since_last_activity: Optional[int] = None
    total_actions: Optional[int] = None
    recent_actions: Optional[list[Dict[str, Any]]] = None


class RecruiterAuditLog(BaseModel):
    """Recruiter audit log entry"""
    recruiter_id: UUID
    action: str
    performed_by: UUID
    performed_at: datetime
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None