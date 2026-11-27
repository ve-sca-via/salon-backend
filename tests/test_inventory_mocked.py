"""
Mocked tests for inventory + delivery (migration 20261127000000):

    * admin stock adjustments and the ledger (app/api/admin/inventory.py)
    * product create/edit routing stock through the ledger
    * order status transitions, restock on cancel, shipment fields, timeline
    * the partner-neutral delivery webhook (POST /webhooks/delivery)

Reuses the in-memory FakeSupabase from test_product_order_mocked, whose RPC fake
mirrors the migration's functions. No marker -> fast job.
"""
import hashlib
import hmac
import json
import uuid

import pytest

from app.core.config import settings
from app.services.delivery_webhook_service import DeliveryWebhookService
from tests.test_product_order_mocked import od, ADMIN_ORDERS  # noqa: F401  (fixture)

API = settings.API_PREFIX
INVENTORY = f"{API}/admin/inventory"
PRODUCTS = f"{API}/products"
DELIVERY_HOOK = f"{API}/webhooks/delivery"
SECRET = "test-delivery-secret"


def _movements(od, product_id=None):
    rows = od.db.table("product_stock_movements").rows
    return [m for m in rows if product_id is None or m["product_id"] == product_id]


def _paid_order(od, product, qty=2, **fields):
    """A paid order whose stock has already been decremented (as the payment flow does)."""
    order = od.seed_order("u1", status="paid", payment_status="completed",
                          stock_decremented=True, **fields)
    od.seed_order_item(order["id"], product_id=product["id"], quantity=qty)
    product["stock_quantity"] -= qty
    return order


# =====================================================================
# Stock adjustments
# =====================================================================
def test_restock_adds_units_and_writes_ledger(od):
    p = od.seed_product(stock_quantity=5)
    od.login_admin()

    r = od.client.post(f"{INVENTORY}/{p['id']}/adjust",
                       json={"change": 20, "reason": "restock", "note": "Invoice 42"})
    assert r.status_code == 200, r.text
    assert r.json()["stock_quantity"] == 25
    assert p["stock_quantity"] == 25
    [m] = _movements(od, p["id"])
    assert (m["change"], m["balance_after"], m["reason"], m["note"], m["created_by"]) == \
        (20, 25, "restock", "Invoice 42", "admin-1")


def test_damaged_removes_units(od):
    p = od.seed_product(stock_quantity=5)
    od.login_admin()
    r = od.client.post(f"{INVENTORY}/{p['id']}/adjust", json={"change": -2, "reason": "damaged"})
    assert r.status_code == 200, r.text
    assert p["stock_quantity"] == 3


def test_adjust_cannot_go_below_zero(od):
    p = od.seed_product(stock_quantity=1)
    od.login_admin()
    r = od.client.post(f"{INVENTORY}/{p['id']}/adjust", json={"change": -5, "reason": "adjustment"})
    assert r.status_code == 400, r.text
    assert p["stock_quantity"] == 1
    assert _movements(od) == []


@pytest.mark.parametrize("body", [
    {"change": -3, "reason": "restock"},
    {"change": 3, "reason": "damaged"},
    {"change": 0, "reason": "adjustment"},
    {"change": 3, "reason": "sale"},          # system-only reason
])
def test_adjust_rejects_inconsistent_requests(od, body):
    p = od.seed_product(stock_quantity=5)
    od.login_admin()
    r = od.client.post(f"{INVENTORY}/{p['id']}/adjust", json=body)
    assert r.status_code == 422, r.text


def test_adjust_unknown_product_is_404(od):
    od.login_admin()
    r = od.client.post(f"{INVENTORY}/{uuid.uuid4()}/adjust", json={"change": 1, "reason": "restock"})
    assert r.status_code == 404, r.text


def test_adjust_requires_admin(od):
    r = od.client.post(f"{INVENTORY}/{uuid.uuid4()}/adjust", json={"change": 1, "reason": "restock"})
    assert r.status_code in (401, 403), r.text


def test_movements_newest_first(od):
    p = od.seed_product(stock_quantity=0)
    od.login_admin()
    od.client.post(f"{INVENTORY}/{p['id']}/adjust", json={"change": 10, "reason": "restock"})
    od.client.post(f"{INVENTORY}/{p['id']}/adjust", json={"change": -1, "reason": "damaged"})

    r = od.client.get(f"{INVENTORY}/{p['id']}/movements")
    assert r.status_code == 200, r.text
    assert [m["reason"] for m in r.json()["movements"]] == ["damaged", "restock"]


