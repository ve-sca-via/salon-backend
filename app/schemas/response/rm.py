from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from .common import SuccessResponse


# =====================================================
# VENDOR REQUESTS
# =====================================================

class VendorRequestOperationResponse(SuccessResponse):
    """Response for vendor request operations (update/delete)"""
    data: Optional[Dict[str, Any]] = Field(None, description="Updated vendor request data (for updates only)")


class VendorRequestsListResponse(SuccessResponse):
    """Response for listing RM's vendor requests"""
    data: List[Dict[str, Any]] = Field(..., description="List of vendor requests")
    count: int = Field(..., description="Total number of requests")


# =====================================================
# SALONS
# =====================================================

class RMSalonsListResponse(SuccessResponse):
    """Response for RM's salons list"""
    data: List[Dict[str, Any]] = Field(..., description="List of salons managed by RM")
    count: int = Field(..., description="Total number of salons")


# =====================================================
# PROFILE
# =====================================================

class RMProfileUpdateResponse(SuccessResponse):
    """Response for RM profile updates"""
    data: Dict[str, Any] = Field(..., description="Updated RM profile data")


# =====================================================
# DASHBOARD
# =====================================================

class RMDashboardStatistics(BaseModel):
    """RM dashboard statistics"""
    total_score: float = Field(..., description="Total performance score")
    total_salons_added: int = Field(..., description="Total salons added by RM")
    total_approved_salons: int = Field(..., description="Total approved salons")
    pending_requests: int = Field(..., description="Pending vendor requests")
    approved_requests: int = Field(..., description="Approved vendor requests")
    rejected_requests: int = Field(..., description="Rejected vendor requests")
    active_salons: int = Field(..., description="Currently active salons")


class RMDashboardResponse(BaseModel):
    """Response for RM dashboard"""
    profile: Dict[str, Any] = Field(..., description="RM profile information")
    statistics: RMDashboardStatistics = Field(..., description="Dashboard statistics")
    recent_scores: List[Dict[str, Any]] = Field(..., description="Recent score changes")


# =====================================================
# LEADERBOARD
# =====================================================

class RMLeaderboardResponse(SuccessResponse):
    """Response for RM leaderboard"""
    data: List[Dict[str, Any]] = Field(..., description="List of top RMs with rankings")
    total: int = Field(..., description="Total number of RMs in leaderboard")


# =====================================================
# SERVICE CATEGORIES
# =====================================================

class ServiceCategoriesResponse(SuccessResponse):
    """Response for service categories list"""
    data: List[Dict[str, Any]] = Field(..., description="List of active service categories")