"""
Response Pydantic schemas for vendor management endpoints
All vendor response models should be defined here for consistency
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, time
from ..domain.common import BusinessType, RequestStatus


# =====================================================
# VENDOR RESPONSE SCHEMAS
# =====================================================

class CompleteRegistrationResponse(BaseModel):
    """Response for vendor registration completion"""
    success: bool = True
    message: str
    data: Dict[str, Any]

    class Config:
        extra = "allow"

class VendorJoinRequestResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    rm_id: str
    status: RequestStatus
    submitted_at: Optional[datetime] = None
    admin_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rm_profile: Optional[Dict[str, Any]] = None  # Changed to Dict to allow dynamic nested data

    # Include all base fields
    business_name: str = Field(..., min_length=2, max_length=255)
    business_type: BusinessType
    owner_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    owner_phone: str = Field(..., max_length=20)
    business_address: str
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    pincode: str = Field(..., pattern=r'^\d{6}$|^\d{10}$', description="6 or 10 digit pincode")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gst_number: Optional[str] = Field(None, max_length=50)
    pan_number: Optional[str] = Field(None, max_length=10)
    business_license: Optional[str] = None
    registration_certificate: Optional[str] = None
    cover_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    services_offered: Optional[Dict[str, Any]] = None
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    working_days: Optional[List[str]] = None
    documents: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        extra = "allow"  # Allow extra fields from database

# =====================================================
# SALON RESPONSE SCHEMAS
# =====================================================

class SalonResponse(BaseModel):
    id: str
    vendor_id: Optional[str] = None
    rm_id: Optional[str] = None
    join_request_id: Optional[str] = None
    is_active: bool
    is_verified: bool
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    average_rating: float
    total_reviews: int
    registration_fee_paid: bool
    registration_fee_amount: Optional[float] = None  # Dynamic from system_config
    registration_payment_id: Optional[str] = None
    assigned_rm: Optional[str] = None
    accepting_bookings: bool = True
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_at: Optional[datetime] = None

    # Include all base fields
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
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SalonListResponse(BaseModel):
    """List view with minimal fields for performance"""
    id: str
    business_name: str
    business_type: Optional[BusinessType] = None  # Optional as not stored in salons table
    city: str
    state: str
    latitude: float
    longitude: float
    logo_url: Optional[str] = None
    average_rating: float
    total_reviews: int
    is_active: bool
    distance_km: Optional[float] = None  # Calculated field for nearby search

    class Config:
        from_attributes = True

# =====================================================
# SERVICE RESPONSE SCHEMAS
# =====================================================

class ServiceCategoryResponse(BaseModel):
    id: str
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    display_order: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ServiceResponse(BaseModel):
    id: str
    salon_id: str
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    category_id: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =====================================================
# DASHBOARD RESPONSE SCHEMAS
# =====================================================

class DashboardStatistics(BaseModel):
    """Statistics section of dashboard response"""
    total_services: int
    total_bookings: int
    pending_bookings: int
    today_bookings: int
    average_rating: float
    total_reviews: int

class VendorDashboardResponse(BaseModel):
    """Response for vendor dashboard endpoint"""
    salon: Dict[str, Any]  # Full salon data
    statistics: DashboardStatistics

    class Config:
        extra = "allow"


class VendorAnalyticsResponse(BaseModel):
    """Response for vendor analytics endpoint"""
    total_bookings: int
    total_revenue: float
    active_services: int
    average_rating: float
    pending_bookings: int

    class Config:
        extra = "allow"


# =====================================================
# PUBLIC SALON RESPONSE SCHEMAS
# =====================================================

class PublicSalonsResponse(BaseModel):
    """Response for public salons listing with pagination"""
    salons: List[SalonListResponse]
    count: int
    offset: int
    limit: int

class SalonDetailResponse(BaseModel):
    """Detailed salon information for single salon view"""
    salon: SalonResponse
    services: Optional[List[Dict[str, Any]]] = None  # Service details
    available_slots: Optional[List[Dict[str, Any]]] = None

class AvailableSlotsResponse(BaseModel):
    """Response for available booking slots"""
    salon_id: str
    date: str
    available_slots: List[Dict[str, Any]]

class NearbySalonsResponse(BaseModel):
    """Response for nearby salons search"""
    salons: List[SalonListResponse]
    search_location: Dict[str, float]  # lat/lng
    radius_km: float
    count: int

class SearchSalonsResponse(BaseModel):
    """Response for text-based salon search"""
    salons: List[SalonListResponse]
    query: str
    count: int
    offset: int
    limit: int


class SalonServicesResponse(BaseModel):
    """Response for salon services listing"""
    services: List[Dict[str, Any]]
    count: int


class PublicConfigResponse(BaseModel):
    """Response for public system configuration"""
    success: bool
    configs: Dict[str, Any]
    error: Optional[str] = None


class CommissionConfigResponse(BaseModel):
    """Response for commission configuration"""
    commission_percentage: float


class ImageUploadResponse(BaseModel):
    """Response for single image upload"""
    success: bool = True
    url: str
    path: str
    filename: str


class UploadedImageInfo(BaseModel):
    """Information about a single uploaded image"""
    url: str
    path: str
    filename: str
    original_name: str


class MultipleImageUploadResponse(BaseModel):
    """Response for multiple image upload"""
    success: bool = True
    uploaded: List[UploadedImageInfo]
    failed: List[Dict[str, Any]]
    total: int
    successful_count: int
    failed_count: int


class ImageDeleteResponse(BaseModel):
    """Response for image deletion"""
    success: bool = True
    message: str
    path: str
