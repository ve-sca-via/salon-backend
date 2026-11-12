"""Customer booking: browse salon -> offers -> cart -> coupon preview -> pay
convenience fee (Razorpay) -> booking -> my-bookings -> cancel."""
import pytest

from .support.builders import future_date
from .support.client import dig, expect
from .support.tokens import razorpay_signature

FLOW = "booking"
FLOW_TITLE = "Customer booking"
pytestmark = pytest.mark.e2e

SERVICE_PRICE = 500.0
PCT = 10


def test_customer_browses_salon(api, world, flow):
    """Customer opens the salon, its services and tomorrow+3 slots"""
    world.require_seeded()
    sid, svc = world.fixed_salon["id"], world.fixed_service["id"]
    token = world.token("customer")
    expect(api.get(f"/salons/{sid}", token=token, params={"include_services": "true"}), 200)
    date = future_date(3)
    slots = expect(api.get(f"/salons/{sid}/available-slots", params={"date": date, "service_ids": svc}), 200)
    assert slots["available_slots"], slots
    flow.update(date=date, slot=slots["available_slots"][len(slots["available_slots"]) // 2])


def test_vendor_creates_service_coupon(api, world, flow):
    """Vendor creates a 10% service coupon for their salon"""
    code = ("E2EV" + world.cfg.run_id[-12:]).upper()
    body = {"code": code, "title": f"E2E vendor coupon {world.cfg.run_id}", "applies_to": "service",
            "discount_type": "percentage", "discount_value": PCT, "usage_limit_per_user": 5}
    data = expect(api.post("/vendors/coupons", token=world.token("vendor"), json=body), 200, 201)
    coupon = data.get("coupon") or data.get("data") or data
    assert coupon.get("id"), data
    flow["coupon"] = {**coupon, "code": code}


def test_available_coupons(api, world, flow):
    """GET /customers/available-coupons?salon_id= includes the vendor coupon"""
    coupon = flow.need("coupon")
    data = expect(api.get("/customers/available-coupons", token=world.token("customer"),
                          params={"salon_id": world.fixed_salon["id"]}), 200)
    codes = {c.get("code") for c in data}
    assert coupon["code"] in codes, f"vendor coupon not offered: {codes}"
    other = expect(api.get("/customers/available-coupons", token=world.token("customer")), 200)
    assert coupon["code"] not in {c.get("code") for c in other}, "salon coupon leaked into platform-only list"


def test_salon_detail_shows_offer(api, world, flow):
    """Public salon detail embeds the coupon / max discount"""
    coupon = flow.need("coupon")
    data = expect(api.get(f"/salons/{world.fixed_salon['id']}"), 200)
    assert coupon["code"] in str(data), "coupon not embedded in salon detail response"


def test_cart_add_service(api, world, flow):
    """Customer clears the cart and adds the fixed service"""
    world.require_seeded()
    token = world.token("customer")
    expect(api.delete("/customers/cart/clear/all", token=token), 200)
    expect(api.post("/customers/cart", token=token,
                    json={"service_id": world.fixed_service["id"], "salon_id": world.fixed_salon["id"], "quantity": 1}), 200, 201)
    cart = expect(api.get("/customers/cart", token=token), 200)
    assert cart["item_count"] == 1 and float(cart["total_amount"]) == SERVICE_PRICE, cart
    flow["cart_ready"] = True


def test_coupon_preview_pricing(api, world, flow):
    """POST /customers/cart/validate-coupon: 10% off service, fee from config, totals add up"""
    coupon = flow.need("coupon")
    flow.need("cart_ready")
    data = expect(api.post("/customers/cart/validate-coupon", token=world.token("customer"),
                           json={"code": coupon["code"]}), 200)
    assert data.get("valid") is True, data
    discount = float(dig(data, "discount_amount") or 0)
    assert discount == SERVICE_PRICE * PCT / 100, data
    pct_row = world.db.table("system_config").select("config_value").eq("config_key", "convenience_fee_percentage").single().execute().data
    pct = float(pct_row["config_value"])
    fee = dig(data, "convenience_fee_due")
    total = dig(data, "total_amount")
    due = dig(data, "service_total_due")
    assert due is not None and float(due) == SERVICE_PRICE - discount, data
    if fee is not None and total is not None:
        assert abs(float(total) - (float(due) + float(fee))) < 0.011, f"total != service + fee: {data}"
        # fee is a % of the service amount (+GST in some configs) - sanity bound
        assert 0 <= float(fee) <= SERVICE_PRICE * (pct / 100) * 1.2 + 1, f"fee {fee} vs {pct}%"
    flow["preview"] = data


def test_pay_convenience_fee(api, world, flow):
    """POST /payments/cart/create-order -> Razorpay order for the convenience fee"""
    coupon = flow.need("coupon")
    flow.need("cart_ready")
    resp = api.post("/payments/cart/create-order", token=world.token("customer"),
                    json={"coupon_code": coupon["code"], "booking_date": flow.get("date"), "time_slots": [flow.get("slot")]})
    if not world.cfg.razorpay_enabled:
        assert resp.status_code in (500, 503), f"create-order without keys -> {resp.status_code}"
        pytest.skip(f"Razorpay disabled on staging -> create-order {resp.status_code} (expected); "
                    "set E2E_RAZORPAY_ENABLED=1 once TEST keys are in system_config")
    order = expect(resp, 200)
    preview = flow.get("preview") or {}
    fee = dig(preview, "convenience_fee_due")
    if fee is not None:
        assert abs(float(order["amount"]) - float(fee)) < 0.011, f"charged {order['amount']} != fee due {fee}"
    flow["rzp_order"] = order


def test_checkout_with_payment(api, world, flow):
    """POST /customers/cart/checkout with a valid signature creates a confirmed booking"""
    order = flow.need("rzp_order")
    pay_id = "pay_E2EC" + world.cfg.run_id[-10:]
    sig = razorpay_signature(world.cfg.razorpay_key_secret, order["order_id"], pay_id)
    data = expect(api.post("/customers/cart/checkout", token=world.token("customer"), json={
        "booking_date": flow["date"], "time_slots": [flow["slot"]], "razorpay_order_id": order["order_id"],
        "razorpay_payment_id": pay_id, "razorpay_signature": sig, "payment_method": "razorpay",
        "notes": f"E2E booking {world.cfg.run_id}", "coupon_code": flow["coupon"]["code"]}), 200)
    assert data["status"] == "confirmed", data["status"]
    assert abs(float(data["total_amount"]) - (float(data["service_price"]) + float(data["convenience_fee"]))) < 0.011
    assert data.get("coupon_code") == flow["coupon"]["code"]
    flow["booking"] = data


def test_checkout_without_payment_rejected(api, world, flow):
    """Checkout with NO payment details is refused (convenience fee must be paid)"""
    world.require_seeded()
    token = world.token("customer")
    cart = expect(api.get("/customers/cart", token=token), 200)
    if not cart.get("item_count"):
        expect(api.post("/customers/cart", token=token, json={"service_id": world.fixed_service["id"],
                                                             "salon_id": world.fixed_salon["id"], "quantity": 1}), 200, 201)
    date = flow.get("date") or future_date(3)
    slot = flow.get("slot") or "11:00"
    resp = api.post("/customers/cart/checkout", token=token, json={
        "booking_date": date, "time_slots": [slot], "notes": f"E2E unpaid booking {world.cfg.run_id}"})
    if resp.status_code == 200:
        flow.setdefault("booking", resp.json())
        flow["unpaid_booking"] = resp.json()
    # Fixed: checkout_cart requires order id + payment id + signature (400 otherwise).
    assert resp.status_code in (400, 402, 422), f"got {resp.status_code}: {resp.text[:300]}"


def test_booking_fallback_seed(api, world, flow):
    """Booking exists for the remaining steps (service-role seed if API paths unavailable)"""
    if flow.get("booking"):
        return
    world.require_seeded()
    svc = world.fixed_service
    row = world.db.table("bookings").insert({
        "booking_number": "E2E" + world.cfg.run_id[-12:], "customer_id": world.accounts["customer"]["id"],
        "salon_id": world.fixed_salon["id"], "booking_date": flow.get("date") or future_date(3),
        "time_slots": [flow.get("slot") or "11:00"], "status": "confirmed",
        "services": [{"service_id": svc["id"], "service_name": svc["name"], "quantity": 1,
                      "unit_price": SERVICE_PRICE, "line_total": SERVICE_PRICE, "duration_minutes": 30}],
        "service_price": SERVICE_PRICE, "subtotal_service_price": SERVICE_PRICE, "convenience_fee": 50,
        "total_amount": SERVICE_PRICE + 50, "notes": f"E2E seeded booking {world.cfg.run_id}",
    }).execute().data[0]
    flow["booking"] = row
    world.notes.append("booking flow: booking seeded via service role (no API path produced one)")


def test_my_bookings(api, world, flow):
    """GET /customers/bookings/my-bookings lists it with consistent pricing"""
    booking = flow.need("booking")
    data = expect(api.get("/customers/bookings/my-bookings", token=world.token("customer")), 200)
    rows = {b["id"]: b for b in data.get("data") or []}
    assert booking["id"] in rows, "booking missing from my-bookings"
    b = rows[booking["id"]]
    assert abs(float(b["total_amount"]) - (float(b["service_price"]) + float(b["convenience_fee"]))) < 0.011, b


def test_other_customer_cannot_cancel(api, world, flow):
    """A different user cannot cancel this booking"""
    booking = flow.need("booking")
    resp = api.put(f"/customers/bookings/{booking['id']}/cancel", token=world.token("vendor"))
    assert resp.status_code in (403, 404), f"got {resp.status_code}"


def test_customer_cancels(api, world, flow):
    """PUT /customers/bookings/{id}/cancel -> cancelled; second cancel is 400"""
    booking = flow.need("booking")
    token = world.token("customer")
    expect(api.put(f"/customers/bookings/{booking['id']}/cancel", token=token), 200)
    row = world.db.table("bookings").select("status").eq("id", booking["id"]).single().execute().data
    assert row["status"] == "cancelled", row
    again = api.put(f"/customers/bookings/{booking['id']}/cancel", token=token)
    assert again.status_code == 400, f"second cancel -> {again.status_code}"


def test_cleanup_vendor_coupon(api, world, flow):
    """Vendor deletes the coupon (DELETE /vendors/coupons/{id})"""
    coupon = flow.need("coupon")
    resp = api.delete(f"/vendors/coupons/{coupon['id']}", token=world.token("vendor"))
    assert resp.status_code in (200, 204, 409), resp.text[:200]  # 409 = has redemptions; deactivated instead
