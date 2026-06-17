# 🎟️ Coupons & Discounts — UI Build Spec

> **Purpose:** This document is a self-contained build brief for an agent/developer to create the
> coupon UI across three frontends. The **backend is already complete, migrated, and tested** —
> no backend work is required. Build the UI to the contracts below.
>
> **Backend base URL:** `http://localhost:8000` · **Global prefix:** `/api/v1`
> **Repos:**
> - `salon-admin-panel` — React 19 + Redux Toolkit Query (web admin) → **Admin coupon management**
> - `salon-management-app` — React (Vite) + RTK Query (web; has vendor + customer pages) → **Vendor coupon management** + **customer apply-coupon at checkout**
> - `lubist_mobile_application` — Expo RN + TanStack Query (customer mobile) → **apply-coupon at checkout**

---

## 1. Concept (read this first)

The platform supports code-based **coupons** that are applied **at checkout time** (recorded on the
booking), separate from the older vendor "Run Promo" automatic sale (which silently discounts
service prices with no code). A coupon can be:

- **Issued by a vendor** (works only at that salon) or **by an admin** (platform-wide — works at *any* salon).
- A **service discount** (reduces the amount paid at the salon) or a **convenience-fee discount** (reduces the online "pay now" fee — e.g. "50% off fees for first-time users").
- **Percentage** or **flat amount**, optionally with a **max cap** ("upto 20%, max ₹300"), a **minimum order amount**, a **first-time-user** restriction, a **validity window**, and **usage limits** (total and per-user).

**Best-of rule (important for UX copy):** a service coupon does **not** stack with an active salon
sale — whichever gives the bigger discount wins. If the salon's running sale already beats the
coupon, the API returns the coupon as not-applied with a reason like *"A better discount is already
applied at this salon."* Convenience-fee coupons are independent and always apply on top.

---

## 2. Shared API reference

### 2.1 Field reference / enums

| Field | Type | Notes |
|---|---|---|
| `code` | string | Shareable code. Stored UPPERCASE; UI should uppercase on input. 3–40 chars. |
| `title` | string | Human label, 2–255 chars. |
| `scope` | `"platform" \| "vendor"` | platform = any salon; vendor = one salon (admin-only field). |
| `salon_id` | uuid? | Required when `scope="vendor"` (admin form). Vendor app sets it automatically. |
| `funded_by` | `"platform" \| "vendor"` | Who absorbs the cost (settlement). Admin-only field. |
| `applies_to` | `"service" \| "convenience_fee"` | What the discount reduces. |
| `discount_type` | `"percentage" \| "flat_amount"` | |
| `discount_value` | number > 0 | If percentage, must be ≤ 100. |
| `max_discount_cap` | number? | Caps the discount (use for "upto X%"). |
| `min_order_amount` | number? | Minimum service subtotal to qualify. |
| `first_time_scope` | `"platform" \| "vendor" \| null` | null = anyone; platform = first booking ever; vendor = first at this salon. |
| `usage_limit_total` | int? | null = unlimited. |
| `usage_limit_per_user` | int? | Defaults to 1; null = unlimited. |
| `used_count` | int | Read-only; redemptions so far. |
| `valid_from` | ISO datetime? | Defaults to now. |
| `valid_until` | ISO datetime? | null = no expiry. |
| `is_active` | bool | Soft on/off. |

### 2.2 `CouponResponse` (returned by create/list/get/update)
```jsonc
{
  "id": "uuid", "code": "SAVE20", "title": "20% off services",
  "scope": "vendor", "salon_id": "uuid", "created_by": "uuid", "funded_by": "vendor",
  "applies_to": "service", "discount_type": "percentage", "discount_value": 20,
  "max_discount_cap": 300, "min_order_amount": null, "first_time_scope": null,
  "usage_limit_total": null, "usage_limit_per_user": 1, "used_count": 4,
  "valid_from": "2026-06-01T00:00:00Z", "valid_until": null, "is_active": true,
  "created_at": "...", "updated_at": "..."
}
```

