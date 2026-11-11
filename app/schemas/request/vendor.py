"""
Request Pydantic schemas for vendor management endpoints
All vendor request models should be defined here for consistency
"""
from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional, Dict, Any, List
from datetime import time
from ..domain.common import BusinessType, RequestStatus, OutletType
from app.core.validators import BlankableUUIDStr
from .base import (
    IndianMobileDigits,
    OptionalIndianMobileDigits,
    OptionalPincode,
    PartialUpdateModel,
    Pincode,
)


# =====================================================
# VENDOR REQUEST SCHEMAS
# =====================================================

class CompleteRegistrationRequest(BaseModel):
    """Schema for vendor registration completion"""
    token: str
    full_name: str
    password: str
    confirm_password: str
    age: int = Field(..., ge=18, le=120, description="Age must be between 18 and 120")
    gender: str = Field(..., description="Gender: male, female, or other")


class VendorJoinRequestBase(BaseModel):
    """Vendor join request schema - comprehensive salon onboarding data"""
    # Business Info
    business_name: str = Field(..., min_length=2, max_length=255)
    business_type: BusinessType = Field(..., description="Type of business: salon, spa, clinic, unisex_salon, barber_shop, beauty_parlor, retail_shop, wholesale_buyer")
    owner_name: str = Field(..., min_length=2, max_length=255)
    # Optional for regular_buyer requests - these owners generally don't have
    # an email on file and activate their account via phone OTP instead of an
    # emailed registration link. Still required for normal salon/vendor requests.
    owner_email: Optional[EmailStr] = None
    owner_phone: IndianMobileDigits
    # The next three are required for regular_buyer only (enforced below):
    # account creation now happens at admin-approval time with no buyer-facing
    # step left, so there's nobody left to ask for these afterwards - the RM
    # collects them at intake instead, right alongside owner_name/owner_phone.
    owner_age: Optional[int] = Field(None, ge=13, le=120, description="Owner's age (required for regular_buyer)")
    owner_gender: Optional[str] = Field(None, description="Owner's gender: male, female, or other (required for regular_buyer)")
    owner_phone_verification_token: Optional[str] = Field(
        None,
        description=(
            "Proof owner_phone was OTP-verified at intake, from "
            "POST /auth/signup/phone/verify-otp's verification_token (required for regular_buyer)"
        ),
    )

    # Location
    business_address: str = Field(..., min_length=10, description="Full business address (minimum 10 characters)")
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: Pincode
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    
    # Legal & Compliance
    outlet: Optional[OutletType] = Field(None, description="Type of outlet: franchisee or Company owned")
    is_gst: Optional[bool] = Field(False, description="Whether the business has GST registration")
    gst_number: Optional[str] = Field(None, max_length=50)
    pan_number: Optional[str] = Field(None, pattern=r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', description="PAN format: ABCDE1234F")
    business_license: Optional[str] = Field(None, description="Business license document URL")
    registration_certificate: Optional[str] = Field(None, description="Registration certificate URL")
    documents: Optional[Dict[str, Any]] = Field(None, description="Additional documents {doc_type: url}")
    
    # Media
    cover_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = Field(default_factory=list)
    
    # Request Type
    request_type: Optional[str] = Field("salon", description="Type of request: salon or regular_buyer")
    
    # Operations
    services_offered: Optional[Dict[str, Any]] = Field(None, description="Services by category")
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    working_days: Optional[List[str]] = Field(default_factory=list)
    facilities: Optional[Dict[str, bool]] = Field(default_factory=dict, description="Salon facilities availability")

    @model_validator(mode="after")
    def _require_regular_buyer_intake_fields(self):
        if self.request_type != "regular_buyer":
            if not self.owner_email:
                raise ValueError("owner_email is required for salon requests")
            return self

        missing = [
            name for name, value in (
                ("owner_age", self.owner_age),
                ("owner_gender", self.owner_gender),
                ("owner_phone_verification_token", self.owner_phone_verification_token),
            ) if value is None
        ]
        if missing:
            raise ValueError(f"{', '.join(missing)} required for regular_buyer requests")
        if self.owner_gender.lower() not in ("male", "female", "other"):
            raise ValueError("owner_gender must be 'male', 'female', or 'other'")
        return self

class VendorJoinRequestCreate(VendorJoinRequestBase):
    pass

class VendorJoinRequestUpdate(PartialUpdateModel):
    status: RequestStatus
    admin_notes: Optional[str] = None

class VendorApprovalRequest(BaseModel):
    """Request body for approving vendor"""
    admin_notes: Optional[str] = Field(None, max_length=500, description="Optional notes from admin")
    custom_registration_fee_amount: Optional[float] = Field(
        None, ge=0,
        description="One-off registration fee for this account, overriding the global default for its type. 0 waives the fee."
    )

class VendorRejectionRequest(BaseModel):
    """Request body for rejecting vendor"""
    admin_notes: str = Field(..., min_length=1, max_length=500, description="Rejection reason (required)")


# =====================================================
# SALON REQUEST SCHEMAS
# =====================================================

class SalonBase(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    phone: IndianMobileDigits
    email: Optional[EmailStr] = None
    address: str
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: Pincode
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    outlet: Optional[OutletType] = Field(None, description="Type of outlet: franchisee or Company owned")
    is_gst: Optional[bool] = Field(False, description="Whether the salon has GST registration")
    gst_number: Optional[str] = Field(None, max_length=15)
    pan_number: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = None
    cover_images: Optional[List[str]] = None
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    working_days: Optional[List[str]] = None
    facilities: Optional[Dict[str, bool]] = Field(default_factory=dict, description="Salon facilities availability")

class SalonCreate(SalonBase):
    pass

class SalonUpdate(PartialUpdateModel):
    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    phone: OptionalIndianMobileDigits = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: OptionalPincode = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    outlet: Optional[OutletType] = Field(None, description="Type of outlet: franchisee or Company owned")
    is_gst: Optional[bool] = Field(None, description="Whether the salon has GST registration")
    gst_number: Optional[str] = Field(None, max_length=15)
    pan_number: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = None
    cover_images: Optional[List[str]] = None
    agreement_document_url: Optional[str] = None
    business_hours: Optional[Dict[str, Any]] = Field(None, description="Day-wise business hours {monday: '9:00 AM - 6:00 PM', ...}")
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    working_days: Optional[List[str]] = None
    accepting_bookings: Optional[bool] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    facilities: Optional[Dict[str, bool]] = None
    custom_registration_fee_amount: Optional[float] = Field(
        None, ge=0,
        description="One-off registration fee override for this account. Send null to clear it and fall back to the global default for this salon_type."
    )
# =====================================================
# SERVICE REQUEST SCHEMAS
# =====================================================

class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    discount_percentage: Optional[float] = Field(None, ge=0, le=100)
    category_id: BlankableUUIDStr = None
    subcategory_id: BlankableUUIDStr = None
    sub_subcategory_id: BlankableUUIDStr = None
    category_name: Optional[str] = Field(None, min_length=1, max_length=255)
    subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    sub_subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gender_category: Optional[str] = Field("both", pattern="^(male|female|both)$")
    image_url: Optional[str] = None
    is_active: Optional[bool] = True

class ServiceUpdate(PartialUpdateModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
    discount_percentage: Optional[float] = Field(None, ge=0, le=100)
    category_id: BlankableUUIDStr = None
    subcategory_id: BlankableUUIDStr = None
    sub_subcategory_id: BlankableUUIDStr = None
    category_name: Optional[str] = Field(None, min_length=1, max_length=255)
    subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    sub_subcategory_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gender_category: Optional[str] = Field(None, pattern="^(male|female|both)$")
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


class SalonPromoApplyRequest(BaseModel):
    """Apply a salon-wide discount promotion to all services."""
    title: str = Field(..., min_length=2, max_length=255)
    discount_type: str = Field(..., pattern="^(percentage|flat_amount)$")
    discount_value: float = Field(..., gt=0)
    min_booking_amount: Optional[float] = Field(None, ge=0)
    max_discount_limit: Optional[float] = Field(None, ge=0)
    start_date: str = Field(..., description="ISO date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="ISO date YYYY-MM-DD, optional")
