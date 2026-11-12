"""Role boundaries: every role is kept out of the others' endpoints."""
import pytest

FLOW = "boundaries"
FLOW_TITLE = "Role boundaries"
pytestmark = pytest.mark.e2e

ZERO = "00000000-0000-0000-0000-000000000000"

ADMIN_ONLY = [
    ("GET", "/admin/stats"),
    ("GET", "/admin/vendor-requests"),
    ("GET", "/admin/users/"),
    ("GET", "/admin/config"),
    ("GET", "/admin/coupons"),
    ("GET", "/admin/product-orders/"),
    ("GET", "/products/admin/all"),
    ("GET", "/banners/admin/all"),
    ("GET", "/partners/requests"),
    ("GET", "/careers/applications"),
]
RM_ONLY = [("GET", "/rm/dashboard"), ("GET", "/rm/vendor-requests"), ("GET", "/rm/salons")]
VENDOR_ONLY = [("GET", "/vendors/salon"), ("GET", "/vendors/services"), ("GET", "/vendors/bookings"),
               ("GET", "/vendors/coupons"), ("GET", "/vendors/service-categories")]


def _status(api, token, method, path, **kw):
    return api.request(method, path, token=token, **kw).status_code


@pytest.mark.parametrize("method,path", ADMIN_ONLY + RM_ONLY + VENDOR_ONLY)
def test_unauthenticated_is_401(api, method, path):
    """Unauthenticated call to a protected endpoint is 401"""
    code = _status(api, None, method, path)
    assert code in (401, 403), f"{method} {path} without token -> {code}"
    if code == 403:
        pytest.xfail("BUG: protected endpoint answers 403 instead of 401 when no token is sent")


def test_customer_blocked_from_admin_rm_vendor(api, world):
    """Customer gets 403 on admin, RM and vendor endpoints"""
    token = world.token("customer")
    bad = [(m, p, c) for m, p in ADMIN_ONLY + RM_ONLY + VENDOR_ONLY
           if (c := _status(api, token, m, p)) != 403]
    assert not bad, f"customer not blocked (expected 403): {bad}"


def test_vendor_blocked_from_admin_and_rm(api, world):
    """Vendor gets 403 on admin and RM endpoints"""
    token = world.token("vendor")
    bad = [(m, p, c) for m, p in ADMIN_ONLY + RM_ONLY if (c := _status(api, token, m, p)) != 403]
    assert not bad, f"vendor not blocked (expected 403): {bad}"


def test_rm_blocked_from_admin_and_vendor(api, world):
    """RM gets 403 on admin and vendor endpoints"""
    token = world.token("rm")
    bad = [(m, p, c) for m, p in ADMIN_ONLY + VENDOR_ONLY if (c := _status(api, token, m, p)) != 403]
    assert not bad, f"RM not blocked (expected 403): {bad}"


def test_rm_cannot_approve(api, world):
    """RM cannot approve or reject vendor requests (403)"""
    token = world.token("rm")
    a = _status(api, token, "POST", f"/admin/vendor-requests/{ZERO}/approve", json={})
    r = _status(api, token, "POST", f"/admin/vendor-requests/{ZERO}/reject", json={"admin_notes": "x"})
    assert (a, r) == (403, 403), f"approve={a} reject={r}"


def test_non_admin_cannot_write_catalog(api, world):
    """Vendor/customer cannot create products, coupons, banners, config"""
    results = {}
    for role in ("vendor", "customer"):
        token = world.token(role)
        results[role] = {
            "product": _status(api, token, "POST", "/products", json={"name": "x", "price": 1}),
            "admin_coupon": _status(api, token, "POST", "/admin/coupons", json={}),
            "banner": _status(api, token, "POST", "/banners", json={}),
            "config": _status(api, token, "PUT", "/admin/config/convenience_fee_percentage", json={"config_value": "0"}),
            "feature_flag": _status(api, token, "PATCH", "/features/admin/blog", json={"status": "disabled"}),
        }
    bad = {r: {k: v for k, v in d.items() if v not in (403, 404)} for r, d in results.items()}
    bad = {r: d for r, d in bad.items() if d}
    assert not bad, f"write not blocked: {bad}"


def test_customer_cannot_create_vendor_coupon(api, world):
    """Customer cannot create a vendor coupon"""
    code = _status(api, world.token("customer"), "POST", "/vendors/coupons",
                   json={"code": "NOPE123", "title": "nope", "applies_to": "service",
                         "discount_type": "percentage", "discount_value": 10})
    assert code == 403, f"got {code}"


def test_customer_cannot_read_other_order(api, world):
    """GET /product-orders/{random id} is 404 for a customer (owner-scoped)"""
    code = _status(api, world.token("customer"), "GET", f"/product-orders/{ZERO}")
    assert code == 404, f"got {code}"


def test_customer_cannot_update_others_booking_status(api, world):
    """Customer cannot use the vendor booking-status endpoint"""
    code = _status(api, world.token("customer"), "PUT", f"/vendors/bookings/{ZERO}/status", json={"status": "confirmed"})
    assert code == 403, f"got {code}"


def test_dev_verify_blocked_on_deployed_env(api, world):
    """POST /product-orders/dev-verify/{id} is unavailable on staging (403)"""
    code = _status(api, world.token("customer"), "POST", f"/product-orders/dev-verify/{ZERO}")
    assert code == 403, f"dev-only payment bypass reachable: {code}"
