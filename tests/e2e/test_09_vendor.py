"""Vendor dashboard: own salon, services CRUD, coupons, bookings + status, analytics."""
import pytest

from .support.builders import future_date
from .support.client import expect

FLOW = "vendor"
FLOW_TITLE = "Vendor dashboard"
pytestmark = pytest.mark.e2e


def test_vendor_salon(api, world):
    """GET /vendors/salon returns the vendor's own active salon"""
    salon = expect(api.get("/vendors/salon", token=world.token("vendor")), 200)
    assert salon["id"] == world.fixed_salon["id"] and salon["is_active"] is True, salon


def test_vendor_updates_salon_partially(api, world):
    """PUT /vendors/salon partial update changes only the sent field"""
    token = world.token("vendor")
    before = expect(api.get("/vendors/salon", token=token), 200)
    new_desc = f"Fixed salon used by the automated E2E suite on staging. Last run {world.cfg.run_id}."
    after = expect(api.put("/vendors/salon", token=token, json={"description": new_desc}), 200)
    assert after["description"] == new_desc
    for key in ("business_name", "phone", "address", "city", "pincode", "opening_time"):
        assert after.get(key) == before.get(key), f"{key} changed by a partial update"


def test_vendor_cannot_self_verify(api, world):
    """Vendor cannot flip admin-only fields (is_verified / fee) through PUT /vendors/salon"""
    token = world.token("vendor")
    resp = api.put("/vendors/salon", token=token, json={"is_verified": False, "custom_registration_fee_amount": 0})
    row = world.db.table("salons").select("is_verified,custom_registration_fee_amount").eq("id", world.fixed_salon["id"]).single().execute().data
    # restore whatever happened so later runs stay green
    world.db.table("salons").update({"is_verified": True, "custom_registration_fee_amount": None}).eq("id", world.fixed_salon["id"]).execute()
    changed = row["is_verified"] is not True or row["custom_registration_fee_amount"] is not None
    # Fixed: admin-only fields are silently dropped (VENDOR_EDITABLE_SALON_FIELDS allowlist).
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    assert not changed, "PUT /vendors/salon wrote admin-only fields"


def test_vendor_service_categories(api, world, flow):
    """GET /vendors/service-categories returns at least one category"""
    data = expect(api.get("/vendors/service-categories", token=world.token("vendor")), 200)
    cats = data if isinstance(data, list) else (data.get("data") or data.get("categories") or [])
    assert cats, data
    flow["category_id"] = cats[0]["id"]


def test_vendor_service_crud(api, world, flow):
    """Create -> list -> public -> update -> delete a service"""
    cat = flow.need("category_id")
    token = world.token("vendor")
    name = f"E2E Service {world.cfg.run_id}"
    created = expect(api.post("/vendors/services", token=token, json={
        "name": name, "price": 300, "duration_minutes": 45, "category_id": cat, "gender_category": "both",
        "description": "E2E service"}), 200, 201)
    svc = created.get("data") or created.get("service") or created
    assert svc.get("id"), created
    listed = expect(api.get("/vendors/services", token=token), 200)
    assert svc["id"] in str(listed)
    public = expect(api.get(f"/salons/{world.fixed_salon['id']}/services"), 200)
    assert svc["id"] in str(public), "new service not public"
    upd = expect(api.put(f"/vendors/services/{svc['id']}", token=token, json={"price": 350}), 200)
    assert float((upd.get("data") or upd.get("service") or upd).get("price")) == 350
    expect(api.delete(f"/vendors/services/{svc['id']}", token=token), 200, 204)
    public = expect(api.get(f"/salons/{world.fixed_salon['id']}/services"), 200)
    assert svc["id"] not in str(public), "deleted service still public"


def test_vendor_coupon_crud(api, world):
    """Vendor coupon: create, list, deactivate, delete; convenience-fee coupons refused"""
    token = world.token("vendor")
    bad = api.post("/vendors/coupons", token=token, json={
        "code": "E2EFEE" + world.cfg.run_id[-8:], "title": f"E2E fee {world.cfg.run_id}",
        "applies_to": "convenience_fee", "discount_type": "percentage", "discount_value": 10})
    assert bad.status_code in (400, 422), f"vendor made a convenience-fee coupon: {bad.status_code}"
    code = "E2EC" + world.cfg.run_id[-12:]
    data = expect(api.post("/vendors/coupons", token=token, json={
        "code": code, "title": f"E2E vendor crud {world.cfg.run_id}", "applies_to": "service",
        "discount_type": "flat_amount", "discount_value": 25}), 200, 201)
    coupon = data.get("coupon") or data.get("data") or data
    assert code in str(expect(api.get("/vendors/coupons", token=token), 200))
    expect(api.patch(f"/vendors/coupons/{coupon['id']}", token=token, json={"is_active": False}), 200)
    expect(api.delete(f"/vendors/coupons/{coupon['id']}", token=token), 200, 204)


