"""
Regression test for `CouponService.create_coupon`'s None-stripping fix.

`CouponCreate.model_dump()` includes every optional field explicitly, so a
blank "Valid From" arrives as `{"valid_from": None, ...}` rather than the key
being absent. `valid_from` is `NOT NULL DEFAULT now()` in Postgres, and an
explicit NULL in an INSERT overrides a column default there — so the vendor
coupons page's ordinary "create with no start date" path was 500ing before
`create_coupon` started stripping `None` values first. Caught by browser-
verifying the new Next.js `/vendor/coupons` page.

Uses a tiny in-memory double instead of the full FakeSupabase in
test_vendor_mocked.py — `create_coupon` only ever touches `coupons` (and
`salons`, only for a vendor-scoped payload), so a real fake table isn't needed
to prove which keys reach `.insert()`.
"""
import asyncio

from app.services.coupon_service import CouponService


class _FakeInsertResult:
    def __init__(self, data):
        self.data = data


class _FakeCouponsTable:
    def __init__(self, captured):
        self._captured = captured

    def insert(self, data):
        self._captured["data"] = data
        return self

    def execute(self):
        row = {
            **self._captured["data"],
            "id": "coupon-1",
            "used_count": 0,
            "is_active": True,
            "created_at": "2026-09-15T00:00:00Z",
            "updated_at": "2026-09-15T00:00:00Z",
        }
        return _FakeInsertResult([row])


class _FakeDB:
    def __init__(self):
        self.captured = {}

    def table(self, name):
        assert name == "coupons", f"unexpected table {name}"
        return _FakeCouponsTable(self.captured)


def _platform_payload(**overrides):
    payload = {
        "code": "save20",
        "title": "20% off",
        "scope": "platform",
        "salon_id": None,
        "created_by": "admin-1",
        "funded_by": "platform",
        "applies_to": "service",
        "discount_type": "percentage",
        "discount_value": 20,
        "max_discount_cap": None,
        "min_order_amount": None,
        "first_time_scope": None,
        "usage_limit_total": None,
        "usage_limit_per_user": 1,
        "valid_from": None,
        "valid_until": None,
    }
    payload.update(overrides)
    return payload


def test_create_coupon_drops_none_valued_fields_before_insert():
    db = _FakeDB()
    service = CouponService(db)

    asyncio.run(service.create_coupon(_platform_payload()))

    sent = db.captured["data"]
    assert "valid_from" not in sent, "an explicit NULL valid_from would violate the NOT NULL DEFAULT now() column"
    assert "salon_id" not in sent
    assert "max_discount_cap" not in sent
    assert "min_order_amount" not in sent
    assert "first_time_scope" not in sent
    assert "usage_limit_total" not in sent
    assert "valid_until" not in sent


def test_create_coupon_keeps_real_values_and_uppercases_code():
    db = _FakeDB()
    service = CouponService(db)

    asyncio.run(service.create_coupon(_platform_payload(code="save20", valid_until="2026-12-31T00:00:00Z")))

    sent = db.captured["data"]
    assert sent["code"] == "SAVE20"
    assert sent["title"] == "20% off"
    assert sent["discount_value"] == 20
    assert sent["valid_until"] == "2026-12-31T00:00:00Z"
