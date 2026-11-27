"""Inventory ledger + order fulfilment + delivery webhook, end to end
(docs/INVENTORY_AND_DELIVERY.md):

admin product with opening stock -> restock / damaged / correction -> customer
orders (pending: no stock taken, can't be marked paid by hand) -> paid (stock
'sale') -> signed delivery webhooks drive shipped -> delivered, by order number
and by AWB, idempotently -> courier return (rto_delivered) cancels + restocks ->
admin ship / cancel with restock + refund flag -> hand delivery -> ledger sums
to the stock balance.

Needs `delivery_webhook_secret` set on the target (read back through the admin
config API to sign requests). Payment is simulated the way the payment flow
does it (paid/completed + decrement_product_stock), as in test_07.
"""
import hashlib
import hmac
import json

import pytest

from .support.client import expect, xfail_if

FLOW = "inventory"
FLOW_TITLE = "Inventory, fulfilment & delivery webhook"
pytestmark = pytest.mark.e2e

OPENING = 10
WEBHOOK = "/webhooks/delivery"


# ---------------------------------------------------------------- helpers
def _shipping(world):
    return {"full_name": f"E2E Customer {world.cfg.run_id}", "phone": "9000000004",
            "address_line1": "3 E2E Street", "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"}


def _secret(api, world, flow):
    if "secret" not in flow:
        r = api.get("/admin/config/delivery_webhook_secret", token=world.token("admin"))
        if r.status_code == 404:
            pytest.skip("delivery_webhook_secret is not configured on this target")
        flow["secret"] = expect(r, 200)["config_value"]
    return flow["secret"]


