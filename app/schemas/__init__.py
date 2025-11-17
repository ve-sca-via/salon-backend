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
    PasswordResetRequest, PasswordResetConfirm
)
from .request.customer import (
    ReviewCreate, ReviewUpdate, CartItemCreate, CartItemUpdate, FavoriteCreate
)
from .request.booking import (
    BookingCreate, BookingUpdate, BookingCancellation
)
from .request.vendor import (
    CompleteRegistrationRequest, VendorJoinRequestBase, VendorJoinRequestCreate, VendorJoinRequestUpdate,
    VendorApprovalRequest, VendorRejectionRequest, SalonBase, SalonCreate, SalonUpdate,
    ServiceCreate, ServiceUpdate, SalonStaffCreate, SalonStaffUpdate
)
from .request.payment import (
    PaymentBase, BookingOrderCreate, RazorpayOrderCreate, PaymentVerification
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

# =====================================================
# RESPONSE SCHEMAS (API Output Contracts)
# =====================================================
from .response.common import (
    SuccessResponse, ErrorResponse, ValidationErrorResponse
)
from .response.auth import (
    LoginResponse, SignupResponse, PasswordResetResponse, PasswordResetConfirmResponse
)
from .response.vendor import (
    VendorJoinRequestResponse, SalonResponse, SalonListResponse,
    ServiceCategoryResponse, ServiceResponse, SalonStaffResponse,
    CompleteRegistrationResponse, VendorDashboardResponse, VendorAnalyticsResponse,
    PublicSalonsResponse, SalonDetailResponse, AvailableSlotsResponse,
    NearbySalonsResponse, SearchSalonsResponse, SalonServicesResponse, SalonStaffListResponse,
    PublicConfigResponse, CommissionConfigResponse, ImageUploadResponse, MultipleImageUploadResponse, ImageDeleteResponse
)
from .response.booking import (
    BookingResponse, BookingListResponse
)
from .response.payment import (
    RazorpayOrderResponse, VendorRegistrationPaymentResponse, BookingPaymentResponse,
    PaymentVerificationResponse, VendorRegistrationVerificationResponse,
    PaymentHistoryResponse, VendorEarningsResponse
)
from .response.admin import (
    SystemConfigResponse, SystemConfigListResponse
)
from .response.location import (
    GeocodeResponse, NearbySalonsResponse
)
from .response.career import (
    CareerApplicationResponse
)

from .response.customer import (
    FavoriteResponse, CartResponse, CartOperationResponse, CartClearResponse,
    CustomerBookingsResponse, BookingCancelResponse, SalonsBrowseResponse,
    SalonsSearchResponse, SalonDetailsResponse, FavoritesResponse,
    FavoriteOperationResponse, CustomerReviewsResponse, ReviewOperationResponse
)

from .response.rm import (
    VendorRequestOperationResponse, VendorRequestsListResponse,
    RMSalonsListResponse, RMProfileUpdateResponse, RMDashboardStatistics,
    RMDashboardResponse, RMLeaderboardResponse, ServiceCategoriesResponse
)

