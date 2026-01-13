"""
Request Pydantic schemas for authentication endpoints
All authentication request models should be defined here for consistency
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# =====================================================
# AUTH REQUEST SCHEMAS
# =====================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    age: int = Field(..., ge=13, le=120, description="User age (13-120 years, required)")
    gender: str = Field(..., description="User gender: male, female, or other (required)")
    user_role: str = "customer"  # Default role

class LogoutAllRequest(BaseModel):
    """Request to logout from all devices"""
    password: str  # Require password confirmation for security

class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str

class PasswordResetRequest(BaseModel):
    """Request to initiate password reset"""
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    """Request to confirm password reset with token"""
    token: str
    new_password: str = Field(..., min_length=8)