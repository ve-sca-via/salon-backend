---
title: Regular buyer (B2B) workflow
area: backend
type: reference
status: current
updated: 2026-11-12
read_when: Anything about the regular_buyer role — RM intake, admin approval, how the buyer logs in, the registration fee, wholesale (B2B) prices, or a buyer who can't order.
related:
  - backend/docs/system_config.md
  - backend/docs/CLIENT_APPS_AND_VERSIONING.md
  - backend/docs/COUPONS.md
  - backend/docs/E2E_TESTING.md
tags: [backend, web, admin, reference, current, regular-buyer, products]
---

# Regular buyer (B2B) workflow

A **regular buyer** is a salon/shop owner who buys **products from us at wholesale (B2B)
prices** but does **not** list a bookable salon. They use the **website only** — not the
customer app, not the Partner app.

## How it differs from a vendor

| | Vendor (salon) | Regular buyer |
|---|---|---|
| `profiles.user_role` | `vendor` | `regular_buyer` |
| `salons.salon_type` / `vendor_join_requests.request_type` | `salon` | `regular_buyer` |
| Publicly listed, takes bookings | Yes | **No** — hidden from discovery; public salon endpoints, `/services` and `/available-slots` return 404 |
| Product price | wholesale | wholesale |
| How the account is created | owner completes registration from an emailed link | **created automatically at admin approval** |
| Logs in with | email + password | **phone OTP** (no password they know) |
| Registration fee key | `registration_fee_amount` | `regular_buyer_registration_fee_amount` |
| Apps | web + Partner app | web only — the apps answer `403 USE_WEB_PORTAL` |

Wholesale pricing: `app/services/product_service.py` → `is_b2b_role()` (true for `vendor` and
`regular_buyer`) swaps `products.b2b_discount_price` into the price. Anonymous visitors never
receive the B2B price fields; logged-in users do.

## The flow

```
RM (web /rm)                    Admin (admin panel)               Buyer (web)
─────────────                   ───────────────────               ───────────
1. /rm/salons/new               3. Pending Salons →               5. /login/vendor → phone OTP
   ?type=regular_buyer             "Approve Buyer"                6. /vendor/payment → pay fee
2. OTP-verify owner's phone        (optional fee override)        7. /products → /checkout/products
   → submit request             4. backend creates salon +
                                   buyer account, emails a
                                   "you're in" notice (if email)
```

1. **Intake.** The RM uses the shortened buyer form (basic info → photos → review; no
   services/hours). Owner **phone is required and must be OTP-verified at intake** via
   `/auth/verify-phone/send-otp` + `/confirm-otp`; the returned token is submitted as
   `owner_phone_verification_token`. Owner age and gender are collected here (the profile
   needs them). **Owner email is optional.**
   Backend: `rm_service._apply_regular_buyer_phone_verification` rejects a missing,
   expired or mismatched token with 400.
2. **Approval.** Same pending queue as salons, with a "Regular Buyer" badge.
   `POST /admin/vendor-requests/{id}/approve` accepts an optional
   `custom_registration_fee_amount` for this one buyer.
3. **Account creation** — `vendor_approval_service._activate_regular_buyer`: creates the
   Supabase auth user (synthetic email `buyer.<phone>@phone.lubist.internal`, random
   password), the `regular_buyer` profile with the verified phone, and links the salon.
   If this fails it is logged as a warning; the salon row stays.
4. **Notice.** If an owner email exists, `buyer_account_activated.html` tells them to log
   in with their phone. No email → nothing is sent (expected). If the owner email equals
   the RM's email, sending is skipped (a testing footgun).
5. **Fee gate.** Until `salons.registration_fee_paid` is true, `POST /product-orders/create`
   returns **403 with the fee amount**. The fee is paid on `/vendor/payment`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Buyer "never got an email" | They may have no email on file — that's normal. They log in by phone. |
| Buyer can't log in | Approval log for `_activate_regular_buyer` errors; that the phone on the request matches the one they type. |
| "Registration fee required" on checkout | `salons.registration_fee_paid`; the fee amount comes from `custom_registration_fee_amount` → else `regular_buyer_registration_fee_amount`. |
| UPI missing in Razorpay for a large order | Razorpay hides UPI above the per-transaction UPI limit (~₹1 lakh). Our code does not restrict methods. Test with a small order. |

## Local testing

```bash
python scripts/seed_regular_buyer.py      # backend running; --help for options
```

Creates the request as RM → approves as admin → activates the buyer → marks the fee paid.
The staging E2E suite covers the same path (`buyer ›` steps) — see [E2E_TESTING.md](E2E_TESTING.md).

## Files

| Layer | Location |
|---|---|
| Schema | migrations `20260512000000` (role, B2B columns), `20261031…` (optional owner email), `20261101000000` (intake fields), `20261102000000` (fee overrides) |
| Intake | `app/services/rm_service.py`, `app/schemas/request/vendor.py` (`VendorJoinRequestBase`) |
| Approval + activation | `app/services/vendor_approval_service.py`, `app/services/email.py` |
| B2B pricing | `app/services/product_service.py` |
| Orders + fee gate | `app/services/product_order_service.py` |
| Web | `salon_management_next/src/app/(rm)/rm/salons/` (wizard, `owner-phone-verify.tsx`), `(auth)/login/vendor/`, `(vendor)/vendor/(portal)/payment/`, `(public)/checkout/products/` |
| Admin | `salon-admin-panel/src/pages/PendingSalons.jsx`, `Salons.jsx`, `Products.jsx` (B2B prices), `ProductOrders.jsx` |
| Seeder | `scripts/seed_regular_buyer.py` |

<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [system_config keys](system_config.md) · [Client apps & versioning (force-update, Partner split)](CLIENT_APPS_AND_VERSIONING.md) · [Coupons & discounts](COUPONS.md) · [Staging end-to-end flow tests](E2E_TESTING.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