def _hook(api, world, flow, body, *, sign=True, raw=None):
    payload = raw if raw is not None else json.dumps(body, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["X-Delivery-Signature"] = hmac.new(_secret(api, world, flow).encode(), payload,
                                                   hashlib.sha256).hexdigest()
    return api.post(WEBHOOK, content=payload, headers=headers)


def _stock(api, product_id):
    return expect(api.get(f"/products/{product_id}"), 200)["product"]["stock_quantity"]


def _movements(api, world, product_id):
    return expect(api.get(f"/admin/inventory/{product_id}/movements", token=world.token("admin")), 200)["movements"]


def _order(api, world, product_id, qty):
    data = expect(api.post("/product-orders/create", token=world.token("customer"),
                           json={"shipping_address": _shipping(world),
                                 "items": [{"product_id": product_id, "quantity": qty}]}), 200)
    return data["order"]


def _pay(world, order):
    """What verify / payment.captured do: guarded flip to paid, then the stock RPC."""
    upd = world.db.table("product_orders").update({"status": "paid", "payment_status": "completed"}) \
        .eq("id", order["id"]).eq("payment_status", "pending").execute()
    if upd.data:
        world.db.rpc("decrement_product_stock", {"p_order_id": order["id"]}).execute()
    return bool(upd.data)


def _status(api, world, order_id, **body):
    return api.patch(f"/admin/product-orders/{order_id}/status", token=world.token("admin"), json=body)


def _row(world, order_id):
    return world.db.table("product_orders").select("*").eq("id", order_id).single().execute().data


def _events(api, world, order_id):
    return expect(api.get(f"/admin/product-orders/{order_id}/events", token=world.token("admin")), 200)["events"]


# ---------------------------------------------------------------- webhook auth
def test_webhook_rejects_unsigned_and_forged(api, world, flow):
    """Unsigned, wrongly signed and non-JSON bodies are 400 (never redelivered)"""
    _secret(api, world, flow)  # skips cleanly if the target has no secret
    body = {"order_number": "ORD-NOPE", "event": "delivered"}
    assert _hook(api, world, flow, body, sign=False).status_code == 400
    forged = api.post(WEBHOOK, content=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json", "X-Delivery-Signature": "0" * 64})
    assert forged.status_code == 400 and forged.json()["status"] == "invalid_signature"
    bad = _hook(api, world, flow, None, raw=b"not json")
    assert bad.status_code == 400 and bad.json()["status"] == "invalid_body", bad.text


def test_webhook_unknown_order_and_event_are_acknowledged(api, world, flow):
    """Unknown order -> 200 order_not_found (don't redeliver forever)"""
    r = expect(_hook(api, world, flow, {"order_number": f"ORD-{world.cfg.run_id}-NONE", "event": "delivered"}), 200)
    assert r["action"] == "order_not_found", r


# ---------------------------------------------------------------- stock ledger
def test_product_opening_stock_is_ledgered(api, world, flow):
    """POST /products with opening stock writes one 'initial' movement"""
    body = {"name": f"E2E Product {world.cfg.run_id} Stock", "price": 500.0, "stock_quantity": OPENING,
            "category": "skin_care", "brand": "E2E", "image_urls": [], "short_description": "E2E stock",
            "tags": ["e2e"], "is_active": True}
    data = expect(api.post("/products", token=world.token("admin"), json=body), 200, 201)
    product = data.get("product") or data
    flow["product"] = product
    moves = _movements(api, world, product["id"])
    assert [(m["reason"], m["change"], m["balance_after"]) for m in moves] == [("initial", OPENING, OPENING)], moves


def test_admin_stock_adjustments(api, world, flow):
    """restock +5, damaged -2, correction -1 -> 12; wrong-sign and below-zero refused"""
    pid = flow.need("product")["id"]
    admin = world.token("admin")
    adj = lambda change, reason: api.post(f"/admin/inventory/{pid}/adjust", token=admin,
                                          json={"change": change, "reason": reason, "note": "e2e"})
    assert expect(adj(5, "restock"), 200)["stock_quantity"] == OPENING + 5
    assert expect(adj(-2, "damaged"), 200)["stock_quantity"] == OPENING + 3
    assert expect(adj(-1, "adjustment"), 200)["stock_quantity"] == OPENING + 2
    assert adj(-3, "restock").status_code == 422
    assert adj(4, "damaged").status_code == 422
    assert adj(0, "adjustment").status_code == 422
    below = adj(-1000, "adjustment")
    assert below.status_code == 400, f"went below zero? {below.status_code} {below.text[:200]}"
    assert _stock(api, pid) == OPENING + 2
    flow["stock"] = OPENING + 2


def test_stock_endpoints_are_admin_only(api, world, flow):
    """Customer can't adjust stock or read the ledger"""
    pid = flow.need("product")["id"]
    tok = world.token("customer")
    assert api.post(f"/admin/inventory/{pid}/adjust", token=tok,
                    json={"change": 100, "reason": "restock"}).status_code == 403
    assert api.get(f"/admin/inventory/{pid}/movements", token=tok).status_code == 403


def test_product_form_stock_edit_is_ledgered(api, world, flow):
    """PUT /products/{id} stock_quantity goes through set_product_stock (an 'adjustment')"""
    pid = flow.need("product")["id"]
    target = flow["stock"] + 3
    expect(api.put(f"/products/{pid}", token=world.token("admin"), json={"stock_quantity": target}), 200)
    newest = _movements(api, world, pid)[0]
    assert (newest["reason"], newest["change"], newest["balance_after"]) == ("adjustment", 3, target), newest
    expect(api.put(f"/products/{pid}", token=world.token("admin"), json={"stock_quantity": flow["stock"]}), 200)
    assert _stock(api, pid) == flow["stock"]


# ---------------------------------------------------------------- order A: courier happy path
def test_pending_order_takes_no_stock_and_cannot_be_paid_by_hand(api, world, flow):
    """A pending order leaves stock alone; admin can't set 'paid'; a courier scan doesn't ship it"""
    pid = flow.need("product")["id"]
    order = _order(api, world, pid, 2)
    assert order["status"] == "pending"
    flow["order_a"] = order
    assert _stock(api, pid) == flow["stock"]
    r = _status(api, world, order["id"], status="paid")
    assert r.status_code == 400, f"admin marked an order paid by hand: {r.status_code} {r.text[:200]}"
    early = expect(_hook(api, world, flow, {"order_number": order["order_number"], "event": "picked_up"}), 200)
    assert early["action"] == "logged" and _row(world, order["id"])["status"] == "pending", early


def test_payment_takes_stock_once(api, world, flow):
    """Paid -> one 'sale' movement of -2; a repeated payment signal changes nothing"""
    order, pid = flow.need("order_a")["id"], flow["product"]["id"]
    assert _pay(world, flow["order_a"]) is True
    assert _pay(world, flow["order_a"]) is False
    world.db.rpc("decrement_product_stock", {"p_order_id": order}).execute()  # idempotent RPC
    flow["stock"] -= 2
    assert _stock(api, pid) == flow["stock"]
    sales = [m for m in _movements(api, world, pid) if m["reason"] == "sale"]
    assert [(m["change"], m["order_id"]) for m in sales] == [(-2, order)], sales


def test_webhook_ships_then_delivers(api, world, flow):
    """manifested (AWB stored) -> picked_up = shipped -> repeat is a no-op -> delivered by AWB"""
    o = flow.need("order_a")
    awb = f"AWB{world.cfg.run_tag}A".upper().replace("-", "")
    m = expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "manifested",
                                         "tracking_number": awb, "courier_name": "E2E Courier",
                                         "tracking_url": f"https://track.example.com/{awb}"}), 200)
    assert m["action"] == "logged", m
    row = _row(world, o["id"])
    assert row["status"] == "paid" and row["tracking_number"] == awb and row["courier_name"] == "E2E Courier", row

    s = expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "picked_up"}), 200)
    assert s["action"] == "status_updated" and s["to"] == "shipped", s
    row = _row(world, o["id"])
    assert row["status"] == "shipped" and row["shipped_at"], row

    again = expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "in_transit"}), 200)
    assert again["action"] == "logged" and _row(world, o["id"])["status"] == "shipped", again

    d = expect(_hook(api, world, flow, {"tracking_number": awb, "event": "delivered",
                                         "occurred_at": "2026-11-27T10:00:00Z"}), 200)
    assert d["action"] == "status_updated" and d["to"] == "delivered", d
    row = _row(world, o["id"])
    assert row["status"] == "delivered" and row["delivered_at"], row
    flow["awb_a"] = awb


