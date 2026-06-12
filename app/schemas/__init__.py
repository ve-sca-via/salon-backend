"""
Pydantic schemas for API request/response validation
Organized into domain models, request DTOs, and response contracts
"""

# =====================================================
# DOMAIN MODELS (Business Entities)
# =====================================================
from .domain.common import (
    UserRole, RequestStatus, BookingStatus, PaymentStatus,
    PaymentType, BusinessType
)
from .domain.user import (
    TimestampMixin, ProfileBase, ProfileCreate, ProfileUpdate, ProfileResponse
)
from .domain.rm import (
    RMProfileBase, RMProfileCreate, RMProfileResponse, RMScoreHistoryResponse
)

# =====================================================
# REQUEST SCHEMAS (API Input Validation)
# =====================================================
from .request.auth import (
    LoginRequest, SignupRequest, LogoutAllRequest, RefreshTokenRequest,
    PasswordResetRequest, PasswordResetConfirm, UserProfileUpdate,
    PhoneLoginSendOTPRequest, PhoneLoginVerifyOTPRequest,
    PhoneVerificationSendOTPRequest, PhoneVerificationConfirmRequest,
    PhoneSignupSendOTPRequest, PhoneSignupVerifyOTPRequest
)
from .request.customer import (
    ReviewCreate, ReviewUpdate, FeedbackReviewCreate, CartItemCreate, CartItemUpdate, FavoriteCreate,
    ProductFavoriteCreate
)
from .request.booking import (
    BookingCreate, BookingCancellation, CartCheckoutCreate
)
from .request.vendor import (
    CompleteRegistrationRequest, VendorJoinRequestBase, VendorJoinRequestCreate, VendorJoinRequestUpdate,
    VendorApprovalRequest, VendorRejectionRequest, SalonBase, SalonCreate, SalonUpdate,
    ServiceCreate, ServiceUpdate, SalonPromoApplyRequest
)
from .request.payment import (
    PaymentVerification
)
from .request.admin import (
    SystemConfigUpdate
)
from .request.location import (
    GeocodeRequest
)
from .request.career import (
    ApplicationStatusUpdate
)
from .request.product import (
    ProductCreate, ProductUpdate
)

# =====================================================
# RESPONSE SCHEMAS (API Output Contracts)
# =====================================================
from .response.common import (
    SuccessResponse, ErrorResponse, ValidationErrorResponse
)
from .response.auth import (
    LoginResponse, SignupResponse, PasswordResetResponse, PasswordResetConfirmResponse,
    PhoneLoginSendOTPResponse, PhoneLoginVerifyOTPResponse,
    PhoneVerificationSendOTPResponse, PhoneVerificationConfirmResponse
)
from .response.vendor import (
    VendorJoinRequestResponse, SalonResponse, SalonListResponse,
    ServiceCategoryResponse, ServiceResponse, SalonPromoResponse,
    CompleteRegistrationResponse, VendorAnalyticsResponse,
    PublicSalonsResponse, SalonDetailResponse, AvailableSlotsResponse,
    SearchSalonsResponse, SalonServicesResponse,
    PublicConfigResponse, ImageUploadResponse
)
from .response.booking import (
    BookingResponse
)
from .response.payment import (
    RazorpayOrderResponse,
    VendorRegistrationVerificationResponse,
)
from .response.admin import (
    SystemConfigResponse, SystemConfigListResponse
)
from .response.location import (
    GeocodeResponse, NearbySalonsResponse
)
from .response.city import (
    PopularCityResponse, PopularCitiesResponse
)
from .response.career import (
    CareerApplicationResponse
)
from .response.product import (
    ProductResponse, ProductListResponse, ProductOperationResponse, ProductDeleteResponse,
    ProductCartResponse, ProductCartOperationResponse
)

from .response.customer import (
    FavoriteResponse, CartResponse, CartOperationResponse, CartClearResponse,
    CustomerBookingsResponse, BookingCancelResponse, SalonsBrowseResponse,
    SalonsSearchResponse, SalonDetailsResponse, FavoritesResponse,
    FavoriteOperationResponse, CustomerReviewsResponse, ReviewOperationResponse,
    ReviewFeedbackContextResponse, PublicSalonReviewsResponse
)

