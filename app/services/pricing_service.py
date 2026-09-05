"""
Pricing Service - Single source of truth for booking checkout math.

Used by both PaymentService (to size the Razorpay convenience-fee order) and
BookingService / CustomerService (to persist the booking) so the amount charged
and the amount recorded always agree.

Responsibilities:
- Sum original vs sale (discounted_price) service totals.
- Compute the convenience fee on the ORIGINAL service price (unchanged behaviour).
- Resolve an optional coupon via CouponService and apply it with **best-of**
  semantics against any active salon sale (no stacking) for service coupons;
  convenience-fee coupons are applied orthogonally.

Centralising this also fixes the historical gap where salon-promo min/max limits
were never enforced at checkout — coupon limits and caps now live in one place.
"""
from typing import Dict, Any, List, Optional
import logging

from app.services.coupon_service import CouponService

logger = logging.getLogger(__name__)


class LineItem:
    """Normalized cart/booking line used for pricing (built by each caller)."""

    __slots__ = ("original_unit_price", "effective_unit_price", "quantity")

    def __init__(self, original_unit_price: float, effective_unit_price: float, quantity: int):
        self.original_unit_price = float(original_unit_price)
        # Effective = sale/discounted price when present, else original
        self.effective_unit_price = float(effective_unit_price)
        self.quantity = int(quantity)


def effective_service_price(service_details: Dict[str, Any]) -> float:
    """Effective price for a service: discounted_price when present, else base price."""
    discounted_price = service_details.get("discounted_price")
    if discounted_price is not None:
        return float(discounted_price)
    return float(service_details.get("price", 0.0))


def _discount(base: float, discount_type: str, value: float, cap: Optional[float]) -> float:
    """Compute a discount on `base`, never exceeding the base, honoring an optional cap."""
    if base <= 0:
        return 0.0
    if discount_type == "percentage":
        amount = base * float(value) / 100.0
    else:  # flat_amount
        amount = float(value)
    amount = min(amount, base)
    if cap is not None:
        amount = min(amount, float(cap))
    return round(max(amount, 0.0), 2)


class PricingService:
    def __init__(self, db_client):
        self.db = db_client
        self.coupon_service = CouponService(db_client)

    async def compute_booking_pricing(
        self,
        line_items: List[LineItem],
        convenience_fee_percentage: float,
        salon_id: str,
        customer_id: str,
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return the full pricing breakdown for a cart/booking.

        Keys:
          original_service_price, subtotal_service_price, discount_amount,
          service_total_due, convenience_fee_base, convenience_fee_discount,
          convenience_fee_due, total_amount, pay_now, pay_at_salon,
          coupon_id, coupon_code, discount_source, coupon_reason
        """
        original_service_price = round(
            sum(li.original_unit_price * li.quantity for li in line_items), 2
        )
        subtotal_service_price = round(
            sum(li.effective_unit_price * li.quantity for li in line_items), 2
        )
        sale_discount = round(max(original_service_price - subtotal_service_price, 0.0), 2)

        convenience_fee_base = round(
            original_service_price * float(convenience_fee_percentage) / 100.0, 2
        )

        # Defaults: no coupon applied
        service_total_due = subtotal_service_price
        discount_amount = 0.0
        convenience_fee_discount = 0.0
        convenience_fee_due = convenience_fee_base
        coupon_id: Optional[str] = None
        applied_code: Optional[str] = None
        discount_source: Optional[str] = "sale" if sale_discount > 0 else None
        coupon_reason: Optional[str] = None
        # Gross coupon discount: the full value of the coupon, independent of any
        # salon sale. Used for settlement/reporting (coupon_redemptions.gross_discount);
        # `discount_amount` stays the net delta recorded against the booking.
        coupon_gross_discount = 0.0

        if coupon_code:
            coupon, reason = await self.coupon_service.get_valid_coupon(
                code=coupon_code,
                salon_id=salon_id,
                customer_id=customer_id,
                service_subtotal=subtotal_service_price,
            )
            if not coupon:
                coupon_reason = reason
            elif coupon["applies_to"] == "service":
                # Best-of against the active salon sale (no stacking)
                coupon_discount = _discount(
                    original_service_price,
                    coupon["discount_type"],
                    coupon["discount_value"],
                    coupon.get("max_discount_cap"),
                )
                if coupon_discount > sale_discount:
                    service_total_due = round(original_service_price - coupon_discount, 2)
                    discount_amount = round(subtotal_service_price - service_total_due, 2)
                    discount_source = "coupon"
                    coupon_id = coupon["id"]
                    applied_code = coupon["code"]
                    coupon_gross_discount = coupon_discount
                else:
                    coupon_reason = "A better discount is already applied at this salon."
            elif coupon["applies_to"] == "convenience_fee":
                fee_discount = _discount(
                    convenience_fee_base,
                    coupon["discount_type"],
                    coupon["discount_value"],
                    coupon.get("max_discount_cap"),
                )
                if fee_discount > 0:
                    convenience_fee_discount = fee_discount
                    convenience_fee_due = round(convenience_fee_base - fee_discount, 2)
                    coupon_id = coupon["id"]
                    applied_code = coupon["code"]
                    coupon_gross_discount = fee_discount

        total_amount = round(service_total_due + convenience_fee_due, 2)

        return {
            "original_service_price": original_service_price,
            "subtotal_service_price": subtotal_service_price,
            "discount_amount": discount_amount,
            "service_total_due": service_total_due,
            "convenience_fee_base": convenience_fee_base,
            "convenience_fee_discount": convenience_fee_discount,
            "convenience_fee_due": convenience_fee_due,
            "total_amount": total_amount,
            "pay_now": convenience_fee_due,
            "pay_at_salon": service_total_due,
            "coupon_id": coupon_id,
            "coupon_code": applied_code,
            "coupon_gross_discount": round(coupon_gross_discount, 2),
            "discount_source": discount_source,
            "coupon_reason": coupon_reason,
        }