def test_vendor_sees_booking(api, world, flow):
    """A booking for the salon shows in GET /vendors/bookings"""
    world.require_seeded()
    svc = world.fixed_service
    row = world.db.table("bookings").insert({
        "booking_number": "E2V" + world.cfg.run_id[-12:], "customer_id": world.accounts["customer"]["id"],
        "salon_id": world.fixed_salon["id"], "booking_date": future_date(4), "time_slots": ["11:00"],
        "status": "pending",
        "services": [{"service_id": svc["id"], "service_name": svc["name"], "quantity": 1,
                      "unit_price": 500, "line_total": 500, "duration_minutes": 30}],
        "service_price": 500, "subtotal_service_price": 500, "convenience_fee": 50, "total_amount": 550,
        "notes": f"E2E vendor-flow booking {world.cfg.run_id}",
    }).execute().data[0]
    flow["booking"] = row
    data = expect(api.get("/vendors/bookings", token=world.token("vendor"), params={"limit": 200}), 200)
    assert row["id"] in {b.get("id") for b in data}, "seeded booking not visible to the vendor"


def test_vendor_updates_booking_status(api, world, flow):
    """PUT /vendors/bookings/{id}/status: confirmed -> completed; bogus status is 400"""
    booking = flow.need("booking")
    token = world.token("vendor")
    bad = api.put(f"/vendors/bookings/{booking['id']}/status", token=token, json={"status": "teleported"})
    assert bad.status_code in (400, 422), f"bogus status -> {bad.status_code}"
    expect(api.put(f"/vendors/bookings/{booking['id']}/status", token=token, json={"status": "confirmed"}), 200)
    expect(api.put(f"/vendors/bookings/{booking['id']}/status", token=token, json={"status": "completed"}), 200)
    row = world.db.table("bookings").select("status").eq("id", booking["id"]).single().execute().data
    assert row["status"] == "completed", row


def test_vendor_cannot_touch_other_salon_booking(api, world):
    """Vendor cannot change a booking of another salon"""
    world.require_seeded()
    db = world.db
    other = db.table("salons").insert({
        "business_name": f"E2E Other Salon {world.cfg.run_id}", "email": f"e2e.other+{world.cfg.run_tag}@example.com",
        "phone": "+919000000009", "address": "9 E2E Lane, Bengaluru", "city": "Bengaluru", "state": "Karnataka",
        "pincode": "560001", "salon_type": "salon", "is_active": False, "is_verified": False,
    }).execute().data[0]
    svc = world.fixed_service
    booking = db.table("bookings").insert({
        "booking_number": "E2O" + world.cfg.run_id[-12:], "customer_id": world.accounts["customer"]["id"],
        "salon_id": other["id"], "booking_date": future_date(4), "time_slots": ["11:00"], "status": "pending",
        "services": [{"service_id": svc["id"], "service_name": svc["name"], "quantity": 1, "unit_price": 500,
                      "line_total": 500, "duration_minutes": 30}],
        "service_price": 500, "convenience_fee": 50, "total_amount": 550,
        "notes": f"E2E other-salon booking {world.cfg.run_id}",
    }).execute().data[0]
    resp = api.put(f"/vendors/bookings/{booking['id']}/status", token=world.token("vendor"), json={"status": "confirmed"})
    row = db.table("bookings").select("status").eq("id", booking["id"]).single().execute().data
    assert resp.status_code in (403, 404) and row["status"] == "pending", f"got {resp.status_code}, status now {row['status']}"


def test_vendor_analytics_and_promotions(api, world):
    """GET /vendors/analytics (flag-gated: 200 or 404), /vendors/promotions(/active)"""
    token = world.token("vendor")
    resp = api.get("/vendors/analytics", token=token)
    assert resp.status_code in (200, 404), f"analytics -> {resp.status_code}: {resp.text[:200]}"
    expect(api.get("/vendors/promotions", token=token), 200)
    expect(api.get("/vendors/promotions/active", token=token), 200)


def test_vendor_registers_and_removes_push_device(api, world):
    """POST/DELETE /notifications/devices: a vendor can register a phone's push token and remove it"""
    token = world.token("vendor")
    push_token = "ExponentPushToken[E2E" + world.cfg.run_id[-12:] + "]"
    body = {"expo_push_token": push_token, "platform": "android", "app": "partner-app"}
    expect(api.post("/notifications/devices", token=token, json=body), 200)
    expect(api.post("/notifications/devices", token=token, json=body), 200)  # idempotent
    rows = world.db.table("device_tokens").select("*").eq("expo_push_token", push_token).execute().data
    assert len(rows) == 1 and rows[0]["is_active"] is True, rows
    bad = api.post("/notifications/devices", token=token, json={**body, "expo_push_token": "nope"})
    assert bad.status_code == 422, bad.status_code
    expect(api.delete("/notifications/devices", token=token, json={"expo_push_token": push_token}), 200)
    assert not world.db.table("device_tokens").select("id").eq("expo_push_token", push_token).execute().data
