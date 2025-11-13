"""
Pydantic schemas for API request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time
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

# =====================================================
# BASE SCHEMAS
# =====================================================

class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# =====================================================
# USER & PROFILE SCHEMAS
# =====================================================

class ProfileBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    profile_image_url: Optional[str] = None

class ProfileCreate(ProfileBase):
    role: UserRole = UserRole.CUSTOMER
    password: str = Field(..., min_length=8)

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    profile_image_url: Optional[str] = None

class ProfileResponse(ProfileBase, TimestampMixin):
    id: str
    role: UserRole
    is_active: bool
    email_verified: bool
    phone_verified: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    last_login_at: Optional[datetime] = None

# =====================================================
# AUTH SCHEMAS (from auth.py inline schemas)
# =====================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    success: bool
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    role: str = "customer"  # Default role

class SignupResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[Dict] = None

class LogoutAllRequest(BaseModel):
    """Request to logout from all devices"""
    password: str  # Require password confirmation for security

class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str

# =====================================================
# RM (RELATIONSHIP MANAGER) SCHEMAS
# =====================================================

class RMProfileBase(BaseModel):
    employee_id: str = Field(..., max_length=50)

class RMProfileCreate(RMProfileBase):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(..., max_length=20)
    manager_notes: Optional[str] = None

class RMProfileResponse(RMProfileBase, TimestampMixin):
    id: str
    total_score: int
    total_salons_added: int
    total_approved_salons: int
    joining_date: date
    is_active: bool
    profile: Optional[ProfileResponse] = None

class RMScoreHistoryResponse(BaseModel):
    id: str
    rm_id: str
    salon_id: Optional[str] = None
    score_change: int
    reason: str
    created_at: datetime
    created_by: Optional[str] = None

# =====================================================
# VENDOR REGISTRATION SCHEMAS (from vendors.py inline schemas)
# =====================================================

class CompleteRegistrationRequest(BaseModel):
    """Schema for vendor registration completion"""
    token: str
    full_name: str
    password: str
    confirm_password: str

# =====================================================
# VENDOR JOIN REQUEST SCHEMAS
# =====================================================

class VendorJoinRequestBase(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=255)
    business_type: BusinessType
    owner_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    owner_phone: str = Field(..., max_length=20)
    business_address: str
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: str = Field(..., max_length=10)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gst_number: Optional[str] = Field(None, max_length=50)
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

class VendorJoinRequestResponse(VendorJoinRequestBase, TimestampMixin):
    id: str
    rm_id: str
    status: RequestStatus
    admin_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rm_profile: Optional[Dict[str, Any]] = None  # Changed to Dict to allow dynamic nested data
    
    class Config:
        extra = "allow"  # Allow extra fields from database

# =====================================================
# SALON SCHEMAS
# =====================================================

class SalonBase(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=255)
    business_type: BusinessType
    description: Optional[str] = None
    phone: str = Field(..., max_length=20)
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    address: str
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: str = Field(..., max_length=10)
    latitude: float
    longitude: float
    gst_number: Optional[str] = Field(None, max_length=50)
    business_license: Optional[str] = None
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    images: Optional[List[str]] = None
    business_hours: Optional[Dict[str, Any]] = None

class SalonCreate(SalonBase):
    pass

class SalonUpdate(BaseModel):
    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    pincode: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    images: Optional[List[str]] = None
    business_hours: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class SalonResponse(SalonBase, TimestampMixin):
    id: str
    vendor_id: Optional[str] = None
    rm_id: Optional[str] = None
    join_request_id: Optional[str] = None
    is_active: bool
    is_verified: bool
    average_rating: float
    total_reviews: int
    registration_fee_paid: bool
    registration_fee_amount: Optional[float] = None
    registration_paid_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None

class SalonListResponse(BaseModel):
    """List view with minimal fields for performance"""
    id: str
    business_name: str
    business_type: BusinessType
    city: str
    state: str
    latitude: float
    longitude: float
    logo_url: Optional[str] = None
    average_rating: float
    total_reviews: int
    is_active: bool
    distance_km: Optional[float] = None  # Calculated field for nearby search

# =====================================================
# SERVICE SCHEMAS
# =====================================================

class ServiceCategoryBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    display_order: int = 0

class ServiceCategoryResponse(ServiceCategoryBase, TimestampMixin):
    id: str
    is_active: bool

class ServiceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    category_id: Optional[str] = None
    image_url: Optional[str] = None

class ServiceCreate(ServiceBase):
    # salon_id is auto-assigned from authenticated vendor, not required from client
    salon_id: Optional[str] = None

class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, ge=0)
    category_id: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    available_for_booking: Optional[bool] = None

class ServiceResponse(ServiceBase, TimestampMixin):
    id: str
    salon_id: str
    is_active: bool
    available_for_booking: bool
    category: Optional[ServiceCategoryResponse] = None

# =====================================================
# STAFF SCHEMAS
# =====================================================

class SalonStaffBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: str = Field(..., max_length=20)
    designation: Optional[str] = Field(None, max_length=100)
    specializations: Optional[List[str]] = None
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None

class SalonStaffCreate(SalonStaffBase):
    salon_id: str
    joining_date: Optional[date] = None

class SalonStaffUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    designation: Optional[str] = Field(None, max_length=100)
    specializations: Optional[List[str]] = None
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None
    is_active: Optional[bool] = None

class SalonStaffResponse(SalonStaffBase, TimestampMixin):
    id: str
    salon_id: str
    user_id: Optional[str] = None
    joining_date: date
    is_active: bool
    average_rating: float
    total_reviews: int

class StaffAvailabilityBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time
    is_available: bool = True

class StaffAvailabilityCreate(StaffAvailabilityBase):
    staff_id: str

class StaffAvailabilityResponse(StaffAvailabilityBase, TimestampMixin):
    id: str
    staff_id: str

# =====================================================
# BOOKING SCHEMAS (Updated from bookings.py inline schemas)
# =====================================================

class BookingCreate(BaseModel):
    """Schema for creating a new booking - matches current API"""
    salon_id: str  # UUID string
    booking_date: str
    booking_time: str
    services: List[Dict]  # Array of service objects
    total_amount: float  # Total service amount before fees
    booking_fee: Optional[float] = 0  # Booking fee (percentage of total)
    gst_amount: Optional[float] = 0  # GST on booking fee
    amount_paid: Optional[float] = 0  # Amount paid online
    remaining_amount: Optional[float] = 0  # Amount to pay at salon
    payment_status: Optional[str] = 'pending'  # Payment status
    payment_method: Optional[str] = None  # Payment method
    notes: Optional[str] = None

class BookingUpdate(BaseModel):
    """Schema for updating a booking - matches current API"""
    status: Optional[str] = None
    notes: Optional[str] = None
    cancellation_reason: Optional[str] = None

class BookingBase(BaseModel):
    """Legacy booking schema - kept for compatibility"""
    salon_id: str
    service_id: str
    staff_id: Optional[str] = None
    booking_date: date
    booking_time: time
    customer_name: str = Field(..., min_length=2, max_length=255)
    customer_phone: str = Field(..., max_length=20)
    customer_email: Optional[EmailStr] = None
    special_requests: Optional[str] = None

class BookingCancellation(BaseModel):
    cancellation_reason: str = Field(..., min_length=10)

class BookingResponse(TimestampMixin):
    """Legacy booking response schema"""
    id: str
    booking_number: str
    customer_id: str
    salon_id: str
    service_id: str
    staff_id: Optional[str] = None
    booking_date: date
    booking_time: time
    customer_name: str
    customer_phone: str
    customer_email: Optional[EmailStr] = None
    special_requests: Optional[str] = None
    duration_minutes: int
    status: BookingStatus
    service_price: float
    convenience_fee: float
    total_amount: float
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    cancelled_by: Optional[str] = None
    salon: Optional[SalonResponse] = None
    service: Optional[ServiceResponse] = None
    staff: Optional[SalonStaffResponse] = None

# =====================================================
# PAYMENT SCHEMAS
# =====================================================

class PaymentBase(BaseModel):
    amount: float = Field(..., gt=0)

class RazorpayOrderCreate(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = Field(default="INR")
    payment_type: PaymentType
    booking_id: Optional[str] = None
    salon_id: Optional[str] = None

class RazorpayOrderResponse(BaseModel):
    order_id: str
    amount: float
    currency: str
    key_id: str  # Razorpay key ID for frontend

class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class VendorPaymentResponse(BaseModel):
    id: str
    vendor_id: str
    salon_id: Optional[str] = None
    payment_type: PaymentType
    amount: float
    status: PaymentStatus
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    payment_method: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime

class BookingPaymentResponse(BaseModel):
    id: str
    booking_id: str
    customer_id: str
    amount: float
    convenience_fee: float
    total_amount: float
    status: PaymentStatus
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    payment_method: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime

# =====================================================
# REVIEW SCHEMAS
# =====================================================

class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = None
    images: Optional[List[str]] = None

class ReviewCreate(ReviewBase):
    booking_id: str

class ReviewResponse(ReviewBase, TimestampMixin):
    id: str
    booking_id: str
    customer_id: str
    salon_id: str
    staff_id: Optional[str] = None
    is_verified: bool
    is_visible: bool

# =====================================================
# SYSTEM CONFIG SCHEMAS
# =====================================================

class SystemConfigBase(BaseModel):
    config_key: str = Field(..., max_length=100)
    config_value: str
    config_type: str = Field(..., max_length=50)
    description: Optional[str] = None

class SystemConfigCreate(SystemConfigBase):
    pass

class SystemConfigUpdate(BaseModel):
    config_value: str
    description: Optional[str] = None
    is_active: Optional[bool] = None

class SystemConfigResponse(SystemConfigBase, TimestampMixin):
    id: str
    is_active: bool
    updated_by: Optional[str] = None

# =====================================================
# AUTHENTICATION SCHEMAS (Legacy - kept for compatibility)
# =====================================================
# Note: LoginRequest and LoginResponse are defined above (lines 100-108)
# Keeping only non-duplicate schemas here

class TokenRefresh(BaseModel):
    refresh_token: str

class PasswordReset(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)

# =====================================================
# SEARCH & FILTER SCHEMAS
# =====================================================

class LocationSearch(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = Field(default=10, gt=0, le=100)
    business_type: Optional[BusinessType] = None
    service_category: Optional[str] = None

class SalonSearchFilters(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    business_type: Optional[BusinessType] = None
    min_rating: Optional[float] = Field(None, ge=0, le=5)
    is_verified: Optional[bool] = None

# =====================================================
# PAGINATION SCHEMAS
# =====================================================

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

# =====================================================
# RESPONSE WRAPPERS
# =====================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Any] = None

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: Optional[List[str]] = None
    error_code: Optional[str] = None

# =====================================================
# PAYMENT SCHEMAS
# =====================================================

class PaymentOrderCreate(BaseModel):
    amount: int = Field(..., description="Amount in paise (1 INR = 100 paise)")
    currency: str = Field(default="INR", description="Currency code")
    receipt: str = Field(..., description="Receipt/order ID")
    notes: Optional[Dict[str, Any]] = Field(default=None, description="Additional notes")

class PaymentOrderResponse(BaseModel):
    id: str
    amount: int
    currency: str
    receipt: str
    status: str
    created_at: int

class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
