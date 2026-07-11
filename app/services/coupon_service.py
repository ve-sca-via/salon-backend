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

        # Active coupon for this code. Codes are stored uppercase (enforced on
        # create), and idx_coupons_active_code guarantees at most one active row
        # per code — so this is an indexed point lookup, not a full scan.
        resp = (
            self.db.table("coupons")
            .select("*")
            .eq("is_active", True)
            .eq("code", normalized)
            .execute()
        )
        coupon = (resp.data or [None])[0]
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
        """
        True if the customer has no prior *non-cancelled* bookings (platform-wide
        or with this salon). Cancelled bookings are excluded so a cancellation
        does not permanently disqualify a customer from first-time offers (D3).
        This is a UX pre-check; redeem_coupon() enforces the same rule atomically.
        """
        query = self.db.table("bookings").select("id", count="exact").eq(
            "customer_id", customer_id
        ).is_("deleted_at", "null").neq("status", "cancelled")
        if scope == "vendor":
            query = query.eq("salon_id", salon_id)
        result = query.execute()
        return (result.count or 0) == 0

    @staticmethod
    def reason_message(reason_code: str) -> str:
        """Map a redeem_coupon() reason code to a human-readable message."""
        return _REASON_MESSAGES.get(reason_code, "This coupon could not be applied.")

    # =====================================================
    # DISCOVERY (customer-facing "available coupons" list)
    # =====================================================
    @staticmethod
    def _coupon_summary(coupon: Dict[str, Any]) -> str:
        """Headline discount label, e.g. '10% OFF up to ₹100' or '₹50 OFF'."""
        dvalue = coupon.get("discount_value") or 0
        try:
            dvalue = float(dvalue)
        except (TypeError, ValueError):
            dvalue = 0
        amount = int(dvalue) if float(dvalue).is_integer() else round(dvalue, 2)
        is_fee = coupon.get("applies_to") == "convenience_fee"

        if coupon.get("discount_type") == "percentage":
            head = f"{amount}% OFF"
            cap = coupon.get("max_discount_cap")
            if cap is not None:
                cap_amt = int(float(cap)) if float(cap).is_integer() else round(float(cap), 2)
                head = f"{head} up to ₹{cap_amt}"
        else:  # flat_amount
            head = f"₹{amount} OFF"

        return f"{head} on booking fee" if is_fee else head

    @staticmethod
    def _coupon_condition(coupon: Dict[str, Any]) -> Optional[str]:
        """Human-readable eligibility condition shown under the headline."""
        parts: List[str] = []
        min_order = coupon.get("min_order_amount")
        if min_order is not None and float(min_order) > 0:
            min_amt = int(float(min_order)) if float(min_order).is_integer() else round(float(min_order), 2)
            parts.append(f"On orders above ₹{min_amt}")
        if coupon.get("first_time_scope"):
            parts.append("First booking only")
        return " • ".join(parts) if parts else None

    def _to_public_coupon(self, coupon: Dict[str, Any]) -> Dict[str, Any]:
        """Project a coupon row down to the fields safe to show a customer."""
        return {
            "id": coupon["id"],
            "code": coupon["code"],
            "title": coupon.get("title"),
            "scope": coupon.get("scope"),
            "salon_id": coupon.get("salon_id"),
            "applies_to": coupon.get("applies_to"),
            "discount_type": coupon.get("discount_type"),
            "discount_value": float(coupon.get("discount_value") or 0),
            "max_discount_cap": coupon.get("max_discount_cap"),
            "min_order_amount": coupon.get("min_order_amount"),
            "first_time_scope": coupon.get("first_time_scope"),
            "valid_until": coupon.get("valid_until"),
            "summary": self._coupon_summary(coupon),
            "subtitle": self._coupon_condition(coupon),
        }

    async def list_available_coupons(
        self,
        customer_id: str,
        salon_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Coupons a customer can currently discover and apply.

        Always includes active, in-window platform coupons (usable anywhere); when
        `salon_id` is given, also includes that salon's active vendor coupons.
        Filters out coupons the customer can't actually use: expired/not-started,
        total-limit exhausted, per-user-limit reached, and first-time offers the
        customer is no longer eligible for. Min-order stays in (surfaced as a
        condition) — the authoritative check still runs on apply (validate_coupon).
        """
        now = datetime.now(timezone.utc)
        resp = self.db.table("coupons").select("*").eq("is_active", True).execute()
        all_active = resp.data or []

        # Scope + validity window + total-usage pre-filter
        candidates: List[Dict[str, Any]] = []
        for coupon in all_active:
            scope = coupon.get("scope")
            if scope == "platform":
                pass
            elif scope == "vendor":
                if not salon_id or coupon.get("salon_id") != salon_id:
                    continue
            else:
                continue

            valid_from = _parse_dt(coupon.get("valid_from"))
            valid_until = _parse_dt(coupon.get("valid_until"))
            if valid_from and now < valid_from:
                continue
            if valid_until and now > valid_until:
                continue

            total_limit = coupon.get("usage_limit_total")
            if total_limit is not None and int(coupon.get("used_count") or 0) >= int(total_limit):
                continue

            candidates.append(coupon)

        if not candidates:
            return []

        # Per-user redemption counts in one query
        coupon_ids = [c["id"] for c in candidates]
        used_by_user: Dict[str, int] = {}
        redemptions = (
            self.db.table("coupon_redemptions")
            .select("coupon_id")
            .eq("user_id", customer_id)
            .in_("coupon_id", coupon_ids)
            .execute()
        )
        for row in (redemptions.data or []):
            cid = row.get("coupon_id")
            used_by_user[cid] = used_by_user.get(cid, 0) + 1

        # First-time eligibility is the same for all coupons of a given scope —
        # compute at most once per scope.
        first_time_cache: Dict[str, bool] = {}

        available: List[Dict[str, Any]] = []
        for coupon in candidates:
            per_user_limit = coupon.get("usage_limit_per_user")
            if per_user_limit is not None and used_by_user.get(coupon["id"], 0) >= int(per_user_limit):
                continue

            first_time_scope = coupon.get("first_time_scope")
            if first_time_scope:
                # A vendor-scoped first-time check needs a salon context.
                if first_time_scope == "vendor" and not salon_id:
                    continue
                if first_time_scope not in first_time_cache:
                    first_time_cache[first_time_scope] = await self._is_first_time(
                        customer_id, salon_id, first_time_scope
                    )
                if not first_time_cache[first_time_scope]:
                    continue

            available.append(self._to_public_coupon(coupon))

        return available

    def _is_publicly_listable(self, coupon: Dict[str, Any], now: datetime) -> bool:
        """
        Whether an active coupon should be shown on public marketing surfaces
        (salon cards, salon-detail offers carousel). No per-user eligibility —
        just in-window and not globally exhausted. The authoritative per-user
        checks still run on apply (get_valid_coupon / redeem_coupon).
        """
        valid_from = _parse_dt(coupon.get("valid_from"))
        valid_until = _parse_dt(coupon.get("valid_until"))
        if valid_from and now < valid_from:
            return False
        if valid_until and now > valid_until:
            return False
        total_limit = coupon.get("usage_limit_total")
        if total_limit is not None and int(coupon.get("used_count") or 0) >= int(total_limit):
            return False
        return True

    def public_vendor_coupons_by_salon(
        self, salon_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Active, in-window vendor coupons grouped by salon id, projected to public
        display fields. One query for the whole set (no N+1 for salon lists).
        Public/unfiltered — usable by logged-out browsers.
        """
        if not salon_ids:
            return {}
        now = datetime.now(timezone.utc)
        resp = (
            self.db.table("coupons")
            .select("*")
            .eq("is_active", True)
            .eq("scope", "vendor")
            .in_("salon_id", salon_ids)
            .execute()
        )
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for coupon in (resp.data or []):
            if not self._is_publicly_listable(coupon, now):
                continue
            sid = coupon.get("salon_id")
            grouped.setdefault(sid, []).append(self._to_public_coupon(coupon))
        return grouped

    def public_platform_coupons(self) -> List[Dict[str, Any]]:
        """
        Active, in-window platform coupons (usable at any salon), projected to
        public display fields. Public/unfiltered.
        """
        now = datetime.now(timezone.utc)
        resp = (
            self.db.table("coupons")
            .select("*")
            .eq("is_active", True)
            .eq("scope", "platform")
            .execute()
        )
        return [
            self._to_public_coupon(c)
            for c in (resp.data or [])
            if self._is_publicly_listable(c, now)
        ]

    # =====================================================
    # REDEMPTION (atomic, used by BookingService)
    # =====================================================
    async def redeem(
        self,
        coupon_id: str,
        user_id: str,
        booking_id: str,
        discount_amount: float,
        gross_discount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Atomically record a redemption and enforce usage limits via redeem_coupon().
        `discount_amount` is the net delta recorded against the booking; `gross_discount`
        is the full coupon value for settlement/reporting (defaults to discount_amount).
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
                "p_gross_discount": round(float(
                    gross_discount if gross_discount is not None else (discount_amount or 0)
                ), 2),
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
        # Vendor-scoped coupons must point at a real salon. The FK would catch a
        # bad id with an opaque 500; check up front for a clean 404 (admins can
        # pass an arbitrary salon_id).
        if data.get("scope") == "vendor" and data.get("salon_id"):
            salon = (
                self.db.table("salons").select("id").eq("id", data["salon_id"]).execute()
            )
            if not (salon.data or []):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Salon not found for this coupon.",
                )
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
