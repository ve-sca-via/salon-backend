"""
Request Pydantic schemas for vendor management endpoints
All vendor request models should be defined here for consistency
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List
from datetime import time
from ..domain.common import BusinessType, RequestStatus


# =====================================================
# VENDOR REQUEST SCHEMAS
# =====================================================

class CompleteRegistrationRequest(BaseModel):
    """Schema for vendor registration completion"""
    token: str
    full_name: str
    password: str
    confirm_password: str

class VendorJoinRequestBase(BaseModel):
    """Vendor join request schema matching updated database schema"""
    business_name: str = Field(..., min_length=2, max_length=255)
    business_type: BusinessType
    owner_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    owner_phone: str = Field(..., max_length=20)
    business_address: str
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: str = Field(..., pattern=r'^\d{6}$', description="6-digit pincode")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gst_number: Optional[str] = Field(None, max_length=15)
    business_license: Optional[str] = None
    documents: Optional[Dict[str, Any]] = None

class VendorJoinRequestCreate(VendorJoinRequestBase):
    pass

class VendorJoinRequestUpdate(BaseModel):
    status: RequestStatus
    admin_notes: Optional[str] = None

class VendorApprovalRequest(BaseModel):
    """Request body for approving vendor"""
    admin_notes: Optional[str] = Field(None, max_length=500, description="Optional notes from admin")

class VendorRejectionRequest(BaseModel):
    """Request body for rejecting vendor"""
    admin_notes: str = Field(..., min_length=1, max_length=500, description="Rejection reason (required)")


# Helper models for approval workflow
class Coordinates(BaseModel):
    latitude: float
    longitude: float


class ApprovalConfig(BaseModel):
    rm_score: int
    registration_fee: float

# =====================================================
# SALON REQUEST SCHEMAS
# =====================================================

class SalonBase(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    phone: str = Field(..., max_length=20)
    email: Optional[EmailStr] = None
    address: str
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: str = Field(..., max_length=6)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gst_number: Optional[str] = Field(None, max_length=15)
    pan_number: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = None
    cover_images: Optional[List[str]] = None
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    working_days: Optional[List[str]] = None

class SalonCreate(SalonBase):
    pass

class SalonUpdate(BaseModel):
    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=6)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gst_number: Optional[str] = Field(None, max_length=15)
    pan_number: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = None
    cover_images: Optional[List[str]] = None
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    working_days: Optional[List[str]] = None
# =====================================================
# SERVICE REQUEST SCHEMAS
# =====================================================

class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    category_id: Optional[str] = None
    image_url: Optional[str] = None

class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
    category_id: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

# =====================================================
# STAFF REQUEST SCHEMAS
# =====================================================

class SalonStaffCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: str = Field(..., max_length=20)
    designation: Optional[str] = Field(None, max_length=100)
    specializations: Optional[List[str]] = None
    profile_image: Optional[str] = None
    joining_date: Optional[str] = None

class SalonStaffUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    designation: Optional[str] = Field(None, max_length=100)
    specializations: Optional[List[str]] = None
    profile_image: Optional[str] = None
    is_active: Optional[bool] = None
