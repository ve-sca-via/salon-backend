"""Regular buyer (B2B) onboarding end-to-end:
RM intake (age/gender/OTP-verified phone) -> admin approves with a fee override
-> account auto-created at approval -> buyer logs in -> hidden from discovery
-> unpaid buyer blocked from ordering -> fee paid -> B2B price -> cart -> order
(stock check) -> my-orders -> [payment] -> stock decrement."""
import pytest

from .support.builders import approve, submit_request
from .support.client import detail, expect, xfail_if
from .support.tokens import razorpay_signature

FLOW = "buyer"
FLOW_TITLE = "Regular buyer (B2B) onboarding & ordering"
pytestmark = pytest.mark.e2e

APPROVAL_FEE = 1499
OVERRIDE_FEE = 999
PRICE, SALE, B2B, STOCK = 1000.0, 900.0, 700.0, 5
SHIPPING = {"full_name": None, "phone": "9000000002", "address_line1": "1 E2E Street",
            "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"}

def _shipping(world):
    return {**SHIPPING, "full_name": f"E2E Buyer {world.cfg.run_id}"}


def test_rm_submits_buyer_request(api, world, flow):
    """RM submits a regular_buyer request with intake fields (age, gender, verified phone)"""
    req = submit_request(api, world, "regular_buyer")
    assert req.get("status") == "pending"
    assert req.get("request_type") == "regular_buyer", req.get("request_type")
    assert req.get("owner_age") == 34 and req.get("owner_gender") == "female", req
    assert req.get("owner_phone_verified") is True, "intake phone verification not stamped"
    assert req.get("owner_email") in (None, ""), "buyer request should not need an email"
    flow["request"] = req


def test_admin_sees_buyer_request(api, world, flow):
    """Admin pending queue shows it as request_type=regular_buyer"""
    req = flow.need("request")
    rows = expect(api.get("/admin/vendor-requests", token=world.token("admin"),
                          params={"status_filter": "pending", "limit": 200}), 200)
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    match = [r for r in rows if r.get("id") == req["id"]]
    assert match and match[0].get("request_type") == "regular_buyer", match


def test_admin_approves_with_fee_override(api, world, flow):
    """Approve with custom_registration_fee_amount -> buyer salon + account created"""
    req = flow.need("request")
    data = approve(api, world, req["id"], custom_registration_fee_amount=APPROVAL_FEE)
    inner = data.get("data") or data
    salon_id = inner.get("salon_id")
    assert salon_id, data
    assert not inner.get("warnings"), f"approval warnings: {inner.get('warnings')}"
    salon = world.db.table("salons").select("*").eq("id", salon_id).single().execute().data
    assert salon["salon_type"] == "regular_buyer"
    assert float(salon["custom_registration_fee_amount"]) == APPROVAL_FEE
    assert salon["registration_fee_paid"] is False
    assert salon["vendor_id"], "buyer account was not created/linked at approval"
    prof = world.db.table("profiles").select("*").eq("id", salon["vendor_id"]).single().execute().data
    assert prof["user_role"] == "regular_buyer" and prof["phone_verified"] is True, prof
    assert prof["age"] == 34 and prof["gender"] == "female", "intake age/gender not carried to the profile"
    flow.update(salon=salon, buyer_id=prof["id"], buyer_email=prof["email"])


def test_buyer_logs_in(api, world, flow):
    """Buyer logs in and /auth/me says regular_buyer"""
    buyer_id, email = flow.need("buyer_id", "buyer_email")
    # Real buyers sign in with phone OTP (real SMS - off limits for automation).
    # The account was created with a random password, so set a known one with
    # the service role and use the email/password login on the same account.
    world.db.auth.admin.update_user_by_id(buyer_id, {"password": world.cfg.password})
    sess = world.login(email, world.cfg.password)
    me = expect(api.get("/auth/me", token=sess["access_token"]), 200)
    assert "regular_buyer" in str(me), me
    flow["token"] = sess["access_token"]


def test_buyer_sees_own_salon_and_fee(api, flow):
    """GET /vendors/salon shows the buyer account, unpaid, with the overridden fee"""
    token = flow.need("token")
    salon = expect(api.get("/vendors/salon", token=token), 200)
    assert salon["salon_type"] == "regular_buyer" and salon["registration_fee_paid"] is False
    assert float(salon.get("registration_fee_amount") or 0) == APPROVAL_FEE, \
        f"fee shown {salon.get('registration_fee_amount')} != override {APPROVAL_FEE}"


def test_buyer_salon_not_discoverable(api, world, flow):
    """Buyer salon is 404 on GET /salons/{id} and absent from /salons/public"""
    salon = flow.need("salon")
    resp = api.get(f"/salons/{salon['id']}")
    assert resp.status_code == 404, f"buyer salon detail -> {resp.status_code}"
    seen = set()
    for offset in range(0, 500, 100):
        page = expect(api.get("/salons/public", params={"limit": 100, "offset": offset}), 200).get("salons") or []
        seen |= {s["id"] for s in page}
        if len(page) < 100:
            break
    assert salon["id"] not in seen, "buyer salon is in the public listing"


