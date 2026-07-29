"""
Request schemas package
"""
from .auth import (
    LoginRequest,
    SignupRequest,
    LogoutAllRequest,
    AccountDeleteRequest,
    RefreshTokenRequest,
)
from .customer import (
    SalonFilters,
    ReviewCreate,
    ReviewUpdate,
    FeedbackReviewCreate,
    CartItemCreate,
    CartItemUpdate,
    FavoriteCreate,
    ProductFavoriteCreate,
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
    SalonPromoApplyRequest,
)
from .booking import (
    BookingCreate,
    BookingCancellation,
)
from .payment import (
    PaymentVerification,
)
from .location import (
    GeocodeRequest,
)
from .career import (
    ApplicationStatusUpdate,
)
from .rm import (
    RMProfileUpdate,
)

__all__ = [
    # Auth
    "LoginRequest", "SignupRequest", "LogoutAllRequest", "AccountDeleteRequest", "RefreshTokenRequest",
    # Customer
    "SalonFilters", "ReviewCreate", "ReviewUpdate", "FeedbackReviewCreate", "CartItemCreate", "CartItemUpdate", "FavoriteCreate",
    "ProductFavoriteCreate",
    # Vendor
    "CompleteRegistrationRequest", "VendorJoinRequestBase", "VendorJoinRequestCreate",
    "VendorJoinRequestUpdate", "VendorApprovalRequest", "VendorRejectionRequest",
    "SalonBase", "SalonCreate", "SalonUpdate", "ServiceCreate", "ServiceUpdate",
    "SalonPromoApplyRequest",
    # Booking
    "BookingCreate", "BookingCancellation",
    # Payment
    "PaymentVerification",
    # Admin
    "SystemConfigUpdate",
    # Location
    "GeocodeRequest",
    # Career
    "ApplicationStatusUpdate",
    "RMProfileUpdate",
]
