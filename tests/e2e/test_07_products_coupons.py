"""Product selling + product coupons: admin catalogue CRUD, platform product
coupon, customer discovery/validation, cart, order priced with the coupon,
stock guard, redemption limits."""
import pytest

from .support.client import detail, dig, expect, xfail_if

FLOW = "products"
FLOW_TITLE = "Products & product coupons"
pytestmark = pytest.mark.e2e

PRICE, SALE, B2B, STOCK = 800.0, 720.0, 560.0, 4
PCT = 10


def _shipping(world):
    return {"full_name": f"E2E Customer {world.cfg.run_id}", "phone": "9000000003",
            "address_line1": "2 E2E Street", "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"}


def test_admin_creates_product(api, world, flow):
    """POST /products (admin) creates an active, stocked product with a slug"""
    body = {"name": f"E2E Product {world.cfg.run_id} Retail", "price": PRICE, "discount_price": SALE,
            "discount_percentage": 10, "b2b_discount_price": B2B, "b2b_discount_percentage": 30,
            "stock_quantity": STOCK, "category": "skin_care", "brand": "E2E", "image_urls": [],
            "short_description": "E2E product", "tags": ["e2e"], "is_active": True}
    data = expect(api.post("/products", token=world.token("admin"), json=body), 200, 201)
    product = data.get("product") or data
    assert product.get("id") and product.get("slug"), product
    flow["product"] = product


def test_product_read_paths(api, world, flow):
    """GET by id, by slug, in public list (search) and in admin list"""
    product = flow.need("product")
    expect(api.get(f"/products/{product['id']}"), 200)
    by_slug = expect(api.get(f"/products/slug/{product['slug']}"), 200)
    assert (by_slug.get("product") or by_slug)["id"] == product["id"]
    listing = expect(api.get("/products", params={"search": world.cfg.run_id, "limit": 20}), 200)
    assert product["id"] in str(listing), "product missing from public search"
    admin = expect(api.get("/products/admin/all", token=world.token("admin"), params={"search": world.cfg.run_id}), 200)
    assert product["id"] in str(admin)
    expect(api.get(f"/products/{product['id']}/related", params={"limit": 4}), 200)


def test_admin_updates_product(api, world, flow):
    """PUT /products/{id} partial update keeps untouched fields"""
    product = flow.need("product")
    data = expect(api.put(f"/products/{product['id']}", token=world.token("admin"),
                          json={"short_description": "E2E product (updated)"}), 200)
    updated = data.get("product") or data
    assert updated.get("short_description") == "E2E product (updated)"
    assert float(updated["price"]) == PRICE and updated["stock_quantity"] == STOCK, "partial update clobbered fields"


def test_vendor_sees_b2b_price(api, world, flow):
    """Vendor (B2B role) sees the wholesale price on the product"""
    product = flow.need("product")
    p = expect(api.get(f"/products/{product['id']}", token=world.token("vendor")), 200)["product"]
    assert p.get("is_b2b_price") is True and float(p["discount_price"]) == B2B, p
    c = expect(api.get(f"/products/{product['id']}", token=world.token("customer")), 200)["product"]
    assert c.get("is_b2b_price") is False and float(c["discount_price"]) == SALE, c


def test_admin_creates_product_coupon(api, world, flow):
    """POST /admin/coupons: platform product coupon (10%, once per user)"""
    code = ("E2EP" + world.cfg.run_id[-12:]).upper()
    body = {"code": code, "title": f"E2E product coupon {world.cfg.run_id}", "applies_to": "product",
            "discount_type": "percentage", "discount_value": PCT, "scope": "platform", "funded_by": "platform",
            "usage_limit_per_user": 1, "usage_limit_total": 10}
    data = expect(api.post("/admin/coupons", token=world.token("admin"), json=body), 200, 201)
    coupon = data.get("coupon") or data.get("data") or data
    assert coupon.get("id"), data
    flow["coupon"] = {**coupon, "code": code}


def test_product_coupon_must_be_platform(api, world):
    """A vendor-scoped product coupon is refused (422)"""
    body = {"code": "E2EBADSCOPE", "title": f"E2E bad {world.cfg.run_id}", "applies_to": "product",
            "discount_type": "percentage", "discount_value": 5, "scope": "vendor",
            "salon_id": world.fixed_salon["id"] if world.fixed_salon else None}
    resp = api.post("/admin/coupons", token=world.token("admin"), json=body)
    assert resp.status_code in (400, 422), f"got {resp.status_code}"


