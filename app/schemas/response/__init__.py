"""
Response schemas package
"""
from .common import (
    SuccessResponse,
    ErrorResponse,
    ErrorDetail,
    ValidationErrorResponse,
)
from .auth import (
    LoginResponse,
    SignupResponse,
)
from .customer import (
    FavoriteResponse,
)
from .vendor import (
    VendorJoinRequestResponse,
    SalonResponse,
    ServiceResponse,
    SalonStaffResponse,
)
from .booking import (
    BookingResponse,
)
from .payment import (
    RazorpayOrderResponse,
    VendorRegistrationPaymentResponse,
    BookingPaymentResponse,
)
from .admin import (
    SystemConfigResponse,
    SystemConfigListResponse,
)
from .location import (
    GeocodeResponse,
    NearbySalonsResponse,
)
from .career import (
    CareerApplicationResponse,
)
from .rm import (
    VendorRequestOperationResponse,
    VendorRequestsListResponse,
    RMSalonsListResponse,
    RMProfileUpdateResponse,
    RMDashboardResponse,
    RMLeaderboardResponse,
    ServiceCategoriesResponse,
)

__all__ = [
    # Common
    "SuccessResponse", "ErrorResponse", "ErrorDetail", "ValidationErrorResponse",
    # Auth
    "LoginResponse", "SignupResponse",
    # Customer
    "FavoriteResponse",
    # Vendor
    "VendorJoinRequestResponse", "SalonResponse", "ServiceResponse", "SalonStaffResponse",
    # Booking
    "BookingResponse",
    # Payment
    "RazorpayOrderResponse", "VendorRegistrationPaymentResponse", "BookingPaymentResponse",
    # Admin
    "SystemConfigResponse", "SystemConfigListResponse",
    # Location
    "GeocodeResponse", "NearbySalonsResponse",
    # Career
    "CareerApplicationResponse",
    # RM
    "VendorRequestOperationResponse", "VendorRequestsListResponse", "RMSalonsListResponse",
    "RMProfileUpdateResponse", "RMDashboardResponse", "RMLeaderboardResponse", "ServiceCategoriesResponse",
]