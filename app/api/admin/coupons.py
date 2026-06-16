"""
Admin Coupon API Endpoints

Full coupon management for admins, including platform-wide coupons usable on any
salon. Vendor-scoped coupon management lives under /vendors/coupons.
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

from app.core.auth import require_admin, TokenData
from app.core.database import get_db_client
from app.services.coupon_service import CouponService
from app.schemas import AdminCouponCreate, CouponUpdate, CouponResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_coupon_service(db=Depends(get_db_client)) -> CouponService:
    """Dependency injection for CouponService"""
    return CouponService(db_client=db)


@router.get("", response_model=List[CouponResponse])
async def list_coupons(
    scope: Optional[str] = Query(None, description="Filter by scope: platform | vendor"),
    salon_id: Optional[str] = Query(None, description="Filter by salon"),
    current_user: TokenData = Depends(require_admin),
    coupon_service: CouponService = Depends(get_coupon_service)
):
    """List all coupons (platform and vendor), optionally filtered."""
    return await coupon_service.list_coupons(scope=scope, salon_id=salon_id)


@router.post("", response_model=CouponResponse)
async def create_coupon(
    coupon: AdminCouponCreate,
    current_user: TokenData = Depends(require_admin),
    coupon_service: CouponService = Depends(get_coupon_service)
):
    """
    Create a coupon. Defaults to a platform-wide coupon usable on any salon;
    set scope='vendor' + salon_id to scope it to one salon.
    """
    payload = coupon.model_dump()
    payload["created_by"] = current_user.user_id
    result = await coupon_service.create_coupon(payload)
    logger.info(f"Admin {current_user.user_id} created coupon {result.get('code')}")
    return result


@router.get("/{coupon_id}", response_model=CouponResponse)
async def get_coupon(
    coupon_id: str,
    current_user: TokenData = Depends(require_admin),
    coupon_service: CouponService = Depends(get_coupon_service)
):
    """Get a single coupon by id."""
    return await coupon_service.get_coupon(coupon_id)


@router.patch("/{coupon_id}", response_model=CouponResponse)
async def update_coupon(
    coupon_id: str,
    updates: CouponUpdate,
    current_user: TokenData = Depends(require_admin),
    coupon_service: CouponService = Depends(get_coupon_service)
):
    """Update a coupon (code and scope are immutable)."""
    return await coupon_service.update_coupon(coupon_id, updates.model_dump(exclude_unset=True))


@router.delete("/{coupon_id}", response_model=CouponResponse)
async def deactivate_coupon(
    coupon_id: str,
    current_user: TokenData = Depends(require_admin),
    coupon_service: CouponService = Depends(get_coupon_service)
):
    """Deactivate a coupon (kept for redemption history)."""
    return await coupon_service.deactivate_coupon(coupon_id)