def test_customer_discovers_product_coupon(api, world, flow):
    """GET /product-orders/available-coupons lists the new coupon"""
    coupon = flow.need("coupon")
    data = expect(api.get("/product-orders/available-coupons", token=world.token("customer")), 200)
    assert coupon["code"] in {c.get("code") for c in data}, f"coupon not offered: {[c.get('code') for c in data]}"


def test_customer_validates_product_coupon(api, world, flow):
    """POST /product-orders/validate-coupon computes 10% off the server-side subtotal"""
    coupon, product = flow.need("coupon", "product")
    data = expect(api.post("/product-orders/validate-coupon", token=world.token("customer"),
                           json={"code": coupon["code"].lower(), "items": [{"product_id": product["id"], "quantity": 2}]}), 200)
    assert data.get("valid") is True, data
    assert float(dig(data, "discount_amount") or 0) == round(2 * SALE * PCT / 100, 2), data
    assert float(dig(data, "total_amount") or 0) == round(2 * SALE * (100 - PCT) / 100, 2), data
    flow["expected_total"] = round(2 * SALE * (100 - PCT) / 100, 2)


def test_invalid_coupon_code(api, world, flow):
    """Unknown code validates as invalid (not an error)"""
    product = flow.need("product")
    data = expect(api.post("/product-orders/validate-coupon", token=world.token("customer"),
                           json={"code": "NOPE-DOES-NOT-EXIST", "items": [{"product_id": product["id"], "quantity": 1}]}), 200)
    assert data.get("valid") is False, data


def test_customer_product_cart(api, world, flow):
    """Customer product cart: add, update qty, read totals (sale price), remove"""
    product = flow.need("product")
    token = world.token("customer")
    expect(api.delete("/customers/product-cart/clear/all", token=token), 200)
    added = expect(api.post("/customers/product-cart", token=token, json={"product_id": product["id"], "quantity": 1}), 200, 201)
    cart = expect(api.get("/customers/product-cart", token=token), 200)
    item = next(i for i in cart["items"] if (i.get("product_id") or (i.get("product") or {}).get("id")) == product["id"])
    expect(api.put(f"/customers/product-cart/{item['id']}", token=token, json={"quantity": 2}), 200)
    cart = expect(api.get("/customers/product-cart", token=token), 200)
    assert float(cart["total_amount"]) == 2 * SALE, cart
    over = api.put(f"/customers/product-cart/{item['id']}", token=token, json={"quantity": STOCK + 5})
    assert over.status_code == 400, f"cart accepted qty above stock: {over.status_code}"
    assert added


def test_order_over_stock_rejected(api, world, flow):
    """POST /product-orders/create with qty > stock is 400"""
    product = flow.need("product")
    resp = api.post("/product-orders/create", token=world.token("customer"),
                    json={"shipping_address": _shipping(world), "items": [{"product_id": product["id"], "quantity": STOCK + 1}]})
    assert resp.status_code == 400 and "stock" in detail(resp).lower(), f"{resp.status_code}: {resp.text[:300]}"


def test_order_with_coupon(api, world, flow):
    """Order with the coupon: discount + total computed server-side"""
    product, coupon = flow.need("product", "coupon")
    resp = api.post("/product-orders/create", token=world.token("customer"),
                    json={"shipping_address": _shipping(world), "coupon_code": coupon["code"],
                          "items": [{"product_id": product["id"], "quantity": 2}]})
    data = expect(resp, 200)
    order = data["order"]
    assert order["coupon_code"] == coupon["code"] and order["coupon_id"] == coupon["id"], order
    assert float(order["subtotal"]) == 2 * SALE
    assert float(order["total_amount"]) == round(2 * SALE * (100 - PCT) / 100, 2), order
    assert float(order["discount_total"]) == round(2 * SALE * PCT / 100, 2)
    assert int(round(float(order["total_amount"]) * 100)) == data["amount_paise"], "charged amount != order total"
    flow["order"] = order


def test_tampered_price_ignored(api, world, flow):
    """Client-sent price/discount fields are ignored (server re-prices)"""
    product = flow.need("product")
    resp = api.post("/product-orders/create", token=world.token("customer"),
                    json={"shipping_address": _shipping(world), "total_amount": 1, "discount_total": 9999,
                          "items": [{"product_id": product["id"], "quantity": 1, "price": 1, "unit_price": 1}]})
    data = expect(resp, 200)
    assert float(data["order"]["total_amount"]) == SALE, data["order"]