# =====================================================================
# Product form goes through the ledger
# =====================================================================
def test_product_edit_stock_is_ledgered_as_adjustment(od):
    p = od.seed_product(stock_quantity=10, slug="hair-serum", is_active=True)
    od.login_admin()

    r = od.client.put(f"{PRODUCTS}/{p['id']}", json={"stock_quantity": 7})
    assert r.status_code == 200, r.text
    assert p["stock_quantity"] == 7
    [m] = _movements(od, p["id"])
    assert (m["change"], m["reason"]) == (-3, "adjustment")


def test_product_edit_with_unchanged_stock_writes_no_ledger_row(od):
    p = od.seed_product(stock_quantity=10, slug="hair-serum", is_active=True)
    od.login_admin()
    r = od.client.put(f"{PRODUCTS}/{p['id']}", json={"stock_quantity": 10, "name": "Hair Serum Pro"})
    assert r.status_code == 200, r.text
    assert p["name"] == "Hair Serum Pro"
    assert _movements(od) == []


def test_product_create_records_initial_stock(od):
    od.login_admin()
    r = od.client.post(PRODUCTS, json={"name": "Shampoo", "price": 500, "category": "hair", "stock_quantity": 12})
    assert r.status_code == 200, r.text
    pid = r.json()["product"]["id"]
    [m] = _movements(od, pid)
    assert (m["change"], m["balance_after"], m["reason"]) == (12, 12, "initial")


# =====================================================================
# Order lifecycle
# =====================================================================
@pytest.mark.parametrize("current,target", [
    ("pending", "shipped"),
    ("pending", "paid"),
    ("paid", "pending"),
    ("delivered", "cancelled"),
    ("cancelled", "paid"),
    ("shipped", "paid"),
])
def test_disallowed_transitions_are_400(od, current, target):
    order = od.seed_order("u1", status=current)
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": target})
    assert r.status_code == 400, r.text
    assert order["status"] == current


def test_ship_stores_tracking_and_timeline(od):
    order = od.seed_order("u1", status="paid", payment_status="completed")
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={
        "status": "shipped", "courier_name": "Delhivery", "tracking_number": "AWB1",
    })
    assert r.status_code == 200, r.text
    assert order["courier_name"] == "Delhivery" and order["tracking_number"] == "AWB1"
    assert order["shipped_at"]

    events = od.client.get(f"{ADMIN_ORDERS}/{order['id']}/events").json()["events"]
    assert [(e["from_status"], e["to_status"], e["source"]) for e in events] == [("paid", "shipped", "admin")]


def test_same_status_is_noop(od):
    order = od.seed_order("u1", status="shipped")
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": "shipped"})
    assert r.status_code == 200, r.text
    assert r.json()["changed"] is False
    assert od.db.table("product_order_events").rows == []


def test_cancel_paid_order_restocks_once_and_flags_refund(od):
    p = od.seed_product(stock_quantity=10)
    order = _paid_order(od, p, qty=3)
    assert p["stock_quantity"] == 7
    od.login_admin()

    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": "cancelled"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stock_restored"] is True
    assert body["refund_required"] is True
    assert p["stock_quantity"] == 10
    assert order["cancelled_at"]
    [m] = _movements(od, p["id"])
    assert (m["change"], m["reason"], m["order_id"]) == (3, "order_cancelled", order["id"])


def test_cancel_without_restock_keeps_stock(od):
    p = od.seed_product(stock_quantity=10)
    order = _paid_order(od, p, qty=3)
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": "cancelled", "restock": False})
    assert r.status_code == 200, r.text
    assert r.json()["stock_restored"] is False
    assert p["stock_quantity"] == 7


def test_cancel_unpaid_order_does_not_touch_stock(od):
    p = od.seed_product(stock_quantity=10)
    order = od.seed_order("u1", status="pending")
    od.seed_order_item(order["id"], product_id=p["id"], quantity=3)
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/status", json={"status": "cancelled"})
    assert r.status_code == 200, r.text
    assert r.json()["stock_restored"] is False
    assert r.json()["refund_required"] is False
    assert p["stock_quantity"] == 10


