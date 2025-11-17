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