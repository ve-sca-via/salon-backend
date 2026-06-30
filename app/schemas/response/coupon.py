"""
Response Pydantic schemas for coupon endpoints.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CouponResponse(BaseModel):
    id: str
    code: str
    title: str
    scope: str
    salon_id: Optional[str] = None
    created_by: Optional[str] = None
    funded_by: str
    applies_to: str
    discount_type: str
    discount_value: float
    max_discount_cap: Optional[float] = None
    min_order_amount: Optional[float] = None
    first_time_scope: Optional[str] = None
    usage_limit_total: Optional[int] = None
    usage_limit_per_user: Optional[int] = None
    used_count: int = 0
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        extra = "allow"


class CouponDiscountBreakdown(BaseModel):
    """Pricing breakdown returned when a coupon is validated/applied."""
    subtotal_service_price: float          # service total before coupon (post-sale)
    discount_amount: float                 # discount on service price
    service_total_due: float               # pay-at-salon after discount
    convenience_fee_base: float            # fee before coupon
    convenience_fee_discount: float        # discount on fee
    convenience_fee_due: float             # pay-now after discount
    total_amount: float                    # service_total_due + convenience_fee_due
    discount_source: Optional[str] = None  # 'coupon' | 'sale' (which won best-of on services)


class CouponValidationResult(BaseModel):
    """Result of validating a coupon against a cart."""
    valid: bool
    reason: Optional[str] = None           # human-readable reason when invalid
    coupon_id: Optional[str] = None
    coupon_code: Optional[str] = None
    breakdown: Optional[CouponDiscountBreakdown] = None
