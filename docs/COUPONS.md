---
title: Coupons & discounts
area: backend
type: reference
status: current
updated: 2026-11-12
read_when: Building or debugging anything coupon-related — admin/vendor coupon CRUD, applying a code at checkout (services or products), the "available offers" lists, or why a discount did/didn't apply.
related:
  - backend/docs/PAYMENT_FLOW_AUDIT.md
  - backend/docs/PARTIAL_UPDATES.md
  - backend/docs/API_PARITY.md
tags: [backend, reference, current, coupons, payments]
---

# Coupons & discounts

Code-based coupons applied **at checkout**, recorded on the booking / product order.
Separate from the vendor "Run Promo" automatic sale, which discounts service prices
with no code.

**Single source of truth for every price:** `app/services/pricing_service.py`
(`PricingService`). Coupon rules live in `app/services/coupon_service.py`. Never compute
a discounted total anywhere else — the web and mobile checkouts display what the backend
returns.

## What a coupon can be

| Dimension | Options |
|---|---|
| Issuer / `scope` | `vendor` — works at one salon · `platform` — works everywhere (admin only) |
| `applies_to` | `service` (amount paid at the salon) · `convenience_fee` (the online "pay now" fee) · `product` (product orders) |
| `discount_type` | `percentage` (≤ 100, optional `max_discount_cap`) · `flat_amount` |
| Restrictions | `min_order_amount`, `first_time_scope` (`platform` = first booking ever, `vendor` = first at this salon), `valid_from`/`valid_until`, `usage_limit_total`, `usage_limit_per_user` (default 1) |
| `funded_by` | `platform` · `vendor` — who absorbs the cost (admin only) |

Hard rules enforced in `app/schemas/request/coupon.py`:

- **Vendors cannot create `convenience_fee` coupons** (that waives platform revenue) **or
  `product` coupons** (products are admin-managed).
- **Product coupons must be `scope: platform`.**
- `code` is stored UPPERCASE, 3–40 chars. `code` and `scope` are immutable after creation.

**Best-of rule:** a service coupon does **not** stack with an active salon sale — whichever
discount is bigger wins. If the sale wins, validation returns `valid:false` with
*"A better discount is already applied at this salon."* Convenience-fee coupons are
independent and always apply on top.

## Endpoints

Paths are under `/api/v1`. Full shapes are in the OpenAPI contract (`openapi/openapi.json`).

| Who | Method | Path | Notes |
|---|---|---|---|
| Admin | GET / POST | `/admin/coupons` | list (`?scope=&salon_id=`) / create (`AdminCouponCreate`) |
| Admin | GET / PATCH / DELETE | `/admin/coupons/{coupon_id}` | DELETE deactivates, keeps history |
| Vendor | GET / POST | `/vendors/coupons` | own salon only; scope/salon/funded_by forced server-side |
| Vendor | PATCH / DELETE | `/vendors/coupons/{coupon_id}` | |
| Customer | POST | `/customers/cart/validate-coupon` | `{code}` → `CouponValidationResult` for the service cart |
| Customer | GET | `/customers/available-coupons` | "available offers" list at service checkout + mobile home |
| Customer / buyer | POST | `/product-orders/validate-coupon` | product-cart equivalent |
| Customer / buyer | GET | `/product-orders/available-coupons` | product-checkout offers list |

The code is then passed as `coupon_code` when creating the payment order
(`/payments/cart/create-order`, product order create). Public salon list/detail responses
also embed the salon's real coupons and max-discount % for the offer carousels.

### `CouponValidationResult`

```jsonc
{
  "valid": true,
  "reason": null,                 // human message when valid=false — show as-is
  "coupon_id": "uuid", "coupon_code": "SAVE20",
  "breakdown": {
    "subtotal_service_price": 1000.0, "discount_amount": 200.0, "service_total_due": 800.0,
    "convenience_fee_base": 100.0, "convenience_fee_discount": 0.0, "convenience_fee_due": 100.0,
    "total_amount": 900.0, "discount_source": "coupon"   // "coupon" | "sale" | null
  }
}
```

`reason` strings: not valid · no longer active · not active yet · expired · cannot be used
at this salon · minimum amount not met · first-time customers only · usage limit reached ·
already used · a better discount is already applied (info, not an error) · cart is empty.
Create/update: `409` = an active coupon with this code already exists.

## Decisions (locked — don't re-open without the client)

| # | Decision |
|---|---|
| D1 | Vendors are **blocked** from `convenience_fee` coupons. |
| D2 | A coupon is **redeemed only on payment success**, never at booking creation. `redeem_coupon` RPC is service-role only and serialises with `FOR UPDATE`. |
| D3 | A cancelled booking **keeps** its redemption (audit trail) but does **not** count against "first-time" eligibility. |
| D4 | Order amounts are **pinned** when the payment order is created and trusted at checkout — no recompute-and-fail. Redemptions snapshot the coupon terms, so later coupon edits are safe. |

## Still open

- **RLS:** `coupons` / `coupon_redemptions` have RLS disabled — safe only while every access
  is service-role. Revisit if a client ever reads them directly.
- **GST:** confirm with the client that GST is charged on the post-discount convenience fee.
- **Money math** uses float with per-step rounding, not `Decimal`. Deferred; mitigated.
- **Tests not yet written:** two users racing for the last redemption; valid-at-order /
  invalid-at-checkout (TOCTOU); fee coupon hitting the ₹1 floor. The code paths exist.

## Files

| Layer | Location |
|---|---|
| Rules & validation | `app/services/coupon_service.py` |
| Pricing (single source) | `app/services/pricing_service.py` |
| Schemas | `app/schemas/request/coupon.py`, `app/schemas/response/coupon.py` |
| Admin UI | `salon-admin-panel` → Coupons page |
| Vendor UI | `salon_management_next` → `/vendor/coupons` · Partner app |
| Customer UI | web `/cart`, `/checkout`, `/checkout/products` · mobile cart + home offers |
| Tests | `tests/test_coupon*`, `tests/test_product_coupon_pricing.py` |

<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [Payment flow audit & open payment incident](PAYMENT_FLOW_AUDIT.md) · [Partial updates (edit forms)](PARTIAL_UPDATES.md) · [API parity report (generated)](API_PARITY.md)

**Referenced by:** [Regular buyer (B2B) workflow](REGULAR_BUYER_WORKFLOW.md) · [Backend tech debt & open loose ends](TECH_DEBT.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
