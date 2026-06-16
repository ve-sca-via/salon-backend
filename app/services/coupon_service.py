"""
Coupon Service - Business Logic Layer

Owns coupon lifecycle and validation:
- Admin / vendor CRUD for coupons
- Eligibility validation against a cart (scope, window, min-order, first-time, limits)
- Atomic redemption via the redeem_coupon() Postgres function

Pricing math (best-of vs salon sale, fee waivers) lives in PricingService, which
calls get_valid_coupon() here. Keeping the two separate mirrors the existing
service-layer split (e.g. PaymentService vs BookingService).
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import logging

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse a Supabase timestamptz string/`datetime` into an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Machine reason code -> human-readable message for invalid coupons
_REASON_MESSAGES = {
    "not_found": "This coupon code is not valid.",
    "inactive": "This coupon is no longer active.",
    "not_started": "This coupon is not active yet.",
    "expired": "This coupon has expired.",
    "wrong_salon": "This coupon cannot be used at this salon.",
    "min_order_not_met": "Your order does not meet the minimum amount for this coupon.",
    "not_first_time": "This coupon is only valid for first-time customers.",
    "total_limit_reached": "This coupon has reached its usage limit.",
    "per_user_limit_reached": "You have already used this coupon.",
}


class CouponService:
    """Service for coupon CRUD, validation and redemption."""

    def __init__(self, db_client):
        self.db = db_client

    # =====================================================
    # VALIDATION (used by PricingService)
    # =====================================================
    async def get_valid_coupon(
        self,
        code: str,
        salon_id: str,
        customer_id: str,
        service_subtotal: float,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Resolve a coupon code and check eligibility against a cart.

        Returns (coupon_row, None) when usable, or (None, reason_message) otherwise.
        Usage-limit checks here are a best-effort pre-check for UX; the authoritative
        enforcement happens atomically in redeem().
        """
        if not code:
            return None, None

        normalized = code.strip().upper()

        # Active coupon for this code (unique index guarantees at most one)
        resp = self.db.table("coupons").select("*").eq("is_active", True).execute()
        coupon = next(
            (c for c in (resp.data or []) if (c.get("code") or "").upper() == normalized),
            None,
        )
        if not coupon:
            return None, _REASON_MESSAGES["not_found"]

        # Validity window
        now = datetime.now(timezone.utc)
        valid_from = _parse_dt(coupon.get("valid_from"))
        valid_until = _parse_dt(coupon.get("valid_until"))
        if valid_from and now < valid_from:
            return None, _REASON_MESSAGES["not_started"]
        if valid_until and now > valid_until:
            return None, _REASON_MESSAGES["expired"]

        # Scope: platform coupons work anywhere; vendor coupons only at their salon
        if coupon.get("scope") == "vendor" and coupon.get("salon_id") != salon_id:
            return None, _REASON_MESSAGES["wrong_salon"]

        # Minimum order amount (checked against the service subtotal)
        min_order = coupon.get("min_order_amount")
        if min_order is not None and service_subtotal < float(min_order):
            return None, _REASON_MESSAGES["min_order_not_met"]

        # First-time-user restriction
        first_time_scope = coupon.get("first_time_scope")
        if first_time_scope and not await self._is_first_time(customer_id, salon_id, first_time_scope):
            return None, _REASON_MESSAGES["not_first_time"]

        # Usage limits (soft pre-check)
        total_limit = coupon.get("usage_limit_total")
        if total_limit is not None and int(coupon.get("used_count") or 0) >= int(total_limit):
            return None, _REASON_MESSAGES["total_limit_reached"]

        per_user_limit = coupon.get("usage_limit_per_user")
        if per_user_limit is not None:
            used_by_user = self.db.table("coupon_redemptions").select(
                "id", count="exact"
            ).eq("coupon_id", coupon["id"]).eq("user_id", customer_id).execute()
            if (used_by_user.count or 0) >= int(per_user_limit):
                return None, _REASON_MESSAGES["per_user_limit_reached"]

        return coupon, None

    async def _is_first_time(self, customer_id: str, salon_id: str, scope: str) -> bool:
        """True if the customer has no prior bookings (platform-wide or with this salon)."""
        query = self.db.table("bookings").select("id", count="exact").eq(
            "customer_id", customer_id
        ).is_("deleted_at", "null")
        if scope == "vendor":
            query = query.eq("salon_id", salon_id)
        result = query.execute()
        return (result.count or 0) == 0

    @staticmethod
    def reason_message(reason_code: str) -> str:
        """Map a redeem_coupon() reason code to a human-readable message."""
        return _REASON_MESSAGES.get(reason_code, "This coupon could not be applied.")

    # =====================================================
    # REDEMPTION (atomic, used by BookingService)
    # =====================================================
    async def redeem(
        self,
        coupon_id: str,
        user_id: str,
        booking_id: str,
        discount_amount: float,
    ) -> Dict[str, Any]:
        """
        Atomically record a redemption and enforce usage limits via redeem_coupon().
        Returns {success, reason, was_already_redeemed}. Never raises on a limit
        failure — booking creation must not be rolled back by a redemption race; the
        caller logs and proceeds (the discount was already validated at order time).
        """
        try:
            resp = self.db.rpc("redeem_coupon", {
                "p_coupon_id": coupon_id,
                "p_user_id": user_id,
                "p_booking_id": booking_id,
                "p_discount_amount": round(float(discount_amount or 0), 2),
            }).execute()
            row = resp.data[0] if resp.data else {}
            return {
                "success": bool(row.get("success")),
                "reason": row.get("reason"),
                "was_already_redeemed": bool(row.get("was_already_redeemed")),
            }
        except Exception as e:
            logger.error(f"Coupon redemption RPC failed for coupon {coupon_id}: {e}")
            return {"success": False, "reason": "rpc_error", "was_already_redeemed": False}

    # =====================================================
    # CRUD
    # =====================================================
    async def create_coupon(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a coupon. `data` must already carry scope/salon_id/funded_by/created_by."""
        if data.get("code"):
            data["code"] = data["code"].strip().upper()
        try:
            resp = self.db.table("coupons").insert(data).execute()
        except Exception as e:
            msg = str(e).lower()
            if "idx_coupons_active_code" in msg or "duplicate" in msg or "unique" in msg:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An active coupon with this code already exists.",
                )
            logger.error(f"Failed to create coupon: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create coupon.",
            )
        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create coupon.",
            )
        return resp.data[0]

    async def list_coupons(
        self,
        scope: Optional[str] = None,
        salon_id: Optional[str] = None,
        include_inactive: bool = True,
    ) -> List[Dict[str, Any]]:
        query = self.db.table("coupons").select("*")
        if scope:
            query = query.eq("scope", scope)
        if salon_id:
            query = query.eq("salon_id", salon_id)
        if not include_inactive:
            query = query.eq("is_active", True)
        resp = query.order("created_at", desc=True).execute()
        return resp.data or []

    async def get_coupon(self, coupon_id: str) -> Dict[str, Any]:
        resp = self.db.table("coupons").select("*").eq("id", coupon_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found")
        return resp.data

    async def update_coupon(
        self,
        coupon_id: str,
        updates: Dict[str, Any],
        salon_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a coupon. When salon_id is given, the coupon must belong to it (vendor guard)."""
        existing = await self.get_coupon(coupon_id)
        if salon_id is not None and existing.get("salon_id") != salon_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only modify your own coupons.",
            )
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return existing
        resp = self.db.table("coupons").update(clean).eq("id", coupon_id).execute()
        return resp.data[0] if resp.data else existing

    async def deactivate_coupon(
        self,
        coupon_id: str,
        salon_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Soft-disable a coupon (keeps redemption history). Vendor-guarded when salon_id given."""
        return await self.update_coupon(coupon_id, {"is_active": False}, salon_id=salon_id)
