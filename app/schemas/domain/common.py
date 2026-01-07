"""
Domain models and enums - core business entities
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# =====================================================
# ENUMS
# =====================================================

class UserRole(str, Enum):
    ADMIN = "admin"
    RELATIONSHIP_MANAGER = "relationship_manager"
    VENDOR = "vendor"
    CUSTOMER = "customer"

class RequestStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

class PaymentType(str, Enum):
    REGISTRATION_FEE = "registration_fee"
    CONVENIENCE_FEE = "convenience_fee"
    SERVICE_PAYMENT = "service_payment"

class BusinessType(str, Enum):
    SALON = "salon"
    SPA = "spa"
    CLINIC = "clinic"
    UNISEX_SALON = "unisex_salon"
    BARBER_SHOP = "barber_shop"
    BEAUTY_PARLOR = "beauty_parlor"


# =====================================================
# BASE DOMAIN MODELS
# =====================================================

class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProfileBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=6)