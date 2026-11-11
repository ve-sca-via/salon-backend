"""
Mocked unit tests for product-order coupon support (migration
20261104000000_add_product_order_coupon_support.sql).

Mirrors tests/test_coupon_pricing.py's two-layer structure:
  1. PricingService.compute_product_order_pricing — pure math (no convenience
     fee, no salon-sale "best-of" to compete with, unlike bookings).
  2. CouponService.get_valid_product_coupon — eligibility rules against a small
     in-memory fake DB (applies_to/scope gate, window, min-order, first-time,
     usage limits).

No marker -> runs in the fast (no-stack) job.
"""
from app.services.pricing_service import PricingService, _discount
from app.services.coupon_service import CouponService


# =====================================================================
# Helpers
# =====================================================================
def _product_coupon(**overrides):
    base = {
        "id": "coupon-1",
        "code": "SAVE",
        "scope": "platform",
        "salon_id": None,
        "applies_to": "product",
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


class _StubProductCouponService:
    """Stand-in for CouponService used by PricingService pricing-math tests."""
    def __init__(self, coupon=None, reason=None):
        self._coupon = coupon
        self._reason = reason

    async def get_valid_product_coupon(self, code, customer_id, order_subtotal):
        return self._coupon, self._reason


def _pricing_with(coupon=None, reason=None):
    ps = PricingService(db_client=None)
    ps.coupon_service = _StubProductCouponService(coupon, reason)
    return ps


# =====================================================================
# 1. PricingService.compute_product_order_pricing math
# =====================================================================
async def test_no_coupon():
    ps = _pricing_with()
    r = await ps.compute_product_order_pricing(subtotal=1000, customer_id="u1", coupon_code=None)
    assert r["subtotal"] == 1000
    assert r["discount_amount"] == 0
    assert r["total_amount"] == 1000
    assert r["coupon_id"] is None
    assert r["coupon_reason"] is None


async def test_percentage_coupon_applies():
    ps = _pricing_with(_product_coupon(discount_type="percentage", discount_value=20))
    r = await ps.compute_product_order_pricing(subtotal=1000, customer_id="u1", coupon_code="SAVE")
    assert r["discount_amount"] == 200
    assert r["total_amount"] == 800
    assert r["coupon_id"] == "coupon-1"
    assert r["coupon_code"] == "SAVE"


async def test_flat_coupon_applies():
    ps = _pricing_with(_product_coupon(discount_type="flat_amount", discount_value=150))
    r = await ps.compute_product_order_pricing(subtotal=1000, customer_id="u1", coupon_code="FLAT150")
    assert r["discount_amount"] == 150
    assert r["total_amount"] == 850


async def test_percentage_coupon_capped():
    ps = _pricing_with(_product_coupon(discount_type="percentage", discount_value=50, max_discount_cap=100))
    r = await ps.compute_product_order_pricing(subtotal=1000, customer_id="u1", coupon_code="SAVE")
    assert r["discount_amount"] == 100   # 50% of 1000 would be 500, capped at 100
    assert r["total_amount"] == 900


async def test_discount_never_exceeds_subtotal():
    ps = _pricing_with(_product_coupon(discount_type="flat_amount", discount_value=5000))
    r = await ps.compute_product_order_pricing(subtotal=1000, customer_id="u1", coupon_code="SAVE")
    assert r["discount_amount"] == 1000
    assert r["total_amount"] == 0


async def test_invalid_coupon_reason_passthrough():
    ps = _pricing_with(coupon=None, reason="This coupon has expired.")
    r = await ps.compute_product_order_pricing(subtotal=1000, customer_id="u1", coupon_code="OLD")
    assert r["discount_amount"] == 0
    assert r["total_amount"] == 1000
    assert r["coupon_id"] is None
    assert r["coupon_reason"] == "This coupon has expired."


def test_discount_helper_still_shared():
    # No behavioural change to the shared helper — just confirms the product
    # path calls the same one bookings use.
    assert _discount(1000, "percentage", 50, 100) == 100


# =====================================================================
# 2. CouponService.get_valid_product_coupon eligibility
# =====================================================================
class _PResp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _PQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []
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

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def _match(self, row):
        for kind, col, val in self._filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "neq" and row.get(col) == val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        matched = [dict(r) for r in self._rows if self._match(r)]
        return _PResp(matched, count=len(matched) if self._count else None)


class _PTable:
    def __init__(self):
        self.rows = []

    def select(self, cols="*", count=None):
        return _PQuery(self.rows).select(cols, count=count)


class _PDB:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _PTable())


def _db_with_product_coupon(**overrides):
    db = _PDB()
    db.table("coupons").rows.append(_product_coupon(**overrides))
    return db


async def test_valid_product_coupon_resolves():
    svc = CouponService(_db_with_product_coupon())
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is not None and reason is None


async def test_unknown_code_not_found():
    svc = CouponService(_db_with_product_coupon())
    coupon, reason = await svc.get_valid_product_coupon("NOPE", "u1", 1000)
    assert coupon is None and "not valid" in reason


async def test_service_scoped_coupon_rejected_for_products():
    # A coupon meant for bookings (applies_to='service') must never apply to a
    # product order, even if the code matches.
    svc = CouponService(_db_with_product_coupon(applies_to="service"))
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is None
    assert "product orders" in reason


async def test_vendor_scope_coupon_rejected_for_products():
    # Products are admin-managed only — a vendor-scope coupon (even if somehow
    # flagged applies_to='product') is never usable here.
    svc = CouponService(_db_with_product_coupon(scope="vendor", salon_id="s1"))
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is None
    assert "product orders" in reason


async def test_min_order_not_met():
    svc = CouponService(_db_with_product_coupon(min_order_amount=2000))
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is None and "minimum amount" in reason


async def test_total_limit_reached():
    svc = CouponService(_db_with_product_coupon(usage_limit_total=5, used_count=5))
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is None and "usage limit" in reason


async def test_per_user_limit_reached():
    db = _db_with_product_coupon(usage_limit_per_user=1)
    db.table("coupon_redemptions").rows.append({"id": "r1", "coupon_id": "coupon-1", "user_id": "u1"})
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is None and "already used" in reason


async def test_first_time_blocks_returning_buyer():
    db = _db_with_product_coupon(first_time_scope="platform")
    db.table("product_orders").rows.append({"id": "o1", "user_id": "u1", "status": "paid"})
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is None and "first-time" in reason


async def test_first_time_ignores_cancelled_order():
    db = _db_with_product_coupon(first_time_scope="platform")
    db.table("product_orders").rows.append({"id": "o1", "user_id": "u1", "status": "cancelled"})
    svc = CouponService(db)
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is not None and reason is None


async def test_first_time_allows_new_buyer():
    svc = CouponService(_db_with_product_coupon(first_time_scope="platform"))
    coupon, reason = await svc.get_valid_product_coupon("save", "u1", 1000)
    assert coupon is not None and reason is None