def test_delivered_is_final(api, world, flow):
    """Delivered orders ignore a late return scan and can't be cancelled; stock untouched"""
    o = flow.need("order_a")
    late = expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "rto_delivered"}), 200)
    assert late["action"] == "logged" and _row(world, o["id"])["status"] == "delivered", late
    assert _status(api, world, o["id"], status="cancelled").status_code == 400
    assert _stock(api, flow["product"]["id"]) == flow["stock"]


def test_order_timeline(api, world, flow):
    """Timeline holds every courier update with its raw payload, oldest first"""
    o = flow.need("order_a")
    events = _events(api, world, o["id"])
    hooks = [e for e in events if e["source"] == "delivery_webhook"]
    assert [e["event"] for e in hooks] == ["picked_up", "manifested", "picked_up", "in_transit",
                                           "delivered", "rto_delivered"], [e["event"] for e in hooks]
    moved = [(e["from_status"], e["to_status"]) for e in hooks if e["to_status"]]
    assert moved == [("paid", "shipped"), ("shipped", "delivered")], moved
    assert all(isinstance(e["payload"], dict) and e["payload"].get("event") == e["event"] for e in hooks)


def test_customer_sees_tracking(api, world, flow):
    """Customer's order view returns status + courier/tracking fields"""
    o = flow.need("order_a")
    data = expect(api.get(f"/product-orders/{o['id']}", token=world.token("customer")), 200)
    order = data.get("order") or data
    assert order["status"] == "delivered" and order["tracking_number"] == flow["awb_a"], order
    assert order.get("tracking_url") and order.get("courier_name"), order


# ---------------------------------------------------------------- order B: courier return
def test_courier_return_cancels_and_restocks(api, world, flow):
    """paid -> picked_up -> rto_delivered = cancelled + 3 units back ('order_cancelled')"""
    pid = flow.need("product")["id"]
    o = _order(api, world, pid, 3)
    _pay(world, o)
    flow["stock"] -= 3
    assert _stock(api, pid) == flow["stock"]
    expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "picked_up",
                                     "tracking_number": f"AWB{world.cfg.run_tag}B".upper().replace("-", "")}), 200)
    r = expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "rto_delivered"}), 200)
    assert r["action"] == "status_updated" and r["to"] == "cancelled", r
    row = _row(world, o["id"])
    assert row["status"] == "cancelled" and row["cancelled_at"] and row["stock_restored"], row
    flow["stock"] += 3
    assert _stock(api, pid) == flow["stock"]
    back = [m for m in _movements(api, world, pid) if m["reason"] == "order_cancelled"]
    assert [(m["change"], m["order_id"]) for m in back] == [(3, o["id"])], back
    again = expect(_hook(api, world, flow, {"order_number": o["order_number"], "event": "rto_delivered"}), 200)
    assert again["action"] == "logged" and _stock(api, pid) == flow["stock"], "double restock"


