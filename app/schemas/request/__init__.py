"""
Request schemas package
"""
from .auth import (
    LoginRequest,
    SignupRequest,
    LogoutAllRequest,
    RefreshTokenRequest,
)
from .customer import (
    SalonFilters,
    ReviewCreate,
    ReviewUpdate,
    CartItemCreate,
    CartItemUpdate,
    FavoriteCreate,
)
from .vendor import (
    CompleteRegistrationRequest,
    VendorJoinRequestBase,
    VendorJoinRequestCreate,
    VendorJoinRequestUpdate,
    VendorApprovalRequest,
    VendorRejectionRequest,
    SalonBase,
    SalonCreate,
    SalonUpdate,
    ServiceCreate,
    ServiceUpdate,
)
from .booking import (
    BookingCreate,
    BookingUpdate,
    BookingCancellation,
)
from .payment import (
    PaymentBase,
    BookingOrderCreate,
    RazorpayOrderCreate,
    PaymentVerification,
)
from .location import (
    GeocodeRequest,
)
from .career import (
    ApplicationStatusUpdate,
    PersonalInfo,
    JobDetails,
    Education,
    AdditionalInfo,
)
from .rm import (
    RMProfileUpdate,
)

__all__ = [
    # Auth
    "LoginRequest", "SignupRequest", "LogoutAllRequest", "RefreshTokenRequest",
    # Customer
    "SalonFilters", "ReviewCreate", "ReviewUpdate", "CartItemCreate", "CartItemUpdate", "FavoriteCreate",
    # Vendor
    "CompleteRegistrationRequest", "VendorJoinRequestBase", "VendorJoinRequestCreate",
    "VendorJoinRequestUpdate", "VendorApprovalRequest", "VendorRejectionRequest",
    "SalonBase", "SalonCreate", "SalonUpdate", "ServiceCreate", "ServiceUpdate",
    # Booking
    "BookingCreate", "BookingUpdate", "BookingCancellation",
    # Payment
    "PaymentBase", "BookingOrderCreate", "RazorpayOrderCreate", "PaymentVerification",
    # Admin
    "SystemConfigUpdate",
    # Location
    "GeocodeRequest",
    # Career
    "ApplicationStatusUpdate",
    "PersonalInfo", "JobDetails", "Education", "AdditionalInfo",
    "RMProfileUpdate",
]