"""
Mocked unit tests for the coupon / pricing system.

Two layers, no Supabase stack required:
  1. PricingService.compute_booking_pricing — pure math, with CouponService stubbed
     (service %/flat, caps, best-of vs salon sale, convenience-fee waivers).
  2. CouponService.get_valid_coupon — eligibility rules against a small in-memory
     fake DB (scope, window, min-order, first-time, usage limits).

No marker -> runs in the fast (no-stack) job.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.services.pricing_service import PricingService, LineItem, _discount
from app.services.coupon_service import CouponService


# =====================================================================
# Helpers
# =====================================================================
def _coupon(**overrides):
    base = {
        "id": "coupon-1",
        "code": "SAVE",
        "scope": "platform",
        "salon_id": None,
        "applies_to": "service",
        "discount_type": "percentage",
        "discount_value": 20,
        "max_discount_cap": None,
        "min_order_amount": None,
        "first_time_scope": None,
        "usage_limit_total": None,
        "usage_limit_per_user": 1,
        "used_count": 0,
        "valid_from": None,
        "valid_until": None,
        "is_active": True,
    }
    base.update(overrides)
    return base


class _StubCouponService:
    """Stand-in for CouponService used by PricingService pricing-math tests."""
    def __init__(self, coupon=None, reason=None):
        self._coupon = coupon
        self._reason = reason

    async def get_valid_coupon(self, code, salon_id, customer_id, service_subtotal):
        return self._coupon, self._reason


def _pricing_with(coupon=None, reason=None):
    ps = PricingService(db_client=None)
    ps.coupon_service = _StubCouponService(coupon, reason)
    return ps


# =====================================================================
# 1. PricingService math
# =====================================================================
async def test_no_coupon_no_sale():
    ps = _pricing_with()
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code=None,
    )
    assert r["subtotal_service_price"] == 1000
    assert r["service_total_due"] == 1000
    assert r["convenience_fee_base"] == 100
    assert r["convenience_fee_due"] == 100
    assert r["total_amount"] == 1100
    assert r["coupon_id"] is None
    assert r["discount_source"] is None


async def test_sale_only_sets_source_sale():
    ps = _pricing_with()
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 800, 1)],   # vendor sale already on the service
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code=None,
    )
    assert r["subtotal_service_price"] == 800
    assert r["service_total_due"] == 800
    # convenience fee is on ORIGINAL price (unchanged behaviour)
    assert r["convenience_fee_base"] == 100
    assert r["discount_source"] == "sale"
    assert r["coupon_id"] is None


async def test_service_percentage_coupon_applies():
    ps = _pricing_with(_coupon(discount_type="percentage", discount_value=20))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="SAVE",
    )
    assert r["service_total_due"] == 800
    assert r["discount_amount"] == 200
    assert r["discount_source"] == "coupon"
    assert r["coupon_id"] == "coupon-1"
    assert r["total_amount"] == 900   # 800 + 100 fee


async def test_service_flat_coupon_applies():
    ps = _pricing_with(_coupon(discount_type="flat_amount", discount_value=150))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="FLAT150",
    )
    assert r["service_total_due"] == 850
    assert r["discount_amount"] == 150


async def test_service_coupon_capped():
    # 50% of 1000 = 500, but cap is 120
    ps = _pricing_with(_coupon(discount_type="percentage", discount_value=50, max_discount_cap=120))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="UPTO50",
    )
    assert r["discount_amount"] == 120
    assert r["service_total_due"] == 880


async def test_best_of_coupon_beats_sale():
    # sale gives 200 off (800); coupon gives 30% = 300 off -> coupon wins
    ps = _pricing_with(_coupon(discount_type="percentage", discount_value=30))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 800, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="SAVE30",
    )
    assert r["service_total_due"] == 700      # 1000 - 300
    assert r["discount_amount"] == 100        # extra over the 800 sale baseline
    assert r["discount_source"] == "coupon"
    assert r["coupon_id"] == "coupon-1"


async def test_best_of_sale_beats_coupon_no_apply():
    # sale gives 300 off (700); coupon only 10% = 100 off -> sale wins, coupon NOT applied
    ps = _pricing_with(_coupon(discount_type="percentage", discount_value=10))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 700, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="SAVE10",
    )
    assert r["service_total_due"] == 700
    assert r["discount_amount"] == 0
    assert r["coupon_id"] is None
    assert r["discount_source"] == "sale"
    assert r["coupon_reason"]  # tells the user a better discount already applies


async def test_convenience_fee_percentage_coupon():
    ps = _pricing_with(_coupon(applies_to="convenience_fee", discount_type="percentage", discount_value=50))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="FEE50",
    )
    assert r["convenience_fee_base"] == 100
    assert r["convenience_fee_discount"] == 50
    assert r["convenience_fee_due"] == 50
    assert r["service_total_due"] == 1000     # services untouched
    assert r["total_amount"] == 1050
    assert r["coupon_id"] == "coupon-1"


async def test_convenience_fee_full_waiver():
    ps = _pricing_with(_coupon(applies_to="convenience_fee", discount_type="percentage", discount_value=100))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="NOFEE",
    )
    assert r["convenience_fee_due"] == 0
    assert r["total_amount"] == 1000


async def test_invalid_coupon_reason_passthrough():
    ps = _pricing_with(coupon=None, reason="This coupon code is not valid.")
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="BOGUS",
    )
    assert r["coupon_id"] is None
    assert r["coupon_reason"] == "This coupon code is not valid."
    assert r["total_amount"] == 1100


def test_discount_helper_never_exceeds_base():
    assert _discount(100, "flat_amount", 500, None) == 100
    assert _discount(100, "percentage", 50, None) == 50
    assert _discount(100, "percentage", 50, 30) == 30
    assert _discount(0, "percentage", 50, None) == 0


# =====================================================================
# 2. CouponService.get_valid_coupon eligibility
# =====================================================================
class _CResp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _CQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []   # list of (kind, col, val)
        self._count = False

    def select(self, cols="*", count=None):
        self._count = count == "exact"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, *args, **kwargs):
        return self

    def _match(self, row):
        for kind, col, val in self._filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "neq" and row.get(col) == val:
                return False
            if kind == "is" and val == "null" and row.get(col) is not None:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        matched = [dict(r) for r in self._rows if self._match(r)]
        return _CResp(matched, count=len(matched) if self._count else None)


class _CTable:
    def __init__(self):
        self.rows = []

    def select(self, cols="*", count=None):
        return _CQuery(self.rows).select(cols, count=count)


class _CDB:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _CTable())


def _db_with_coupon(**overrides):
    db = _CDB()
    db.table("coupons").rows.append(_coupon(**overrides))
    return db


async def test_valid_coupon_resolves():
    svc = CouponService(_db_with_coupon())
    coupon, reason = await svc.get_valid_coupon("save", "s1", "u1", 1000)
    assert coupon is not None and reason is None


async def test_unknown_code_not_found():
    svc = CouponService(_db_with_coupon())
    coupon, reason = await svc.get_valid_coupon("NOPE", "s1", "u1", 1000)
    assert coupon is None and "not valid" in reason


async def test_expired_coupon():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    svc = CouponService(_db_with_coupon(valid_until=past))
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "expired" in reason


async def test_not_started_coupon():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    svc = CouponService(_db_with_coupon(valid_from=future))
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "not active yet" in reason


async def test_vendor_scope_wrong_salon():
    svc = CouponService(_db_with_coupon(scope="vendor", salon_id="other-salon"))
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "this salon" in reason


async def test_min_order_not_met():
    svc = CouponService(_db_with_coupon(min_order_amount=500))
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 200)
    assert coupon is None and "minimum" in reason


async def test_total_limit_reached():
    svc = CouponService(_db_with_coupon(usage_limit_total=5, used_count=5))
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "usage limit" in reason


async def test_per_user_limit_reached():
    db = _db_with_coupon(usage_limit_per_user=1)
    db.table("coupon_redemptions").rows.append(
        {"id": "r1", "coupon_id": "coupon-1", "user_id": "u1"}
    )
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "already used" in reason


async def test_first_time_platform_blocks_returning_customer():
    db = _db_with_coupon(first_time_scope="platform")
    db.table("bookings").rows.append(
        {"id": "b1", "customer_id": "u1", "salon_id": "s9", "deleted_at": None}
    )
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "first-time" in reason


async def test_first_time_platform_allows_new_customer():
    db = _db_with_coupon(first_time_scope="platform")
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is not None and reason is None


async def test_first_time_vendor_allows_new_to_this_salon():
    # Customer has a booking elsewhere but none at this salon -> still "first time" here
    db = _db_with_coupon(first_time_scope="vendor")
    db.table("bookings").rows.append(
        {"id": "b1", "customer_id": "u1", "salon_id": "other", "deleted_at": None}
    )
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is not None and reason is None


async def test_first_time_ignores_cancelled_booking():
    # A cancelled booking must NOT disqualify a customer from first-time offers (D3)
    db = _db_with_coupon(first_time_scope="platform")
    db.table("bookings").rows.append(
        {"id": "b1", "customer_id": "u1", "salon_id": "s1", "deleted_at": None, "status": "cancelled"}
    )
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is not None and reason is None


async def test_first_time_blocks_on_active_booking():
    # A non-cancelled booking still blocks first-time
    db = _db_with_coupon(first_time_scope="platform")
    db.table("bookings").rows.append(
        {"id": "b1", "customer_id": "u1", "salon_id": "s1", "deleted_at": None, "status": "confirmed"}
    )
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_coupon("SAVE", "s1", "u1", 1000)
    assert coupon is None and "first-time" in reason


# =====================================================================
# 2b. CouponService.list_available_coupons (customer discovery)
# =====================================================================
async def test_available_includes_platform_without_salon():
    svc = CouponService(_db_with_coupon(scope="platform", salon_id=None))
    out = await svc.list_available_coupons(customer_id="u1", salon_id=None)
    assert [c["code"] for c in out] == ["SAVE"]
    # Display fields are projected
    assert out[0]["summary"] == "20% OFF"


async def test_available_excludes_vendor_coupon_without_salon():
    svc = CouponService(_db_with_coupon(scope="vendor", salon_id="s1"))
    out = await svc.list_available_coupons(customer_id="u1", salon_id=None)
    assert out == []


async def test_available_includes_vendor_coupon_for_matching_salon():
    svc = CouponService(_db_with_coupon(scope="vendor", salon_id="s1"))
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert [c["code"] for c in out] == ["SAVE"]


async def test_available_excludes_vendor_coupon_for_other_salon():
    svc = CouponService(_db_with_coupon(scope="vendor", salon_id="other"))
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out == []


async def test_available_excludes_expired():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    svc = CouponService(_db_with_coupon(valid_until=past))
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out == []


async def test_available_excludes_total_limit_reached():
    svc = CouponService(_db_with_coupon(usage_limit_total=3, used_count=3))
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out == []


async def test_available_excludes_per_user_limit_reached():
    db = _db_with_coupon(usage_limit_per_user=1)
    db.table("coupon_redemptions").rows.append(
        {"id": "r1", "coupon_id": "coupon-1", "user_id": "u1"}
    )
    svc = CouponService(db)
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out == []


async def test_available_excludes_first_time_ineligible():
    db = _db_with_coupon(first_time_scope="platform")
    db.table("bookings").rows.append(
        {"id": "b1", "customer_id": "u1", "salon_id": "s9", "deleted_at": None, "status": "confirmed"}
    )
    svc = CouponService(db)
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out == []


async def test_available_summary_and_condition_fields():
    svc = CouponService(_db_with_coupon(
        discount_type="percentage", discount_value=10, max_discount_cap=100,
        min_order_amount=499, first_time_scope="platform",
    ))
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out[0]["summary"] == "10% OFF up to ₹100"
    assert out[0]["subtitle"] == "On orders above ₹499 • First booking only"


async def test_available_fee_coupon_summary():
    svc = CouponService(_db_with_coupon(
        applies_to="convenience_fee", discount_type="flat_amount", discount_value=50,
    ))
    out = await svc.list_available_coupons(customer_id="u1", salon_id="s1")
    assert out[0]["summary"] == "₹50 OFF on booking fee"


# =====================================================================
# 3. Gross coupon discount exposed for settlement (H6)
# =====================================================================
async def test_gross_discount_service_coupon():
    ps = _pricing_with(_coupon(discount_type="percentage", discount_value=20))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="SAVE",
    )
    assert r["coupon_gross_discount"] == 200


async def test_gross_discount_fee_coupon():
    ps = _pricing_with(_coupon(applies_to="convenience_fee", discount_type="percentage", discount_value=50))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 1000, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="FEE50",
    )
    assert r["coupon_gross_discount"] == 50


async def test_gross_discount_over_sale_is_full_coupon_value():
    # Sale already gives 200 off; a 30% coupon (300 gross) wins. Gross is the full
    # 300, while discount_amount is only the 100 delta over the sale.
    ps = _pricing_with(_coupon(discount_type="percentage", discount_value=30))
    r = await ps.compute_booking_pricing(
        line_items=[LineItem(1000, 800, 1)],
        convenience_fee_percentage=10,
        salon_id="s1", customer_id="u1", coupon_code="SAVE30",
    )
    assert r["coupon_gross_discount"] == 300
    assert r["discount_amount"] == 100


# =====================================================================
# 4. Schema validation (vendor fee-coupon block, past valid_until)
# =====================================================================
def test_vendor_cannot_create_convenience_fee_coupon():
    import pytest as _pytest
    from pydantic import ValidationError
    from app.schemas.request.coupon import VendorCouponCreate
    with _pytest.raises(ValidationError):
        VendorCouponCreate(
            code="NOFEE", title="No fee", applies_to="convenience_fee",
            discount_type="percentage", discount_value=100,
        )


def test_vendor_service_coupon_allowed():
    from app.schemas.request.coupon import VendorCouponCreate
    c = VendorCouponCreate(
        code="SVC10", title="10% off", applies_to="service",
        discount_type="percentage", discount_value=10,
    )
    assert c.applies_to == "service"


def test_past_valid_until_rejected():
    import pytest as _pytest
    from pydantic import ValidationError
    from app.schemas.request.coupon import AdminCouponCreate
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with _pytest.raises(ValidationError):
        AdminCouponCreate(
            code="OLD", title="Expired on arrival", applies_to="service",
            discount_type="flat_amount", discount_value=50, valid_until=past,
        )