def test_coupon_redemption_and_limit(api, world, flow):
    """Paid order redeems the coupon once; it is then no longer valid for that user"""
    order, coupon, product = flow.need("order", "coupon", "product")
    if not world.cfg.razorpay_enabled:
        # Same RPCs verify/webhook run after payment (service_role only).
        world.db.table("product_orders").update({"status": "paid", "payment_status": "completed"}).eq("id", order["id"]).execute()
        world.db.rpc("decrement_product_stock", {"p_order_id": order["id"]}).execute()
        world.db.rpc("redeem_product_coupon", {"p_coupon_id": coupon["id"], "p_user_id": order["user_id"],
                                               "p_product_order_id": order["id"],
                                               "p_discount_amount": order["discount_total"]}).execute()
        world.db.rpc("redeem_product_coupon", {"p_coupon_id": coupon["id"], "p_user_id": order["user_id"],
                                               "p_product_order_id": order["id"],
                                               "p_discount_amount": order["discount_total"]}).execute()
    else:
        pytest.skip("covered by the Razorpay-enabled order payment path (TODO: wire verify here once keys exist)")
    row = world.db.table("coupons").select("used_count").eq("id", coupon["id"]).single().execute().data
    assert row["used_count"] == 1, f"used_count={row['used_count']} (redeem not idempotent?)"
    data = expect(api.post("/product-orders/validate-coupon", token=world.token("customer"),
                           json={"code": coupon["code"], "items": [{"product_id": product["id"], "quantity": 1}]}), 200)
    assert data.get("valid") is False, f"coupon still valid after per-user limit reached: {data}"
    stock = world.db.table("products").select("stock_quantity").eq("id", product["id"]).single().execute().data
    assert stock["stock_quantity"] == STOCK - 2


def test_rpcs_locked_to_service_role(cfg):
    """decrement_product_stock / redeem_product_coupon refuse the public anon key"""
    import httpx
    if not (cfg.supabase_url and cfg.anon_key):
        pytest.skip("E2E_SUPABASE_ANON_KEY not configured")
    headers = {"apikey": cfg.anon_key, "Authorization": f"Bearer {cfg.anon_key}"}
    zero = "00000000-0000-0000-0000-000000000000"
    calls = {
        "decrement_product_stock": {"p_order_id": zero},
        "redeem_product_coupon": {"p_coupon_id": zero, "p_user_id": zero, "p_product_order_id": zero,
                                  "p_discount_amount": 0},
    }
    codes = {fn: httpx.post(f"{cfg.supabase_url}/rest/v1/rpc/{fn}", json=body, headers=headers, timeout=30).status_code
             for fn, body in calls.items()}
    assert all(c in (401, 403, 404) for c in codes.values()), f"RPC callable with the anon key: {codes}"


def test_admin_coupon_update_and_list(api, world, flow):
    """Admin lists coupons, deactivates the product coupon; it disappears from discovery"""
    coupon = flow.need("coupon")
    token = world.token("admin")
    rows = expect(api.get("/admin/coupons", token=token, params={"scope": "platform"}), 200)
    assert coupon["id"] in str(rows)
    expect(api.patch(f"/admin/coupons/{coupon['id']}", token=token, json={"is_active": False}), 200)
    data = expect(api.get("/product-orders/available-coupons", token=world.token("customer")), 200)
    assert coupon["code"] not in {c.get("code") for c in data}


def test_admin_soft_then_hard_deletes_product(api, world, flow):
    """DELETE /products/{id} hides it publicly; ?hard=true removes it"""
    product = flow.need("product")
    token = world.token("admin")
    # A product with order lines can't be hard-deleted (FK); use a fresh one.
    data = expect(api.post("/products", token=token, json={
        "name": f"E2E Product {world.cfg.run_id} Disposable", "price": 100, "stock_quantity": 1,
        "image_urls": [], "tags": []}), 200, 201)
    temp = data.get("product") or data
    expect(api.delete(f"/products/{temp['id']}", token=token), 200)
    assert api.get(f"/products/{temp['id']}").status_code == 404, "soft-deleted product still public"
    assert api.get(f"/products/{temp['id']}", token=token).status_code == 200, "admin can't see soft-deleted product"
    expect(api.delete(f"/products/{temp['id']}", token=token, params={"hard": "true"}), 200)
    assert api.get(f"/products/{temp['id']}", token=token).status_code == 404
    assert product
