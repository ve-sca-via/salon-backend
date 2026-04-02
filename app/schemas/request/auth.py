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
    verification_token: Optional[str] = Field(None, description="JWT token obtained from phone OTP verification")

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

class UserProfileUpdate(BaseModel):
    """Request to update user profile details"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = None
    age: Optional[int] = Field(None, ge=13, le=120)
    gender: Optional[str] = Field(None, description="male, female, or other")

class PhoneLoginSendOTPRequest(BaseModel):
    """Request to send OTP to phone number for login"""
    phone: str = Field(
        ...,
        description="Phone number (10 digits for India, or with country code like +919876543210)",
        min_length=10,
        max_length=15
    )
    country_code: Optional[str] = Field(
        default="91",
        description="Country code (default: 91 for India)"
    )

class PhoneLoginVerifyOTPRequest(BaseModel):
    """Request to verify OTP and login via phone"""
    phone: str = Field(
        ...,
        description="Phone number used to receive OTP",
        min_length=10,
        max_length=15
    )
    otp: str = Field(
        ...,
        description="6-digit OTP code",
        min_length=6,
        max_length=6,
        pattern=r'^\d{6}$'
    )
    verification_id: str = Field(
        ...,
        description="Verification ID returned from send-otp endpoint"
    )

class PhoneVerificationSendOTPRequest(BaseModel):
    """Request to send OTP for phone verification (for authenticated users)"""
    phone: str = Field(
        ...,
        description="New or existing phone number to verify in E.164 format",
        min_length=10,
        max_length=20
    )
    country_code: Optional[str] = Field(
        default="91",
        description="Country code (default: 91 for India)"
    )

class PhoneVerificationConfirmRequest(BaseModel):
    """Request to confirm phone verification with OTP"""
    phone: str = Field(
        ...,
        description="Phone number being verified",
        min_length=10,
        max_length=20
    )
    otp: str = Field(
        ...,
        description="6-digit OTP code",
        min_length=6,
        max_length=6,
        pattern=r'^\d{6}$'
    )
    verification_id: str = Field(
        ...,
        description="Verification ID from send-otp endpoint"
    )

class PhoneSignupSendOTPRequest(BaseModel):
    """Request to send OTP to phone number for signup"""
    phone: str = Field(
        ...,
        description="Phone number (10 digits for India, or with country code like +919876543210)",
        min_length=10,
        max_length=15
    )
    country_code: Optional[str] = Field(
        default="91",
        description="Country code (default: 91 for India)"
    )

class PhoneSignupVerifyOTPRequest(BaseModel):
    """Request to verify OTP for phone signup"""
    phone: str = Field(
        ...,
        description="Phone number used to receive OTP",
        min_length=10,
        max_length=15
    )
    otp: str = Field(
        ...,
        description="6-digit OTP code",
        min_length=6,
        max_length=6,
        pattern=r'^\d{6}$'
    )
    verification_id: str = Field(
        ...,
        description="Verification ID returned from send-otp endpoint"
    )

