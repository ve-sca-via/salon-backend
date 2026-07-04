# Regular Buyer — Complete Workflow Reference

> **One-line definition:** A *regular buyer* is a salon/shop owner who wants to **buy products from us at wholesale (B2B) prices**, but does **not** want to list their salon publicly for bookable services.

This document is the single source of truth for how the `regular_buyer` role works end-to-end
across the backend, the admin panel, and the web/vendor app. Read it before touching anything
regular-buyer-related so you don't get confused again.

---

## 1. What a Regular Buyer actually is

| | Regular Salon (Vendor) | Regular Buyer |
|---|---|---|
| `user_role` (profiles) | `vendor` | `regular_buyer` |
| `salons.salon_type` | `salon` | `regular_buyer` |
| `vendor_join_requests.request_type` | `salon` | `regular_buyer` |
| Listed publicly for bookings? | **Yes** (discoverable, has services) | **No** (hidden from salon discovery) |
| Offers services / takes bookings? | Yes | No |
| Buys products from us? | Yes (B2B price) | Yes (B2B price) — this is their whole purpose |
| Pays registration fee? | Yes | Yes (same flow) |
| Product pricing tier | Wholesale (`b2b_discount_price`) | Wholesale (`b2b_discount_price`) |

Both `vendor` and `regular_buyer` are treated as **B2B roles** and receive wholesale product
pricing. The single helper that decides this is:

- `app/services/product_service.py` → `is_b2b_role(user_role)` returns `True` for
  `("vendor", "regular_buyer")`.
- `effective_unit_price()` and `_apply_b2b_pricing()` swap in `products.b2b_discount_price`
  when the buyer is a B2B role and a B2B price is set.

The **only** functional difference between a vendor and a regular buyer is that the regular
buyer's salon is `salon_type = 'regular_buyer'`, which **hides it from public salon discovery**
and blocks the public salon detail endpoint:

- `app/api/salons.py` → returns `404 "Salon not available."` when `salon_type == 'regular_buyer'`.

Everything else (auth, registration, payment, product catalog, orders) is the **same shared code
path** as a normal vendor.

---

## 2. Where it comes from (schema / migrations)

Added in `supabase/migrations/20260512000000_add_regular_buyer_and_b2b_pricing.sql`:

1. `ALTER TYPE user_role ADD VALUE 'regular_buyer'` — new role.
2. `products.b2b_discount_price`, `products.b2b_discount_percentage` — wholesale price columns.
3. `vendor_join_requests.request_type` — `'salon' | 'regular_buyer'`.
4. `salons.salon_type` — `'salon' | 'regular_buyer'` (regular_buyer salons hidden from discovery).
5. `product_orders.user_type` — records the buyer's role at purchase time.

B2B discount pricing was refined in `20260514120000_add_b2b_discount_pricing.sql`.

---

## 3. End-to-end creation workflow

```
 RM (web app)              Admin (admin panel)           Buyer (email → web app)
┌──────────────┐          ┌────────────────────┐        ┌──────────────────────────┐
│ Add Regular  │  submit  │ PendingSalons      │ approve│ 1. Click email link      │
│ Buyer form   ├─────────►│ "Approve Buyer"    ├───────►│ 2. Set password          │
│ (3 steps)    │          │                    │        │ 3. Pay registration fee  │
└──────────────┘          └────────────────────┘        │ 4. Buy products @ B2B    │
   request_type              creates salon               └──────────────────────────┘
   = regular_buyer           salon_type = regular_buyer
                             sends registration email
```

### Step 1 — RM submits the request (web app)
- File: `salon-management-app/src/pages/hmr/AddSalonForm.jsx`
- Entry point: route `add-salon?type=regular_buyer` (the `type` query param drives the form).
- The form is a **shortened 3-step flow** (Basic Info → Photos → Review). It **skips** the
  services and business-hours steps that a normal salon has.
- Submits to `POST /rm/vendor-requests` with `request_type: "regular_buyer"` and the owner's
  email/name/phone. **`owner_email` is required** — it's where the registration link goes.

### Step 2 — Admin approves (admin panel)
- File: `salon-admin-panel/src/pages/PendingSalons.jsx`
- Regular-buyer requests appear in the same pending queue, tagged with a blue **"Regular Buyer"**
  badge. The approve button reads **"Approve Buyer"**.