def test_update_shipment_sets_and_clears(od):
    order = od.seed_order("u1", status="shipped", courier_name="Old", tracking_number="AWB0")
    od.login_admin()
    r = od.client.patch(f"{ADMIN_ORDERS}/{order['id']}/shipment",
                        json={"tracking_number": "AWB9", "tracking_url": None, "courier_name": ""})
    assert r.status_code == 200, r.text
    assert order["tracking_number"] == "AWB9"
    assert order["tracking_url"] is None
    assert order["courier_name"] == "Old"        # blank = untouched
    assert order["status"] == "shipped"


# =====================================================================
# Delivery webhook
# =====================================================================
@pytest.fixture()
def hook(od, monkeypatch):
    async def _secret(self):
        return SECRET
    monkeypatch.setattr(DeliveryWebhookService, "resolve_secret", _secret)

    def send(body, secret=SECRET):
        raw = json.dumps(body).encode()
        sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return od.client.post(DELIVERY_HOOK, content=raw,
                              headers={"X-Delivery-Signature": sig, "Content-Type": "application/json"})
    return send


def test_webhook_bad_signature_is_400(od, hook):
    order = od.seed_order("u1", status="paid")
    r = hook({"order_number": order["order_number"], "event": "picked_up"}, secret="wrong")
    assert r.status_code == 400, r.text
    assert order["status"] == "paid"


def test_webhook_missing_secret_is_503(od):
    r = od.client.post(DELIVERY_HOOK, content=b"{}", headers={"X-Delivery-Signature": "x"})
    assert r.status_code == 503, r.text


def test_webhook_pickup_ships_order_and_stores_awb(od, hook):
    order = od.seed_order("u1", status="paid", payment_status="completed")
    r = hook({"order_number": order["order_number"], "event": "picked_up",
              "courier_name": "Shiprocket", "tracking_number": "AWB77"})
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "status_updated"
    assert order["status"] == "shipped"
    assert order["tracking_number"] == "AWB77"
    [e] = od.db.table("product_order_events").rows
    assert (e["source"], e["event"], e["to_status"]) == ("delivery_webhook", "picked_up", "shipped")
    assert e["payload"]["courier_name"] == "Shiprocket"


def test_webhook_finds_order_by_tracking_number_and_delivers(od, hook):
    order = od.seed_order("u1", status="shipped", tracking_number="AWB5")
    r = hook({"tracking_number": "AWB5", "event": "delivered"})
    assert r.status_code == 200, r.text
    assert order["status"] == "delivered"
    assert order["delivered_at"]


def test_webhook_in_transit_on_shipped_order_only_logs(od, hook):
    order = od.seed_order("u1", status="shipped")
    r = hook({"order_number": order["order_number"], "event": "in_transit"})
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "logged"
    assert order["status"] == "shipped"
    assert len(od.db.table("product_order_events").rows) == 1


def test_webhook_rto_delivered_cancels_and_restocks(od, hook):
    p = od.seed_product(stock_quantity=10)
    order = _paid_order(od, p, qty=2, )
    order["status"] = "shipped"
    r = hook({"order_number": order["order_number"], "event": "rto_delivered"})
    assert r.status_code == 200, r.text
    assert order["status"] == "cancelled"
    assert p["stock_quantity"] == 10


def test_webhook_cannot_resurrect_cancelled_order(od, hook):
    order = od.seed_order("u1", status="cancelled")
    r = hook({"order_number": order["order_number"], "event": "delivered"})
    assert r.status_code == 200, r.text
    assert order["status"] == "cancelled"
    [e] = od.db.table("product_order_events").rows
    assert e["to_status"] is None and "ignored" in e["note"]


def test_webhook_unknown_order_and_event_are_acknowledged(od, hook):
    r = hook({"order_number": "NOPE", "event": "delivered"})
    assert r.status_code == 200 and r.json()["action"] == "order_not_found"

    order = od.seed_order("u1", status="paid")
    r = hook({"order_number": order["order_number"], "event": "weird_courier_state"})
    assert r.status_code == 200 and r.json()["action"] == "logged_unknown_event"
    assert order["status"] == "paid"
