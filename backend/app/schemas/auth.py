"""Authentication and user schemas."""
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


# Request schemas
class LoginRequest(BaseModel):
    """Login request payload."""
    email: EmailStr
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=20)
    role: UserRole = UserRole.CONSUMER

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class SignupRequest(BaseModel):
    """Public self-registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: str = Field(..., min_length=3, max_length=20)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class GoogleAuthRequest(BaseModel):
    """Google OAuth login/signup request."""
    id_token: str
    username: Optional[str] = Field(None, min_length=3, max_length=20)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class SetUsernameRequest(BaseModel):
    """Set/update username request."""
    username: str = Field(..., min_length=3, max_length=20)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class RefreshTokenRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class SendOTPRequest(BaseModel):
    """Request to send OTP for email verification during signup."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: Optional[str] = Field(None, min_length=3, max_length=20)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class VerifyOTPSignupRequest(BaseModel):
    """Verify OTP and complete signup."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    username: Optional[str] = Field(None, min_length=3, max_length=20)
    otp_code: str = Field(..., min_length=6, max_length=6)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class SimpleRegisterRequest(BaseModel):
    """Simple registration — no OTP, username auto-derived from email prefix."""
    email: EmailStr
    password: str = Field(..., min_length=8)


class PasswordChangeRequest(BaseModel):
    """Password change request."""
    current_password: str
    new_password: str = Field(..., min_length=8)


# Response schemas
class UserResponse(BaseModel):
    """User data response."""
    id: UUID
    email: str
    full_name: Optional[str]
    username: Optional[str]
    role: UserRole
    is_active: bool
    auth_provider: str
    avatar_url: Optional[str]
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response with tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse


class TokenResponse(BaseModel):
    """Token refresh response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# Internal schemas
class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # user id
    email: str
    role: str
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    type: str = "access"  # "access" or "refresh"


class UserCreate(BaseModel):
    """Internal user creation schema."""
    email: EmailStr
    password: Optional[str] = None
    full_name: Optional[str] = None
    username: Optional[str] = None
    google_id: Optional[str] = None
    auth_provider: str = "local"
    avatar_url: Optional[str] = None
    role: UserRole = UserRole.CONSUMER


class UserUpdate(BaseModel):
    """User update schema."""
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
