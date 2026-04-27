"""
Response Pydantic schemas for authentication endpoints
All authentication response models should be defined here for consistency
"""
from pydantic import BaseModel
from typing import Dict, Optional


# =====================================================
# AUTH RESPONSE SCHEMAS
# =====================================================

class LoginResponse(BaseModel):
    success: bool
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict

class SignupResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[Dict] = None

class PasswordResetResponse(BaseModel):
    success: bool
    message: str

class PasswordResetConfirmResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

class PhoneLoginSendOTPResponse(BaseModel):
    """Response after sending OTP to phone"""
    success: bool
    message: str
    verification_id: str
    expires_in: int = 300  # Seconds until OTP expires
    phone: str  # Masked phone number for display
    customer_name: Optional[str] = None

class PhoneLoginVerifyOTPResponse(BaseModel):
    """Response after successful OTP verification and login"""
    success: bool
    message: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict

class PhoneVerificationSendOTPResponse(BaseModel):
    """Response after sending OTP for phone verification (during signup/profile update)"""
    success: bool
    message: str
    verification_id: str
    expires_in: int = 300  # Seconds until OTP expires
    phone: str  # Masked phone number

class PhoneVerificationConfirmResponse(BaseModel):
    """Response after confirming phone verification"""
    success: bool
    message: str
    phone_verified: bool
    phone: str