from .response.rm import (
    VendorRequestOperationResponse, VendorRequestsListResponse,
    RMSalonsListResponse, RMProfileUpdateResponse, RMDashboardStatistics,
    RMDashboardResponse, RMLeaderboardResponse
)

# Public schema surface. This package is an intentional aggregator: every name
# above is re-exported for `from app.schemas import X`. Declaring __all__ makes
# that explicit (and silences "imported but unused" on the re-exports).
__all__ = [
    # --- Domain models ---
    "UserRole", "RequestStatus", "BookingStatus", "PaymentStatus", "PaymentType", "BusinessType",
    "TimestampMixin", "ProfileBase", "ProfileCreate", "ProfileUpdate", "ProfileResponse",
    "RMProfileBase", "RMProfileCreate", "RMProfileResponse", "RMScoreHistoryResponse",
    # --- Request schemas ---
    "LoginRequest", "SignupRequest", "LogoutAllRequest", "RefreshTokenRequest",
    "PasswordResetRequest", "PasswordResetConfirm", "UserProfileUpdate",
    "PhoneLoginSendOTPRequest", "PhoneLoginVerifyOTPRequest",
    "PhoneVerificationSendOTPRequest", "PhoneVerificationConfirmRequest",
    "PhoneSignupSendOTPRequest", "PhoneSignupVerifyOTPRequest",
    "ReviewCreate", "ReviewUpdate", "FeedbackReviewCreate", "CartItemCreate", "CartItemUpdate", "FavoriteCreate",
    "ProductFavoriteCreate",
    "BookingCreate", "BookingCancellation", "CartCheckoutCreate",
    "CompleteRegistrationRequest", "VendorJoinRequestBase", "VendorJoinRequestCreate", "VendorJoinRequestUpdate",
    "VendorApprovalRequest", "VendorRejectionRequest", "SalonBase", "SalonCreate", "SalonUpdate",
    "ServiceCreate", "ServiceUpdate", "SalonPromoApplyRequest",
    "PaymentVerification",
    "SystemConfigUpdate",
    "GeocodeRequest",
    "ApplicationStatusUpdate",
    "ProductCreate", "ProductUpdate",
    # --- Response schemas ---
    "SuccessResponse", "ErrorResponse", "ValidationErrorResponse",
    "LoginResponse", "SignupResponse", "PasswordResetResponse", "PasswordResetConfirmResponse",
    "PhoneLoginSendOTPResponse", "PhoneLoginVerifyOTPResponse",
    "PhoneVerificationSendOTPResponse", "PhoneVerificationConfirmResponse",
    "VendorJoinRequestResponse", "SalonResponse", "SalonListResponse",
    "ServiceCategoryResponse", "ServiceResponse", "SalonPromoResponse",
    "CompleteRegistrationResponse", "VendorAnalyticsResponse",
    "PublicSalonsResponse", "SalonDetailResponse", "AvailableSlotsResponse",
    "NearbySalonsResponse", "SearchSalonsResponse", "SalonServicesResponse",
    "PublicConfigResponse", "ImageUploadResponse",
    "BookingResponse",
    "RazorpayOrderResponse",
    "VendorRegistrationVerificationResponse",
    "SystemConfigResponse", "SystemConfigListResponse",
    "GeocodeResponse",
    "PopularCityResponse", "PopularCitiesResponse",
    "CareerApplicationResponse",
    "ProductResponse", "ProductListResponse", "ProductOperationResponse", "ProductDeleteResponse",
    "ProductCartResponse", "ProductCartOperationResponse",
    "FavoriteResponse", "CartResponse", "CartOperationResponse", "CartClearResponse",
    "CustomerBookingsResponse", "BookingCancelResponse", "SalonsBrowseResponse",
    "SalonsSearchResponse", "SalonDetailsResponse", "FavoritesResponse",
    "FavoriteOperationResponse", "CustomerReviewsResponse", "ReviewOperationResponse",
    "ReviewFeedbackContextResponse", "PublicSalonReviewsResponse",
    "VendorRequestOperationResponse", "VendorRequestsListResponse",
    "RMSalonsListResponse", "RMProfileUpdateResponse", "RMDashboardStatistics",
    "RMDashboardResponse", "RMLeaderboardResponse",
]

