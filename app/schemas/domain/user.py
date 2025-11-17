"""
Domain models for user and profile entities
Core business entities for user management
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from .common import UserRole, TimestampMixin, ProfileBase


# =====================================================
# USER DOMAIN MODELS
# =====================================================

class ProfileCreate(ProfileBase):
    user_role: UserRole = UserRole.CUSTOMER
    password: str = Field(..., min_length=8)

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=6)

class ProfileResponse(ProfileBase, TimestampMixin):
    id: str
    user_role: UserRole
    is_active: bool
    phone_verified: bool
    phone_verified_at: Optional[datetime] = None
    phone_verification_method: Optional[str] = None
    deleted_at: Optional[datetime] = None