### 2.3 Endpoints

**Admin** (`bearer` admin) — `salon-admin-panel`
| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/admin/coupons` | `?scope=&salon_id=` (optional) | `CouponResponse[]` |
| POST | `/admin/coupons` | `AdminCouponCreate` (below) | `CouponResponse` |
| GET | `/admin/coupons/{id}` | — | `CouponResponse` |
| PATCH | `/admin/coupons/{id}` | `CouponUpdate` (below) | `CouponResponse` |
| DELETE | `/admin/coupons/{id}` | — (deactivates; keeps history) | `CouponResponse` |

**Vendor** (`bearer` vendor) — `salon-management-app` vendor pages
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/vendors/coupons` | — | `CouponResponse[]` (this vendor's salon only) |
| POST | `/vendors/coupons` | `VendorCouponCreate` (below) | `CouponResponse` |
| PATCH | `/vendors/coupons/{id}` | `CouponUpdate` | `CouponResponse` |
| DELETE | `/vendors/coupons/{id}` | — (deactivates) | `CouponResponse` |

**Customer** (`bearer` customer) — `salon-management-app` customer + `lubist_mobile_application`
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/customers/cart/validate-coupon` | `{ "code": "SAVE20" }` | `CouponValidationResult` (below) |
| POST | `/payments/cart/create-order` | `{ "coupon_code": "SAVE20" }` (optional) | order incl. discounted `breakdown` |
| POST | `/customers/cart/checkout` | existing body **+ `coupon_code`** | booking with discount fields |

### 2.4 Request bodies

`VendorCouponCreate` (vendor form — scope/salon/funded are forced server-side):
```jsonc
{ "code", "title", "applies_to", "discount_type", "discount_value",
  "max_discount_cap?", "min_order_amount?", "first_time_scope?",
  "usage_limit_total?", "usage_limit_per_user?", "valid_from?", "valid_until?" }
```

`AdminCouponCreate` = all of the above **plus** `scope` (default `"platform"`),
`salon_id?` (required if `scope="vendor"`), `funded_by` (default `"platform"`).

`CouponUpdate` (PATCH — code & scope are immutable):
```jsonc
{ "title?", "discount_value?", "max_discount_cap?", "min_order_amount?",
  "usage_limit_total?", "usage_limit_per_user?", "valid_until?", "is_active?" }
```

### 2.5 `CouponValidationResult` (the "Apply coupon" response)
```jsonc
{
  "valid": true,
  "reason": null,                       // human message when valid=false
  "coupon_id": "uuid",                  // null when not applied
  "coupon_code": "SAVE20",              // null when not applied
  "breakdown": {
    "subtotal_service_price": 1000.0,   // services before coupon (post automatic-sale)
    "discount_amount": 200.0,           // coupon discount on services
    "service_total_due": 800.0,         // pay at salon
    "convenience_fee_base": 100.0,      // fee before coupon
    "convenience_fee_discount": 0.0,    // coupon discount on fee
    "convenience_fee_due": 100.0,       // pay now (online)
    "total_amount": 900.0,              // service_total_due + convenience_fee_due
    "discount_source": "coupon"         // "coupon" | "sale" | null
  }
}
```
When `valid=false`, `breakdown` may still be present (showing the un-discounted totals) and
`reason` explains why (see §6 for the message set).

---

## 3. Surface A — Admin panel (`salon-admin-panel`)

**Goal:** let admins create/manage platform-wide coupons (and optionally salon-scoped ones).

**Where it fits:** new top-level page `Coupons.jsx` in `src/pages/`, a nav entry beside
`SystemConfig`/`Products`, and a new RTK Query slice `src/services/api/couponApi.js`
(mirror `configApi.js` / `productApi.js`). Wire the slice into the existing `store.js`.

### Screens / components
1. **Coupons list page** — table of all coupons with columns:
   `Code` · `Title` · `Scope` (Platform / salon name) · `Applies to` (Service / Fee) ·
   `Discount` (render `20%` or `₹150`, append `· max ₹300` if cap, `· min ₹500` if min) ·
   `First-time` (—/Platform/Vendor) · `Usage` (`used_count / usage_limit_total or ∞`) ·
   `Validity` (date range or "No expiry") · `Status` (Active/Inactive toggle).
   - Filters: scope (All/Platform/Vendor), status (All/Active/Inactive), search by code/title.
   - Row actions: **Edit**, **Deactivate** (DELETE → confirm modal; copy: "Deactivate keeps the redemption history; the code stops working").
   - "Copy code" button per row.
2. **Create / Edit coupon modal or drawer** (form):
   - **Code** (text, auto-uppercase, disabled on edit), **Title**.
   - **Scope** radio: *Platform-wide (any salon)* / *Specific salon* → when "Specific salon", show a **salon picker** (reuse the salons list from `salonApi`) bound to `salon_id`.
   - **Funded by** radio: *Platform* / *Vendor* (default Platform; show helper: "Who absorbs the discount cost").
   - **Applies to** radio: *Service price* / *Convenience fee*.
   - **Discount type** radio: *Percentage* / *Flat amount* → value input (suffix `%` or prefix `₹`).
   - **Max discount cap** (optional, shown mainly for percentage).
   - **Minimum order amount** (optional).
   - **First-time only** select: *Anyone* / *First booking on platform* / *First booking at this salon*.
   - **Usage limit (total)** (optional, blank = unlimited), **Per user** (default 1, blank = unlimited).
   - **Valid from** (optional, default now) / **Valid until** (optional, blank = no expiry).
   - On edit, only send fields in `CouponUpdate` (PATCH); code & scope read-only.
3. **Empty state** + **toast** on create/update/deactivate. Handle `409` (duplicate active code) with: "An active coupon with this code already exists."

---

## 4. Surface B — Vendor dashboard (`salon-management-app` → `src/pages/vendor`)

**Goal:** let a vendor create coupon codes for **their own salon** (the "issue a code, share on
Instagram" use case). This is separate from the existing **Run Promo** (`VendorRunPromo.jsx`,
which is the codeless automatic sale).

**Where it fits:** new page `src/pages/vendor/VendorCoupons.jsx`, linked from `VendorDashboard.jsx`
next to "Run Promo". Add coupon endpoints to the existing `src/services/api/vendorApi.js`
(it already has `getActiveVendorPromotion` / `applyVendorPromotion` — follow that exact RTK Query
style, add a `VendorCoupons` tag type).

### RTK Query endpoints to add (vendorApi.js)
- `getVendorCoupons` → GET `/vendors/coupons` (providesTags `VendorCoupons`)
- `createVendorCoupon` → POST `/vendors/coupons` (invalidates `VendorCoupons`)
- `updateVendorCoupon` → PATCH `/vendors/coupons/{id}`
- `deactivateVendorCoupon` → DELETE `/vendors/coupons/{id}`

### Screens / components
1. **My Coupons list** — card or table list of the salon's coupons (same columns as admin **minus** Scope/Funded-by, which are fixed). Show `used_count`, validity, active toggle, "Copy code", Edit, Deactivate.
2. **Create / Edit coupon form** — `VendorCouponCreate` fields only (no scope/salon/funded — server forces vendor scope, this salon, funded_by=vendor):
   - Code, Title, Applies to (Service / Convenience fee), Discount type + value, Max cap, Min order, First-time (Anyone / First on platform / First at my salon), Usage total, Per user, Valid from/until.
3. **Helper banners:**
   - On the page: "Coupons are codes your customers type at checkout. For an automatic storewide sale with no code, use **Run Promo** instead."
   - Note that a coupon and a Run Promo sale don't stack — the bigger discount wins.
4. Toast + `409` duplicate-code handling as in admin.

> A vendor only ever has one salon (resolved server-side); no salon picker needed.

---

## 5. Surface C — Customer "Apply coupon" at checkout

This is the surface that actually **redeems** coupons. Build it in **both**:
- `salon-management-app` → `src/pages/public/Checkout.jsx` (service booking checkout; web)
- `lubist_mobile_application` → CheckoutScreen (Expo RN; see tracker)

### Flow
1. On the checkout/cart screen add a **"Have a coupon?"** input + **Apply** button.
2. On Apply → `POST /customers/cart/validate-coupon` with `{ code }`.
   - **`valid: true`** → show applied state: green chip with the code, a "Remove" (✕) action, and update the price summary from `breakdown`:
     - Services: `subtotal_service_price` with `− discount_amount` line (if > 0) → `service_total_due` ("Pay at salon").
     - Fee: `convenience_fee_base` with `− convenience_fee_discount` line (if > 0) → `convenience_fee_due` ("Pay now").
     - Grand total `total_amount`. Show a "You save ₹X" badge = `discount_amount + convenience_fee_discount`.
   - **`valid: false`** → inline error using `reason` (see §6). Keep totals un-discounted.
3. Store the applied `coupon_code` in checkout state.
4. **Create order:** `POST /payments/cart/create-order` with `{ coupon_code }`. The returned
   `breakdown` (and the amount charged) already reflects the fee discount — open Razorpay with that amount.
5. **Confirm booking:** `POST /customers/cart/checkout` with the existing body **plus
   `coupon_code`**. The backend re-validates and records the redemption. The created booking now
   includes `discount_amount`, `convenience_fee_discount`, `coupon_id`, `coupon_code`.

### UX rules
- Re-validate (or clear the applied coupon) whenever the cart changes — the discount depends on cart contents.
- A coupon that doesn't beat the salon's active sale comes back `valid:false` with the "better discount already applied" reason — show it as an info message, not a hard error.
- Always show "pay now" (fee) vs "pay at salon" (services) clearly; coupons may reduce either or both.

---

## 6. Reason / error messages (from the API)

`validate-coupon` returns these human-readable `reason` strings when `valid:false` — display as-is:
- "This coupon code is not valid."
- "This coupon is no longer active."
- "This coupon is not active yet."
- "This coupon has expired."
- "This coupon cannot be used at this salon."
- "Your order does not meet the minimum amount for this coupon."
- "This coupon is only valid for first-time customers."
- "This coupon has reached its usage limit."
- "You have already used this coupon."
- "A better discount is already applied at this salon." (info, not error)
- "Your cart is empty."

Create/update errors: `409 Conflict` → "An active coupon with this code already exists."
Validation errors return FastAPI `422` with `{detail:[...]}` — map to field errors.

---

## 7. Client-side validation to enforce (match server constraints)
- `code`: required, 3–40 chars, uppercased.
- `discount_value`: > 0; if `discount_type="percentage"`, ≤ 100.
- `max_discount_cap`, `min_order_amount`, `usage_limit_*`: ≥ 0 when provided.
- `valid_until` ≥ `valid_from` when both set.
- Admin: `salon_id` required when `scope="vendor"`.

---

## 8. Build checklist
- [ ] **Admin panel:** `couponApi.js` slice + `Coupons.jsx` page + nav + create/edit form + list/filters/deactivate.
- [ ] **Vendor app:** coupon endpoints in `vendorApi.js` + `VendorCoupons.jsx` + link from dashboard + create/edit form.
- [ ] **Customer (web `Checkout.jsx`):** apply-coupon input → validate → price summary → pass `coupon_code` into create-order + checkout.
- [ ] **Customer (mobile):** same flow on CheckoutScreen (TanStack hooks — see tracker).
- [ ] Reason-message handling, 409 handling, re-validate-on-cart-change everywhere.

_Backend reference: coupon migrations `supabase/migrations/20260614000000_*` & `20260614000001_*`;
services `app/services/coupon_service.py`, `app/services/pricing_service.py`; tests
`tests/test_coupon_pricing.py`._
