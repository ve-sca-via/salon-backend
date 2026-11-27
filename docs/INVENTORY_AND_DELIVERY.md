---
title: Inventory & delivery — stock ledger, order fulfilment, delivery webhook
area: backend
type: reference
status: current
updated: 2026-11-27
read_when: Changing product stock, the product-order lifecycle, or integrating a delivery partner (Shiprocket, Delhivery, Porter, ...).
related:
  - backend/docs/MIGRATION_SAFETY.md
  - backend/docs/PARTIAL_UPDATES.md
  - backend/docs/PAYMENT_FLOW_AUDIT.md
tags: [backend, admin, products, inventory, delivery, webhooks]
---
# Inventory & delivery

**Model:** every product ships from **one central warehouse**, and **admins**
manage the stock. There is no separate inventory role and no multi-location
stock, both by client decision. The catalogue is small (under 50 products), so
the design is deliberately small too: one stock number per product plus a ledger.

Migration: `supabase/migrations/20261127000000_add_inventory_ledger_and_shipments.sql`.

## Stock

`products.stock_quantity` is the running balance. **Never write it directly.**
Every change goes through a SECURITY DEFINER RPC (service_role only). Each RPC
updates the balance and appends a row to `product_stock_movements` in the same
transaction, so a product's ledger always sums to its stock.

| Reason | Written by | Direction |
|---|---|---|
| `initial` | product create (`InventoryService.record_initial_stock`); opening balances backfilled by the migration | + |
| `restock` | admin, `POST /admin/inventory/{id}/adjust` | + |
| `damaged` | admin, same endpoint (damaged / expired / lost) | − |
| `adjustment` | admin count correction, same endpoint; also `PUT /products/{id}` with `stock_quantity` (`set_product_stock`, the difference is computed under a row lock) | ± |
| `sale` | `decrement_product_stock(order_id)` when an order is paid, once per order (`stock_decremented`) | − |
| `order_cancelled` | `restore_order_stock(order_id, actor)` when a paid order is cancelled, once per order (`stock_restored`) | + |

Stock cannot go below zero. The RPCs raise and the API returns 400.

History: `GET /admin/inventory/{product_id}/movements` (newest first).

**Admin panel:** on the Products page, click a stock number (or use
*Stock & history* in the row menu) to open the adjust modal. Stock is editable on
the product form only at creation (as opening stock). After that it is read-only
there, so a sale made while the form is open can't be overwritten.

## Order lifecycle

```
pending ──(payment flow only)──▶ paid ──▶ shipped ──▶ delivered
   │                              │  └──────────────────▲   (paid → delivered: hand delivery)
   └──▶ cancelled ◀───────────────┴── shipped ─▶ cancelled
```

`ALLOWED_TRANSITIONS` in `app/services/product_order_service.py` is the only
place these rules live. The admin panel copies them only to decide which
options to show.

- `paid` is set **only** by the payment flow (verify / Razorpay webhook / dev-verify),
  never by hand, because marking an order paid by hand would skip the stock decrement.
- `delivered` and `cancelled` are final.
- Setting the status an order already has is a no-op success (webhooks repeat).
- The update is guarded on the status that was read: if two moves happen at
  once, the second gets 409.
- **Cancel** returns stock if `restock` is true (the default) and the order
  was paid. It **does not refund**: the response's `refund_required: true`
  tells the admin to refund from the Razorpay dashboard.
- Timestamps: `shipped_at`, `delivered_at`, `cancelled_at`.

Endpoints (admin):

- `PATCH /admin/product-orders/{id}/status`: `{status, courier_name?, tracking_number?, tracking_url?, restock?, note?}`
- `PATCH /admin/product-orders/{id}/shipment`: set, correct or clear tracking without changing the status (partial-update contract: blank = untouched, null = clear)
- `GET /admin/product-orders/{id}/events`: the order timeline

Every status change and courier update appends to `product_order_events`
(`source` = `admin` | `delivery_webhook` | `system`, with the raw webhook body
in `payload`).

## Delivery webhook (partner-neutral)

No partner is chosen yet, so the backend accepts **our own** small format.
Integrating a partner means one of two things:

1. The partner can send custom webhooks (or a no-code relay such as Zapier or
   Make can): point it at our endpoint in this format. Or:
2. The partner has a fixed format: add a thin adapter route that verifies
   **their** auth, maps their payload to the fields below, and calls
   `DeliveryWebhookService.handle_update(body)`. The order flow needs no
   changes.

```
POST /api/v1/webhooks/delivery
X-Delivery-Signature: <hex HMAC-SHA256 of the raw body, key = delivery_webhook_secret>
Content-Type: application/json

{
  "order_number":   "PO-...",            // or tracking_number, at least one
  "tracking_number": "AWB123",
  "event":          "picked_up",
  "courier_name":   "Delhivery",         // optional
  "tracking_url":   "https://...",       // optional
  "note":           "free text",         // optional
  "occurred_at":    "2026-11-27T10:00:00Z" // optional, stored in payload
}
```

Secret: system config key **`delivery_webhook_secret`** (Admin panel → Config,
same place as `razorpay_webhook_secret`). Until it is set, the endpoint returns 503.

| `event` | Effect on the order |
|---|---|
| `picked_up`, `in_transit`, `out_for_delivery` | → `shipped` (if `paid`); otherwise timeline only |
| `delivered` | → `delivered` |
| `rto_delivered` (parcel back at the warehouse) | → `cancelled` **and restock** |
| `manifested`, `delivery_failed`, `rto_initiated`, `shipment_cancelled` | timeline only |
| anything else | timeline only (`logged_unknown_event`) |

The order is found by `order_number` first, then `tracking_number`. The first
courier, AWB or URL heard for an order is stored on it.

Response codes (same contract as the Razorpay webhook): **200** received (acted on
or deliberately ignored: unknown order, a move that isn't allowed, out of order),
**400** bad signature or body (don't redeliver), **503** no secret configured,
**500** our own failure (redeliver).

Test locally:

```bash
BODY='{"order_number":"PO-123","event":"picked_up","tracking_number":"AWB1"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)
curl -X POST localhost:8000/api/v1/webhooks/delivery \
  -H "X-Delivery-Signature: $SIG" -H 'Content-Type: application/json' -d "$BODY"
```

## Not built (on purpose, for now)

- Refunds on cancel: done by hand in Razorpay.
- Creating shipments or pickups via a partner API: needs a chosen partner.
- Showing tracking to customers in the web or mobile apps: the fields are
  already returned by `/product-orders/my-orders` and `/product-orders/{id}`.
- Low-stock alerts: the admin list shows stock in red at 0 and amber at 5 or less.

<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [Database migrations — workflow & safety](MIGRATION_SAFETY.md) · [Partial updates (edit forms)](PARTIAL_UPDATES.md) · [Payment flow audit & open payment incident](PAYMENT_FLOW_AUDIT.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