- Calls `POST /admin/vendor-requests/{id}/approve`.

### Step 3 — Backend approval logic
- File: `app/services/vendor_approval_service.py` → `approve_vendor_request()`
- Creates a `salons` row with `salon_type = request_type` (so `regular_buyer`),
  `is_active=false`, `is_verified=false`, `registration_fee_paid=false`.
- Generates a JWT **registration token** and **sends the approval email** with a link to
  `{VENDOR_PORTAL_URL}/complete-registration?token=...`.
  (See `_send_approval_email()` and `app/services/email.py → send_vendor_approval_email()`.)

### Step 4 — Buyer completes registration
- File: `salon-management-app/src/pages/vendor/CompleteRegistration.jsx`
- Calls the completion endpoint → `app/services/vendor_service.py → complete_registration()`.
- This reads `salon_type` (fallback: request's `request_type`) and sets the new account's
  `user_role = 'regular_buyer'`. Creates the auth user + profile, links to the salon.

### Step 5 — Buyer pays the registration fee & starts buying
- Registration fee flow: `VendorPayment.jsx` (Razorpay).
- Product buying flow: `salon-management-app/src/pages/public/ProductCheckout.jsx`.
- Because `user_role = regular_buyer`, the product APIs return B2B prices automatically.

---

## 4. Admin-panel controls related to Regular Buyer

| Screen | File | What it controls |
|---|---|---|
| Pending Salons | `PendingSalons.jsx` | Approve/reject regular-buyer requests ("Approve Buyer"). |
| Salons | `Salons.jsx` | Lists salons incl. `salon_type` (regular buyers included). |
| Products | `Products.jsx` | Set `b2b_discount_price` / `b2b_discount_percentage` — the wholesale price regular buyers (and vendors) pay. |
| Product Orders | `ProductOrders.jsx` | View product orders, incl. `user_type` (customer vs vendor/regular_buyer). |
| System Config | `SystemConfig.jsx` | Razorpay keys (`razorpay_key_id`/`razorpay_key_secret`) and `registration_fee_amount`. |

---

## 5. Known client-reported issues (diagnosis)

### 5.1 Registration email not being sent for regular buyers

**The email path is identical to a normal salon** — there is no regular-buyer-specific email
code. So if the salon email works but the regular-buyer one doesn't, check these in order:

1. **Owner email == RM email (most common in testing).**
   `_send_approval_email()` deliberately **skips** the email when the owner's email equals the
   RM's email:
   ```python
   if rm_email and request_data.owner_email.lower() == rm_email.lower():
       logger.info("Skipping vendor email - owner is the RM ...")
       return
   ```
   If the RM created the buyer using **their own email** as the owner email, no mail is sent.
   → **Fix while testing:** use a distinct owner email.

2. **SMTP failure is swallowed as a "warning".**
   In `approve_vendor_request()` the email send is wrapped so a failure does **not** fail the
   approval — it just appends to `warnings`. The admin still sees "approved successfully".
   → **Check:** the approval API response `data.warnings` and the backend logs for
   `"Failed to send approval email"`. If this is failing it likely affects **all** vendor
   approval emails, not just regular buyers — the buyer flow just happens to be what's being
   tested right now. Verify SMTP settings (`SMTP_HOST/PORT/USER/PASSWORD/TLS/SSL`, `EMAIL_FROM`).

3. **The registration URL is always the vendor portal.**
   The email link is `{VENDOR_PORTAL_URL}/complete-registration?token=...` for both salons and
   regular buyers. Even if email delivery is flaky, the backend **logs the full registration URL**
   on every approval (banner in `email.py → send_vendor_approval_email()`), so you can copy it
   from the logs and hand it to the buyer to unblock them immediately.

**How to confirm quickly:** approve a regular buyer with a real, distinct owner email and grep
the backend logs for `REGISTRATION URL` and `approval email`.

### 5.2 UPI option missing on Razorpay for regular buyers (but present for salon services)

**Neither checkout restricts payment methods in code.** Both build a plain Razorpay options
object with no `method`/`config` block:
- Product (regular buyer): `ProductCheckout.jsx → openRazorpay()`
- Salon service (end user): `Checkout.jsx` (booking convenience fee)

So UPI is being hidden by **Razorpay's own rules**, not our code. The two realistic causes,
ranked:

1. **UPI per-transaction amount limit (most likely).**
   UPI has an NPCI per-transaction cap (commonly **₹1,00,000**, sometimes higher for verified
   merchants). Razorpay **automatically hides UPI** when the order amount exceeds the UPI limit.
   - A **salon booking** only charges a small **convenience fee** (tens/hundreds of rupees) → UPI
     always shows.
   - A **regular buyer** buys products in bulk (B2B) → cart totals routinely exceed ₹1 lakh → UPI
     disappears.
   → **Confirm:** note the exact amount on the Razorpay screen where UPI is missing. If it's above
   ~₹1 lakh, this is the cause. Test with a small (<₹1,000) product order — UPI should reappear.

2. **Different Razorpay key/account for the product flow.**
   `ProductCheckout.jsx` uses `key: orderResponse.key_id || import.meta.env.VITE_RAZORPAY_KEY_ID`
   — it **falls back to the `VITE_RAZORPAY_KEY_ID` frontend env var** if the backend doesn't return
   a key. The booking checkout uses `orderData.key_id` **only** (no env fallback). If
   `VITE_RAZORPAY_KEY_ID` points to a **different Razorpay account** (e.g. one where UPI isn't
   activated, or a test key), the product checkout can render a different method set.
   → **Confirm:** log/inspect the `key` actually passed to `new window.Razorpay(options)` in both
   flows; they must be the same live key with UPI enabled in the Razorpay dashboard.

**Backend note:** the product order flow (`product_order_service.create_order`) resolves the key
via `resolve_razorpay_credentials(..., allow_env_fallback=True)` and can enter a **dev/simulation
mode** when credentials are placeholders — in that mode `key_id` is not a real key and the frontend
falls back to `VITE_RAZORPAY_KEY_ID`. Make sure production has real `razorpay_key_id` /
`razorpay_key_secret` in `system_config`.

---

## 6. Testing the workflow locally

Use the seeder to create a fully-activated regular buyer end-to-end (mirrors `seed_full_salon.py`
but for the `regular_buyer` path):

```bash
# backend running, venv active
python scripts/seed_regular_buyer.py
```

It: submits a `request_type=regular_buyer` join request as the RM → approves it as admin →
creates the buyer auth account (`user_role=regular_buyer`) → marks the registration paid and
activates the salon. Log in as the printed buyer credentials to test B2B product buying.

See `scripts/seed_regular_buyer.py --help` for options (reuse an existing request/salon, custom
RM/admin creds, etc.).

---

## 7. File map (quick jump)

**Backend**
- Migration: `supabase/migrations/20260512000000_add_regular_buyer_and_b2b_pricing.sql`
- B2B pricing: `app/services/product_service.py` (`is_b2b_role`, `effective_unit_price`, `_apply_b2b_pricing`)
- Approval + email: `app/services/vendor_approval_service.py`, `app/services/email.py`
- Registration completion: `app/services/vendor_service.py` (`complete_registration`)
- Public-salon hiding: `app/api/salons.py`
- Product orders / Razorpay: `app/services/product_order_service.py`, `app/services/payment.py`
- Approve endpoint: `app/api/admin/vendor_requests.py`
- Seeder: `scripts/seed_regular_buyer.py`

**Web app (salon-management-app)**
- RM create form: `src/pages/hmr/AddSalonForm.jsx` (`?type=regular_buyer`)
- Complete registration: `src/pages/vendor/CompleteRegistration.jsx`
- Registration payment: `src/pages/vendor/VendorPayment.jsx`
- Product checkout (B2B): `src/pages/public/ProductCheckout.jsx`
- Booking checkout (end user): `src/pages/public/Checkout.jsx`

**Admin panel (salon-admin-panel)**
- Approve buyers: `src/pages/PendingSalons.jsx`
- Salons list: `src/pages/Salons.jsx`
- Product B2B pricing: `src/pages/Products.jsx`
- Product orders: `src/pages/ProductOrders.jsx`
- Razorpay / fees config: `src/pages/SystemConfig.jsx`
</content>
</invoke>