def test_admin_updates_fee_override(api, world, flow):
    """Admin changes the fee via PUT /admin/salons/{id}; buyer sees the new amount"""
    salon, token = flow.need("salon", "token")
    expect(api.put(f"/admin/salons/{salon['id']}", token=world.token("admin"),
                   json={"custom_registration_fee_amount": OVERRIDE_FEE}), 200)
    shown = expect(api.get("/vendors/salon", token=token), 200).get("registration_fee_amount")
    assert float(shown or 0) == OVERRIDE_FEE, f"fee shown {shown} != {OVERRIDE_FEE}"
    flow["fee"] = OVERRIDE_FEE


def test_admin_creates_b2b_product(api, world, flow):
    """Admin creates a stocked product with retail, sale and B2B prices"""
    body = {"name": f"E2E Product {world.cfg.run_id} B2B", "price": PRICE, "discount_price": SALE,
            "discount_percentage": 10, "b2b_discount_price": B2B, "b2b_discount_percentage": 30,
            "stock_quantity": STOCK, "category": "hair_care", "is_active": True,
            "short_description": "E2E test product", "image_urls": [], "tags": ["e2e"]}
    data = expect(api.post("/products", token=world.token("admin"), json=body), 200, 201)
    product = data.get("product") or data
    assert product.get("id"), data
    flow["product"] = product


def test_unpaid_buyer_blocked_from_ordering(api, world, flow):
    """Unpaid buyer: POST /product-orders/create is 403 and names the fee"""
    token, product = flow.need("token", "product")
    resp = api.post("/product-orders/create", token=token,
                    json={"shipping_address": _shipping(world), "items": [{"product_id": product["id"], "quantity": 1}]})
    assert resp.status_code == 403, f"unpaid buyer -> {resp.status_code}: {resp.text[:300]}"
    msg = detail(resp)
    assert str(flow.get("fee", OVERRIDE_FEE)) in msg.replace(",", ""), f"fee amount missing from message: {msg!r}"


def test_buyer_pays_registration_fee(api, world, flow):
    """Buyer pays the registration fee (Razorpay when enabled, else service-role)"""
    token, req, salon = flow.need("token", "request", "salon")
    if world.cfg.razorpay_enabled:
        order = expect(api.post("/payments/registration/create-order", token=token,
                                params={"vendor_request_id": req["id"]}), 200)
        assert float(order["amount"]) == float(flow.get("fee", OVERRIDE_FEE)), order
        pay_id = "pay_E2EB" + world.cfg.run_id[-10:]
        sig = razorpay_signature(world.cfg.razorpay_key_secret, order["order_id"], pay_id)
        expect(api.post("/payments/registration/verify", token=token,
                        json={"razorpay_order_id": order["order_id"], "razorpay_payment_id": pay_id,
                              "razorpay_signature": sig}), 200)
    else:
        # Razorpay is blocked on staging: record the payment the way a verified
        # payment would (paid + active) so the ordering steps can continue.
        world.db.table("salons").update({"registration_fee_paid": True, "is_active": True, "is_verified": True}) \
            .eq("id", salon["id"]).execute()
        world.notes.append("buyer registration fee marked paid via service role (Razorpay disabled)")
    row = expect(api.get("/vendors/salon", token=token), 200)
    assert row["registration_fee_paid"] is True
    flow["paid"] = True


def test_buyer_salon_hidden_after_activation(api, flow):
    """Activated buyer salon stays hidden (detail, services, slots)"""
    salon = flow.need("salon")
    flow.need("paid")
    import datetime as dt
    d = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    codes = {
        "detail": api.get(f"/salons/{salon['id']}").status_code,
        "services": api.get(f"/salons/{salon['id']}/services").status_code,
        "available-slots": api.get(f"/salons/{salon['id']}/available-slots", params={"date": d}).status_code,
    }
    assert codes["detail"] == 404, codes
    assert codes["services"] == 404, codes
    assert codes["available-slots"] == 404, codes


def test_b2b_price_visible(api, world, flow):
    """Buyer sees the B2B price; anonymous sees the retail sale price"""
    token, product = flow.need("token", "product")
    mine = expect(api.get(f"/products/{product['id']}", token=token), 200)["product"]
    anon = expect(api.get(f"/products/{product['id']}"), 200)["product"]
    assert mine.get("is_b2b_price") is True and float(mine["discount_price"]) == B2B, mine
    assert anon.get("is_b2b_price") is False and float(anon["discount_price"]) == SALE, anon
    xfail_if(anon.get("b2b_discount_price") is not None,
             "BUG: (data exposure - confirm with product owner) GET /products and /products/{id} return "
             "b2b_discount_price/b2b_discount_percentage to anonymous and customer callers, so the wholesale "
             "price is visible to anyone inspecting the API (app/services/product_service.py:66 "
             "_apply_b2b_pricing only swaps the display price, it never strips the B2B fields)")