# ---------------------------------------------------------------- order C: admin ship + cancel
def test_admin_ships_with_tracking_and_edits_shipment(api, world, flow):
    """Admin paid -> shipped with tracking; shipment PATCH: blank untouched, null clears"""
    pid = flow.need("product")["id"]
    o = _order(api, world, pid, 1)
    _pay(world, o)
    flow["stock"] -= 1
    flow["order_c"] = o
    r = expect(_status(api, world, o["id"], status="shipped", courier_name="Hand Courier",
                       tracking_number="MANUAL-1", tracking_url="https://t.example.com/1", note="e2e"), 200)
    assert r["changed"] and r["order"]["status"] == "shipped", r
    expect(api.patch(f"/admin/product-orders/{o['id']}/shipment", token=world.token("admin"),
                     json={"tracking_number": "MANUAL-2", "courier_name": ""}), 200)
    row = _row(world, o["id"])
    assert row["tracking_number"] == "MANUAL-2" and row["courier_name"] == "Hand Courier", row
    expect(api.patch(f"/admin/product-orders/{o['id']}/shipment", token=world.token("admin"),
                     json={"tracking_url": None}), 200)
    assert _row(world, o["id"])["tracking_url"] is None
    assert _status(api, world, o["id"], status="pending").status_code == 400, "moved backwards"


def test_admin_cancel_restocks_and_flags_refund(api, world, flow):
    """Cancelling a paid order returns stock and says a refund is needed; repeating is a no-op"""
    o, pid = flow.need("order_c"), flow["product"]["id"]
    r = expect(_status(api, world, o["id"], status="cancelled", note="customer asked"), 200)
    assert r["changed"] and r["refund_required"] is True and r["stock_restored"] is True, r
    flow["stock"] += 1
    assert _stock(api, pid) == flow["stock"]
    again = expect(_status(api, world, o["id"], status="cancelled"), 200)
    assert again["changed"] is False and _stock(api, pid) == flow["stock"], again


# ---------------------------------------------------------------- orders D, E
def test_cancel_unpaid_order_takes_nothing_back(api, world, flow):
    """Cancelling a pending order: no restock, no refund"""
    pid = flow.need("product")["id"]
    o = _order(api, world, pid, 4)
    r = expect(_status(api, world, o["id"], status="cancelled"), 200)
    assert r["refund_required"] is False and not r.get("stock_restored"), r
    assert _stock(api, pid) == flow["stock"]
    # Known bug (found 2026-11-27): cancelling leaves payment_status='pending', and
    # the payment paths guard only on that, so a late payment revives the order
    # and takes stock. Keep the ledger expectation in step, then report it.
    revived = _pay(world, o)
    if revived:
        flow["stock"] -= 4
    xfail_if(revived, "BUG: a cancelled (unpaid) order can still be marked paid and take stock")


def test_hand_delivery(api, world, flow):
    """paid -> delivered directly (no courier)"""
    pid = flow.need("product")["id"]
    o = _order(api, world, pid, 1)
    _pay(world, o)
    flow["stock"] -= 1
    r = expect(_status(api, world, o["id"], status="delivered"), 200)
    assert r["order"]["status"] == "delivered", r


def test_ledger_sums_to_stock(api, world, flow):
    """Sum of every movement == stock_quantity; balances chain correctly"""
    pid = flow.need("product")["id"]
    moves = list(reversed(_movements(api, world, pid)))  # oldest first
    running = 0
    for m in moves:
        running += m["change"]
        assert m["balance_after"] == running, f"broken chain at {m}"
    assert running == _stock(api, pid) == flow["stock"], (running, flow["stock"])
    world.notes.append(f"inventory: {len(moves)} ledger rows, final stock {running}")
