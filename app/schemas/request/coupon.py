"""
Request Pydantic schemas for coupon management and validation.
All coupon request models live here for consistency.
"""
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator
from typing import Optional


# =====================================================
# SHARED VALIDATION
# =====================================================

_DISCOUNT_TYPES = "^(percentage|flat_amount)$"
_APPLIES_TO = "^(service|convenience_fee)$"
_FIRST_TIME_SCOPE = "^(platform|vendor)$"


def _validate_future_valid_until(v: Optional[str]) -> Optional[str]:
    """Parse an ISO `valid_until` and reject values in the past (would create a
    dead-on-arrival coupon). Returns the original string when valid/None."""
    if v is None:
        return v
    s = str(v).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError("valid_until must be a valid ISO datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt < datetime.now(timezone.utc):
        raise ValueError("valid_until cannot be in the past")
    return v


class CouponBase(BaseModel):
    """Common coupon fields shared by create/update."""
    code: str = Field(..., min_length=3, max_length=40, description="Shareable coupon code")
    title: str = Field(..., min_length=2, max_length=255)
    applies_to: str = Field(..., pattern=_APPLIES_TO, description="service | convenience_fee")
    discount_type: str = Field(..., pattern=_DISCOUNT_TYPES, description="percentage | flat_amount")
    discount_value: float = Field(..., gt=0)
    max_discount_cap: Optional[float] = Field(None, ge=0, description="Cap for 'upto X%' style discounts")
    min_order_amount: Optional[float] = Field(None, ge=0, description="Minimum service subtotal to qualify")
    first_time_scope: Optional[str] = Field(
        None, pattern=_FIRST_TIME_SCOPE,
        description="Restrict to first-time users: 'platform' (first booking ever) or 'vendor' (first with this salon). Null = anyone."
    )
    usage_limit_total: Optional[int] = Field(None, ge=0, description="Total redemptions allowed (null = unlimited)")
    usage_limit_per_user: Optional[int] = Field(1, ge=0, description="Redemptions allowed per user (null = unlimited)")
    valid_from: Optional[str] = Field(None, description="ISO datetime; defaults to now")
    valid_until: Optional[str] = Field(None, description="ISO datetime; null = no expiry")

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("discount_value")
    @classmethod
    def _percentage_le_100(cls, v: float, info):
        if info.data.get("discount_type") == "percentage" and v > 100:
            raise ValueError("Percentage discount cannot exceed 100")
        return v

    @field_validator("valid_until")
    @classmethod
    def _valid_until_future(cls, v):
        return _validate_future_valid_until(v)


class VendorCouponCreate(CouponBase):
    """Coupon created by a vendor (always scoped to their own salon)."""

    @field_validator("applies_to")
    @classmethod
    def _no_convenience_fee_for_vendors(cls, v: str) -> str:
        # The convenience fee is platform revenue. Vendors fund their own
        # discounts, so they may only discount the service price — not waive a
        # fee they don't collect. Admins issue convenience-fee coupons.
        if v == "convenience_fee":
            raise ValueError(
                "Vendors can only create service-discount coupons. "
                "Convenience-fee coupons are issued by the platform."
            )
        return v


class AdminCouponCreate(CouponBase):
    """Coupon created by an admin. Can be platform-wide or scoped to a salon."""
    scope: str = Field("platform", pattern="^(platform|vendor)$")
    salon_id: Optional[str] = Field(None, description="Required when scope='vendor'")
    funded_by: str = Field("platform", pattern="^(platform|vendor)$")

    @field_validator("salon_id")
    @classmethod
    def _salon_required_for_vendor_scope(cls, v, info):
        if info.data.get("scope") == "vendor" and not v:
            raise ValueError("salon_id is required when scope is 'vendor'")
        return v


class CouponUpdate(BaseModel):
    """Partial update for a coupon. Code/scope are immutable post-creation."""
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    discount_value: Optional[float] = Field(None, gt=0)
    max_discount_cap: Optional[float] = Field(None, ge=0)
    min_order_amount: Optional[float] = Field(None, ge=0)
    usage_limit_total: Optional[int] = Field(None, ge=0)
    usage_limit_per_user: Optional[int] = Field(None, ge=0)
    valid_until: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("valid_until")
    @classmethod
    def _valid_until_future(cls, v):
        return _validate_future_valid_until(v)


class CouponValidateRequest(BaseModel):
    """Preview a coupon against the caller's current cart ('Apply coupon' button)."""
    code: str = Field(..., min_length=1, max_length=40)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        return v.strip().upper()
