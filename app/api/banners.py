"""
Banner API Endpoints

Public endpoints:
    GET  /banners               — Active, in-window banners for the home carousel (ordered)

Admin endpoints (require_admin):
    GET    /banners/admin/all   — List all banners (including inactive)
    POST   /banners             — Create banner
    PUT    /banners/reorder     — Bulk-update sort order
    PUT    /banners/{banner_id} — Update banner
    DELETE /banners/{banner_id} — Soft-delete banner (hard=true to purge)

IMPORTANT: Static path segments (/admin, /reorder) MUST be defined before the
catch-all /{banner_id} routes to avoid incorrect route matching.
"""
from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.core.database import get_db_client
from app.core.auth import require_admin, TokenData
from app.services.banner_service import BannerService
from app.schemas.request.banner import BannerCreate, BannerUpdate, BannerReorder
from app.schemas.response.banner import (
    BannerListResponse,
    BannerOperationResponse,
    BannerDeleteResponse,
)

router = APIRouter(prefix="/banners", tags=["banners"])


# ========================================
# DEPENDENCY INJECTION
# ========================================

def get_banner_service(db: Client = Depends(get_db_client)) -> BannerService:
    """Dependency injection for BannerService."""
    return BannerService(db_client=db)


# ========================================
# PUBLIC ENDPOINTS
# ========================================

@router.get("", response_model=BannerListResponse)
async def list_banners(
    banner_service: BannerService = Depends(get_banner_service),
):
    """
    List active home-carousel banners.

    **Public endpoint** — no auth required (the home screen loads this for
    anonymous users). Returns only active banners currently within their
    schedule window, ordered by `sort_order` ascending.
    """
    banners = await banner_service.list_banners(include_inactive=False)
    return {"success": True, "banners": banners, "count": len(banners)}


# ========================================
# ADMIN ENDPOINTS (static paths before catch-all)
# ========================================

@router.get("/admin/all", response_model=BannerListResponse)
async def admin_list_all_banners(
    current_user: TokenData = Depends(require_admin),
    banner_service: BannerService = Depends(get_banner_service),
):
    """
    List ALL banners including inactive ones.

    **Admin only** — for the banner management panel.
    """
    banners = await banner_service.list_banners(include_inactive=True)
    return {"success": True, "banners": banners, "count": len(banners)}


@router.post("", response_model=BannerOperationResponse)
async def create_banner(
    payload: BannerCreate,
    current_user: TokenData = Depends(require_admin),
    banner_service: BannerService = Depends(get_banner_service),
):
    """
    Create a new carousel banner.

    **Admin only.** `image_url` should come from the
    `/upload/cloudinary-banner-image` endpoint.
    """
    banner = await banner_service.create_banner(payload.model_dump(exclude_none=True))
    return {"success": True, "message": "Banner created successfully", "banner": banner}


@router.put("/reorder", response_model=BannerListResponse)
async def reorder_banners(
    payload: BannerReorder,
    current_user: TokenData = Depends(require_admin),
    banner_service: BannerService = Depends(get_banner_service),
):
    """
    Bulk-update the display order of banners.

    **Admin only.** Send the full ordered set as `{ orders: [{id, sort_order}] }`.
    """
    banners = await banner_service.reorder_banners(
        [item.model_dump() for item in payload.orders]
    )
    return {"success": True, "banners": banners, "count": len(banners)}


# ========================================
# CATCH-ALL PARAMETRIC ROUTES (must be last)
# ========================================

@router.put("/{banner_id}", response_model=BannerOperationResponse)
async def update_banner(
    banner_id: str,
    payload: BannerUpdate,
    current_user: TokenData = Depends(require_admin),
    banner_service: BannerService = Depends(get_banner_service),
):
    """
    Update an existing banner.

    **Admin only.** Only provided (non-None) fields are updated.
    """
    banner = await banner_service.update_banner(
        banner_id, payload.model_dump(exclude_none=True)
    )
    return {"success": True, "message": "Banner updated successfully", "banner": banner}


@router.delete("/{banner_id}", response_model=BannerDeleteResponse)
async def delete_banner(
    banner_id: str,
    hard: bool = Query(False, description="If true, permanently delete instead of soft-delete"),
    current_user: TokenData = Depends(require_admin),
    banner_service: BannerService = Depends(get_banner_service),
):
    """
    Delete a banner.

    **Admin only.** Default is a soft-delete (`is_active = false`); `hard=true`
    removes the row permanently.
    """
    result = await banner_service.delete_banner(banner_id, hard_delete=hard)
    return {"success": True, "message": result["message"], "banner_id": result["banner_id"]}
