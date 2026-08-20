"""
Feature Entitlement API Endpoints

    GET   /features                 — {key: status} map for the current user (any admin)
    GET   /features/admin/all       — Full registry with metadata (INTERNAL ONLY)
    PATCH /features/admin/{key}     — Change a feature's status (INTERNAL ONLY)

The /admin routes are gated by require_internal, deliberately NOT by a feature
flag. A flag-managed flags screen would still have to be visible to somebody,
and showing the client a list of every unsold feature defeats the whole gate.

Both internal routes 404 for non-internal callers rather than 403, so the
client's admin panel cannot distinguish them from routes that do not exist.
"""
from fastapi import APIRouter, Depends
from supabase import Client

from app.core.auth import get_current_user, require_admin, require_internal, TokenData
from app.core.database import get_db_client
from app.services.feature_service import FeatureService
from app.schemas.request.features import FeatureStatusUpdate
from app.schemas.response.features import (
    FeatureListResponse,
    FeatureMapResponse,
    FeatureOperationResponse,
)

router = APIRouter(prefix="/features", tags=["features"])


# ========================================
# DEPENDENCY INJECTION
# ========================================

def get_feature_service(db: Client = Depends(get_db_client)) -> FeatureService:
    """Dependency injection for FeatureService."""
    return FeatureService(db_client=db)


# ========================================
# ENTITLEMENT MAP (any authenticated admin)
# ========================================

@router.get("", response_model=FeatureMapResponse)
async def get_my_features(
    current_user: TokenData = Depends(require_admin),
    feature_service: FeatureService = Depends(get_feature_service),
):
    """
    The feature map for the calling user.

    The admin panel calls this once on load to decide which nav items and
    routes to render. Client admins receive only entitled features; internal
    staff additionally receive features still at 'internal'.

    This is a convenience for the UI, never the security boundary — each gated
    endpoint enforces its own RequireFeature check.
    """
    features = await feature_service.get_visible_features(current_user.is_internal)
    return {
        "success": True,
        "features": features,
        "is_internal": current_user.is_internal,
    }


# ========================================
# REGISTRY MANAGEMENT (internal staff only)
# ========================================

@router.get("/admin/all", response_model=FeatureListResponse)
async def list_all_features(
    current_user: TokenData = Depends(require_internal),
    feature_service: FeatureService = Depends(get_feature_service),
):
    """
    Every registered feature with its status and audit fields.

    **Internal only.** 404s for the client.
    """
    features = await feature_service.list_features()
    return {"success": True, "features": features}


@router.patch("/admin/{key}", response_model=FeatureOperationResponse)
async def update_feature_status(
    key: str,
    payload: FeatureStatusUpdate,
    current_user: TokenData = Depends(require_internal),
    feature_service: FeatureService = Depends(get_feature_service),
):
    """
    Change a feature's entitlement status — this is the "client paid" switch.

    **Internal only.** Takes effect immediately in this worker; other workers
    pick it up within the 60s flag cache TTL.
    """
    feature = await feature_service.set_status(
        key,
        payload.status,
        updated_by=current_user.user_id,
    )
    return {
        "success": True,
        "message": f"Feature '{key}' is now {payload.status}",
        "feature": feature,
    }
