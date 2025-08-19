from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    google_id: Optional[str] = None
    github_id: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserInDBBase(UserBase):
    id: UUID
    google_id: Optional[str] = None
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class User(UserInDBBase):
    pass


class UserInDB(UserInDBBase):
    hashed_password: Optional[str] = None


# Token schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Google OAuth schemas
class GoogleTokenRequest(BaseModel):
    code: str
    state: Optional[str] = None


class GoogleUserInfo(BaseModel):
    id: str
    email: EmailStr
    verified_email: bool
    name: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None


# Google account linking
class GoogleAccountLinkRequest(BaseModel):
    google_code: str
    state: Optional[str] = None


# Mobile Auth schemas
# Mobile-specific schemas
class MobileLogoutRequest(BaseModel):
    """Request schema for mobile logout."""
    refresh_token: str


class MobileAuthResponse(BaseModel):
    """Response schema for mobile authentication."""
    user: Dict[str, Any]
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class MobileTokenResponse(BaseModel):
    """Response schema for mobile token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class MobileSessionInfo(BaseModel):
    """Mobile session information."""
    device_id: Optional[str] = None
    created_at: Optional[str] = None
    last_used: Optional[str] = None
    session_key: Optional[str] = None


class MobileSessionsResponse(BaseModel):
    """Response for mobile sessions list."""
    sessions: list[MobileSessionInfo]
    total_count: int
    message: Optional[str] = None


class DeviceInfo(BaseModel):
    """Device information for mobile sessions."""
    device_id: str
    device_name: Optional[str] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None


# Github
class GitHubTokenRequest(BaseModel):
    code: str
    state: Optional[str] = None

class GitHubAccountLinkRequest(BaseModel):
    """Request schema for linking GitHub account."""
    github_code: str
    state: Optional[str] = None

class GitHubUserInfo(BaseModel):
    id: int
    login: str
    email: Optional[EmailStr]
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    blog: Optional[str] = None
    public_repos: Optional[int] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