def test_buyer_product_cart(api, flow):
    """Buyer adds 2 units to the product cart at the B2B unit price"""
    token, product = flow.need("token", "product")
    expect(api.delete("/customers/product-cart/clear/all", token=token), 200)
    expect(api.post("/customers/product-cart", token=token, json={"product_id": product["id"], "quantity": 2}), 200, 201)
    cart = expect(api.get("/customers/product-cart", token=token), 200)
    assert cart["item_count"] >= 1
    assert float(cart["total_amount"]) == 2 * B2B, f"cart total {cart['total_amount']} != {2 * B2B}"


def test_order_over_stock_rejected(api, world, flow):
    """Ordering more than stock_quantity is 400"""
    token, product = flow.need("token", "product")
    flow.need("paid")
    resp = api.post("/product-orders/create", token=token,
                    json={"shipping_address": _shipping(world), "items": [{"product_id": product["id"], "quantity": STOCK + 1}]})
    assert resp.status_code == 400 and "stock" in detail(resp).lower(), f"{resp.status_code}: {resp.text[:300]}"


def test_buyer_creates_order(api, world, flow):
    """POST /product-orders/create (qty 2) is priced at the B2B price"""
    token, product = flow.need("token", "product")
    flow.need("paid")
    resp = api.post("/product-orders/create", token=token,
                    json={"shipping_address": _shipping(world), "items": [{"product_id": product["id"], "quantity": 2}]})
    data = expect(resp, 200)
    order = data["order"]
    assert float(order["subtotal"]) == 2 * B2B and float(order["total_amount"]) == 2 * B2B, order
    assert order["user_type"] == "regular_buyer"
    if not world.cfg.razorpay_enabled:
        assert data.get("dev_mode") is True, "expected simulation mode on staging (placeholder env keys)"
    flow["order"] = order
    flow["rzp_order_id"] = data["razorpay_order_id"]


def test_my_orders_and_order_by_id(api, world, flow):
    """Order shows in /product-orders/my-orders and /product-orders/{id}; other users get 404"""
    token, order = flow.need("token", "order")
    mine = expect(api.get("/product-orders/my-orders", token=token), 200)
    rows = mine if isinstance(mine, list) else (mine.get("orders") or mine.get("data") or [])
    assert order["id"] in {o.get("id") for o in rows}, "order missing from my-orders"
    one = expect(api.get(f"/product-orders/{order['id']}", token=token), 200)
    assert (one.get("order") or one).get("id") == order["id"]
    other = api.get(f"/product-orders/{order['id']}", token=world.token("customer"))
    assert other.status_code == 404, f"another user can read the order: {other.status_code}"


def test_buyer_pays_order(api, world, flow):
    """Pay the order: /product-orders/verify with a valid Razorpay signature"""
    token, order, rzp = flow.need("token", "order", "rzp_order_id")
    if not world.cfg.razorpay_enabled:
        pytest.skip("Razorpay disabled on staging (E2E_RAZORPAY_ENABLED!=1); orders run in simulation mode "
                    "and /product-orders/dev-verify is (correctly) 403 on ENVIRONMENT=production")
    pay_id = "pay_E2EO" + world.cfg.run_id[-10:]
    bad = api.post("/product-orders/verify", token=token,
                   json={"razorpay_order_id": rzp, "razorpay_payment_id": pay_id, "razorpay_signature": "0" * 64})
    assert bad.status_code == 400, f"bad signature -> {bad.status_code}"
    sig = razorpay_signature(world.cfg.razorpay_key_secret, rzp, pay_id)
    expect(api.post("/product-orders/verify", token=token,
                    json={"razorpay_order_id": rzp, "razorpay_payment_id": pay_id, "razorpay_signature": sig}), 200)
    flow["order_paid"] = True


def test_stock_decrement(api, world, flow):
    """Paid order decrements stock exactly once (5 -> 3, idempotent)"""
    order, product = flow.need("order", "product")
    if not flow.get("order_paid"):
        # Simulate what verify/webhook do after a successful payment, through
        # the same RPC, to prove the DB side (RPC exists, decrements, idempotent).
        world.db.table("product_orders").update({"status": "paid", "payment_status": "completed"}) \
            .eq("id", order["id"]).execute()
        world.db.rpc("decrement_product_stock", {"p_order_id": order["id"]}).execute()
        world.db.rpc("decrement_product_stock", {"p_order_id": order["id"]}).execute()
    stock = world.db.table("products").select("stock_quantity").eq("id", product["id"]).single().execute().data
    assert stock["stock_quantity"] == STOCK - 2, f"stock {stock['stock_quantity']} != {STOCK - 2}"
    public = expect(api.get(f"/products/{product['id']}"), 200)["product"]
    assert public["stock_quantity"] == STOCK - 2
