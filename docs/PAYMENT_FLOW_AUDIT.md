# Payment Flow Audit — latency, state machine, race conditions

**Date:** 2026-10-05, Phase 3 added 2026-10-08 · **Branch:** `dev` ·
**Status: all four phases implemented** (see §12, §13, §14 and §15). Nothing
deployed, and **Phase 2's migration has not been applied anywhere.**

Scope: every payment path end to end — backend (`backend/`), Next web app
(`salon_management_next/`), Expo mobile app (`lubist_mobile_application/`).
Three distinct flows exist; all three are covered:

| Flow | Who pays | Endpoints |
|---|---|---|
| **A. Service cart** (convenience fee) | customer | `POST /payments/cart/create-order` → `POST /customers/cart/checkout` |
| **B. Product order** | customer / vendor / regular buyer | `POST /product-orders/create` → `POST /product-orders/verify` |
| **C. Vendor registration fee** | vendor | `POST /payments/registration/create-order` → `POST /payments/registration/verify` |

Every finding below is numbered (`C-n` critical, `H-n` high, `M-n` medium,
`L-n` low) and cites the file and line read.

---

## 1. Complete flow sequence

### Flow A — service cart (the main customer path)

```
CUSTOMER                WEB/MOBILE                 BACKEND                      RAZORPAY
   |                         |                        |                            |
   |-- open /checkout ------>|                        |                            |
   |                         |-- GET cart ----------->|                            |
   |                         |-- GET config/public -->|   (3 parallel queries,     |
   |                         |-- GET available-slots->|    TanStack, fine)         |
   |                         |-- POST validate-coupon>|                            |
   |<--- page interactive ---|                        |                            |
   |                         |                        |                            |
   |-- click "Pay" --------->|                        |                            |
   |                         |== await checkout.js ==========================>  (CDN)
   |                         |   (SERIAL — see H-1)   |                            |
   |                         |-- POST /payments/cart/create-order -->|             |
   |                         |                        |-- orders.create ---------->|
   |                         |                        |<-- order_id ---------------|
   |                         |<-- order_id, key_id, amount_paise ----|             |
   |                         |                        |                            |
   |<-- Razorpay modal ------|                        |                            |
   |-- pay (UPI/card) ------------------------------------------------------------>|
   |                         |<== handler(payment_id, signature) ==================|
   |                         |                        |                            |
   |                         |-- POST /customers/cart/checkout ----->|             |
   |                         |                        |   ~27 SERIAL round trips   |
   |                         |                        |   incl. orders.fetch ----->|
   |                         |                        |   incl. 2x Resend email    |
   |                         |<-- booking ------------|                            |
   |<-- /booking-confirmation|                        |                            |
```

**The single structural weakness** *(as found; fixed in Phase 2 — §14)*: the arrow
`handler(...)` → `POST /customers/cart/checkout` was the **only** path by which a
successful payment became a booking. There was no Razorpay webhook (`grep -i
webhook app/` returned only unrelated comments and the unused
`razorpay_webhook_secret` config key — the webhook was deliberately removed in the
June cleanup) and no reconciliation job. If that one browser callback was lost,
the money was gone and nothing in our system knew a payment had happened.

There is now a second path: `POST /api/v1/webhooks/razorpay` completes the booking
from a pinned `payment_intents` row, so the browser callback is an optimisation
rather than the only route. It is not yet deployed and the Razorpay dashboard has
not been pointed at it.

### Flow B — product order

Order row + Razorpay order are created in **one** call *before* payment, so an
abandoned payment leaves a permanent `pending` row. Verify is a single UPDATE.

### Flow C — vendor registration

Same shape as B (DB row created at order time), plus salon activation inside verify.

---

## 2. Payment states currently implemented

### Web — `/checkout` (`checkout-shell.tsx`)

There is **no state machine**. State is four independent booleans OR-ed together:

```ts
const busy = processing || createOrder.isPending || checkoutCart.isPending || isNavigating;
```

(`checkout-shell.tsx:144`) — which collapses *six* distinct situations into one
`busy` flag that only disables a button:

| Real situation | Represented as | UI shown |
|---|---|---|
| not started | `busy === false` | Pay button enabled |
| loading SDK | `processing` | button disabled |
| creating order | `createOrder.isPending` | button disabled |
| modal open, waiting for customer | `processing` | button disabled (modal covers page) |
| confirming booking server-side | `checkoutCart.isPending` | **button disabled — nothing else** |
| navigating to confirmation | `isNavigating` | button disabled |

### Web — `/vendor/payment` (`payment-shell.tsx`)

The only place with an explicit machine: `type PaymentStep = "details" | "processing" | "success"`
(`payment-shell.tsx:22`). Three states; no `failed`, no `cancelled`, no `unknown`.

### Mobile — `CheckoutScreen.tsx`

`const busy = isCreatingOrder || isCheckingOut;` (`CheckoutScreen.tsx:81`) plus
`payVisible`. Same collapse as web, with less UI feedback.

---

## 3. Missing states

States the flows can genuinely reach but which no code represents:

| Missing state | Reachable how | Current behaviour |
|---|---|---|
| **payment failed at provider** | card declined | Web: no `payment.failed` listener at all — Razorpay's own retry UI handles it, we never learn. Mobile has the listener (`RazorpayCheckout.tsx:56`). |
| **confirming — do not leave** | always, after every payment | Only a disabled button. Page is fully interactive; nav links live. See **C-2**. |
| **confirmation failed but payment succeeded** | checkout 4xx/5xx/timeout | A toast: "Payment succeeded, but we couldn't finish your booking. Please contact support." (`checkout-shell.tsx:183`) and then the customer is stranded — no payment id on screen, no retry, no recovery page. |
| **payment status unknown** | callback lost, tab closed | Does not exist anywhere. |
| **timed out** | nothing passes `timeout` to Razorpay | Modal can sit open indefinitely. |
| **offline / reconnected** | network drop | No detection; the 30 s `AbortSignal.timeout` surfaces as a generic network error. |
| **resumable attempt** | refresh mid-payment | Nothing persisted; order id lives only in a closure. |

---

## 4. Latency sources

### 4.1 Backend — `POST /customers/cart/checkout`

This is the request the customer waits on **after being charged**. Counted round
trips, in order, all sequential:

| # | Operation | File | Necessary? |
|---|---|---|---|
| 1–2 | `verify_token` profile read, then `get_current_user` profile read — **same row, twice** | `core/auth.py:163`, `core/auth.py:515` | one is redundant (**M-1**) |
| 3 | `get_cart` | `customer_service.py:49` | yes |
| 4 | `salons` select (`accepting_bookings`, `is_active`) | `customer_service.py:575` | yes |
| 5 | `system_config` → `convenience_fee_percentage` | `customer_service.py:613` | **dead** when pinned pricing is used (**M-2**) |
| 6 | `bookings` idempotency by `razorpay_payment_id` | `customer_service.py:637` | yes |
| 7–8 | `razorpay_key_id` + `razorpay_key_secret` config reads (each Fernet-decrypted) | `payment_service.py:50` via `payment.py:35` | yes, once |
| 9 | **`razorpay.client.order.fetch()` — sync HTTP to Razorpay** | `customer_service.py:671` | **avoidable** (**H-2**) |
| 10–11 | `razorpay_key_id` + `razorpay_key_secret` **again** — a second `PaymentService` is constructed at `customer_service.py:733`, so `_initialize_razorpay`'s `self._razorpay_initialized` guard is useless | `customer_service.py:733` | **redundant** (**H-3**) |
| 12 | `bookings` idempotency by `razorpay_payment_id` — **again** | `booking_service.py:166` | **duplicate of #6** (**M-3**) |
| 13 | `profiles` customer read | `booking_service.py:663` | yes (email) |
| 14 | `salons` read — **again**, different columns | `booking_service.py:741` | **duplicate of #4** (**M-4**) |
| 15 | `profiles` vendor email read | `booking_service.py:758` | could join into #14 |
| 16 | `services` batch read | `booking_service.py:796` | yes |
| 17 | `system_config` → `convenience_fee_percentage` — **again** (and with `is_active=True`, which #5 omits) | `booking_service.py:254` | **duplicate of #5** (**M-2**) |
| 18 | `bookings` INSERT | `booking_service.py:355` | yes |
| 19 | `redeem_coupon` RPC | `booking_service.py:383` | yes, when couponed |
| 20 | `payments` INSERT (convenience fee) | `booking_service.py:419` | yes |
| 21 | `payments` INSERT (service payment) | `booking_service.py:439` | yes |
| 22 | **Resend API — customer email** | `booking_service.py:448` | **not required for the response** (**C-1**) |
| 23 | `activity_logs` INSERT (email success log) | `email.py:204` | no |
| 24 | **Resend API — vendor email** | `booking_service.py:475` | **not required for the response** (**C-1**) |
| 25 | `activity_logs` INSERT | `email.py:204` | no |
| 26–27 | `clear_cart` (select + delete) | `customer_service.py:783` | yes |

**≈27 sequential round trips, of which ~8 are provably redundant and 3 are
external** (1 × Razorpay, 2 × Resend).

Worst case on the email path alone: `_send_email` retries up to 4 times
(`max_retries=3`, `email.py:163`) with 15 s HTTP timeout (`RESEND_TIMEOUT_SECONDS = 15`,
`email.py:25`) and 1 s/2 s/4 s backoff — **up to ~67 s per email, ~134 s for both**,
all inside the customer's checkout request. This is finding **C-1** and it is the
most expensive thing in the codebase.

### 4.2 Backend — the event loop is blocked for all of it

`get_db()` returns the **synchronous** supabase client
(`core/database.py:66`, `create_client` from `supabase`), and every service calls
`.execute()` directly inside `async def`. The same is true of
`razorpay.Client` (plain `requests`). Nothing is wrapped in
`run_in_threadpool`.

So each of the ~27 round trips above blocks the **entire** event loop, not just
this request. One customer checking out stalls every other request on that worker
for the full duration. This is finding **C-4** and it makes every other latency
number worse under load.

*(Fixed for the payment path in Phase 3 — §15. Every query there now goes through
`db_exec`, which awaits `.execute()` in the threadpool. The rest of the backend
still blocks; see §15's "still outstanding".)*

### 4.3 Backend — `POST /payments/cart/create-order`

≈10 sequential round trips (auth ×2, creds ×2, `cart_items`, `system_config`,
coupon validation up to ×3 at `coupon_service.py:89/127/145`, Razorpay
`orders.create`). The customer is staring at a disabled Pay button for all of it.
Credential reads and the cart/config reads are independent and could be
concurrent (**M-5**).

### 4.4 Frontend — SDK load is serial with order creation

All three shells do the two slowest independent things one after the other:

```ts
await loadRazorpayScript();                      // checkout-shell.tsx:202   ~200–800 ms cold
const order = await createOrder.mutateAsync(...) // checkout-shell.tsx:204   ~500–1500 ms
```

- `checkout-shell.tsx:202-204` — script, then order.
- `payment-shell.tsx:106-107` — script, then order.
- `checkout-products-shell.tsx:133-145` — order, then script (same cost, reversed).

Nothing about `checkout.js` depends on the order, and loading it initiates no
payment. This is **H-1**: the cheapest real win in the audit.

### 4.5 Mobile — WebView re-downloads the SDK every attempt

`RazorpayCheckout` renders a `WebView` with inline HTML whose `<head>` has a
blocking `<script src="https://checkout.razorpay.com/v1/checkout.js">`
(`RazorpayCheckout.tsx:31`). The WebView mounts only when `visible` flips true, so
the fetch starts *after* the tap, and remounts on each retry. **M-6.**

### 4.6 Artificial delays

- `SUCCESS_REDIRECT_DELAY_MS = 2000` — a hard 2 s wait on a success screen the
  vendor has already read (`payment-shell.tsx:20,86-89`). **M-7.**
- Email backoff sleeps inside the request (covered by C-1).

### Necessary vs unnecessary waiting

| Must wait | Must not wait |
|---|---|
| Razorpay `orders.create` (need a real `order_id`) | `checkout.js` download (parallelize / preload) |
| Signature verification — local HMAC, no network, cheap | Razorpay `orders.fetch` (store the snapshot ourselves) |
| Cart re-validation before recording a booking | Both confirmation emails |
| `bookings` INSERT + the two `payments` INSERTs | Duplicate config / salon / profile / idempotency reads |
| Coupon redemption (usage limits) | `activity_logs` writes |
| `clear_cart` | The 2 s vendor success delay |

---

## 5. Back / cancel / refresh / interrupt behaviour

| Interruption | Web service checkout | Web vendor payment | Mobile |
|---|---|---|---|
| Back **before** modal opens | Link/back works; `createOrder` continues, result discarded. Orphan Razorpay order (harmless, never paid). | same | `goBack()` works, same |
| Back **while modal open** | Razorpay owns a full-screen overlay; browser back closes it → `ondismiss` fires → `processing` cleared (`checkout-shell.tsx:223`). Correct. | same (`payment-shell.tsx:126`) | `Modal onRequestClose` → `onDismiss`. Correct. |
| Back **while confirming** (post-charge) | **Nothing prevents it.** "Back to Cart" link and browser back are live. Unmount does not abort the POST, so the booking is created, but `saveBookingConfirmation` and the redirect never run. Customer is charged and sees no confirmation. **C-2** | Guarded — `ProcessingStep` replaces the page (`payment-shell.tsx:68`) | **Nothing prevents it** — header back button is live during `isCheckingOut`. **C-2** |
| **Refresh while modal open** | Razorpay order abandoned; order id lost. Retry creates a new order. Safe, slightly wasteful. | same | n/a |
| **Refresh while confirming** (post-charge) | `razorpay_payment_id` existed only in a closure → gone. Backend most likely completes the booking anyway (uvicorn does not cancel the handler on disconnect), so the booking exists, but the customer has no way to know. **C-2** | same risk | n/a |
| **Close tab right after paying** | Callback never fires → **no booking, money taken, no webhook, no reconciliation.** Only Razorpay's dashboard knows. **C-3** | Payment row stays `pending` forever | same |
| Lose connectivity mid-confirm | `AbortSignal.timeout(30_000)` (`http.ts:23,120`) → `ApiError.network` → "contact support" toast | same | no timeout configured at all in the mobile client |
| Regain connectivity | No resume, no retry, no detection | — | — |
| Cancel then immediately retry | New `create-order` → brand-new Razorpay order. Previous order abandoned. Correct. | Previous `vendor_registration_payments` row is marked `failed` first (`payment_service.py:397`). Correct. | same as web |
| Click Pay twice | `canProceed` requires `!busy`, `processing` set synchronously before any await — React cannot deliver a second click in the same tick. Safe. | `disabled={processing}` — safe | `disabled={busy}` — safe |

---

## 6. Frontend ↔ backend consistency

**Source of truth.** Razorpay is the source of truth for *whether money moved*;
our DB is the source of truth for *what it bought*. The link between them is the
HMAC signature, verified locally (`payment.py:176`). That part is sound.

**What is verified.** Signature only. We never call Razorpay to confirm the
payment's `status` or `amount` — so a valid signature on an order we created is
accepted as proof of capture. In practice Razorpay only signs captured payments,
so this is acceptable, **but** it means auto-capture must be ON in the Razorpay
dashboard. If it is set to manual, we mark bookings paid for *authorized*
payments that are never captured. **Verify this in the dashboard** — it is a
configuration assumption the code does not state (**H-4**).

**Pinned pricing — a genuinely good design.** The priced breakdown is written
into the Razorpay order's `notes` at order-create time (`payment_service.py:268-301`)
and read back at checkout (`customer_service.py:679-684`), so what is *recorded*
equals what was *charged* even if prices/coupons change in between. Keep this.
The weakness is only *where* it is stored (see H-2) — Razorpay's `notes` is a
remote key-value store we pay a round trip to read, and its values are capped at
15 fields / 256 chars each.

**Fail-open on snapshot read.** If `orders.fetch` errors, the `except` at
`customer_service.py:722-726` logs "Cart validation skipped" and continues to a
fresh recompute. Cart tampering is still caught (that branch raises 400 inside the
`try` and is re-raised at :720), but the *amount recorded* may then diverge from
the amount charged. Acceptable trade-off, worth a metric (**M-8**).

**Duplicate requests.**
- Flow A: safe. Both `checkout_cart` (`customer_service.py:637`) and
  `create_booking` (`booking_service.py:166`) short-circuit on an existing
  `razorpay_payment_id`, and migration `20260122000000_add_razorpay_payment_id_idempotency.sql`
  backs it with a constraint. Two checks is one too many (M-3), not a bug.
- Flow C: safe — optimistic `UPDATE ... WHERE status='pending'`
  (`payment_service.py:519-540`) with an idempotent re-read.
- Flow B: `verify_payment` is a plain UPDATE keyed on `razorpay_order_id`
  (`product_order_service.py:229`) — idempotent by construction, though it will
  happily re-mark a `cancelled` order as `paid`.

**The proxy replays non-idempotent POSTs.** `api/backend/[...path]/route.ts:159-161`
retries the request once after a token refresh. For `/customers/cart/checkout`
the idempotency guard saves us. For `/payments/cart/create-order` and
`/product-orders/create` a replay creates a **second** Razorpay order (and, for
products, a second DB order row). Not a money bug; is a data-hygiene bug (**M-9**).

**Stale state overwriting newer state.** The success callback closes over
`cart`, `selectedDate`, `selectedTimes`, `totals` at click time
(`checkout-shell.tsx:220`) — which is deliberately *correct*: it records what was
actually paid for. Nothing in the flow lets an older attempt's response overwrite
a newer one, because there is only ever one in-flight attempt per mount.

---

## 7. Race conditions

| Race | Verdict |
|---|---|
| Cancel while `create-order` in flight | Benign — orphan Razorpay order, never paid. |
| Retry while previous payment still confirming | Cannot reach it: `busy` covers `checkoutCart.isPending`, and the only entry point is the disabled button. |
| Success callback arrives after `ondismiss` | **Real.** Razorpay fires `ondismiss` when its modal closes after a successful payment in some flows. `ondismiss` runs `setProcessing(false)` + "Payment cancelled" toast (`checkout-shell.tsx:223-226`); `handler` runs `handlePaymentSuccess`. There is no flag marking "payment already succeeded", so the customer can see **"Payment cancelled"** while the booking is in fact being created. **H-5** — UX only, no data corruption. |
| Failure callback after success | Web has no `payment.failed` listener, so unreachable. Mobile's `onError` only closes the modal. |
| Status checks returning out of order | N/A — no polling anywhere. |
| Component unmounts mid-request | **Real.** No mutation is aborted; `saveBookingConfirmation`/`navigate` never run. Part of **C-2**. |
| Cart modified in another tab between order and checkout | Caught — snapshot comparison includes service ids, quantities **and** unit prices (`customer_service.py:701-717`). Good. |
| Webhook vs callback | Was N/A — no webhook (**C-3**). Now real, and handled: whichever arrives first creates the booking, and the other finds it via the `razorpay_payment_id` idempotency check, which Phase 2 moved to the top of `checkout_cart` so an empty cart cannot mask it (§14). |
| Payment succeeds but booking INSERT fails | Customer charged, no booking, 500 returned. No compensating action, no refund, no record outside Razorpay. **C-3** again. |
| Booking created but coupon redemption fails | Deliberately tolerated and logged (`booking_service.py:390-394`), documented as D2. Correct call. |
| Booking created but `payments` INSERT fails | Swallowed and logged (`booking_service.py:421-423`, `:441-443`). Booking is correct; the payments ledger silently loses a row. **M-10.** |
| Two concurrent `vendor/registration/verify` | Safe (optimistic update). |

---

## 8. Potential bugs

### C-5 — Product order totals trust a client-supplied discount

`app/api/product_orders.py:20`
```python
class CreateOrderRequest(BaseModel):
    shipping_address: Dict[str, Any]
    discount_total: float = 0.0        # <- straight from the client, unvalidated
    items: List[OrderItemSchema]
```
`app/services/product_order_service.py:74-78`
```python
discount_total = order_data.get('discount_total', 0.0)
total_amount = subtotal - discount_total
if total_amount < 1:
    total_amount = 1.0
```

`subtotal` is carefully recomputed server-side from the products table to stop
price tampering (`product_order_service.py:60`, and the comment at
`product_orders.py:13` says exactly that) — and then an arbitrary client number is
subtracted from it.

**Any authenticated user can buy any product order for ₹1** by posting
`{"discount_total": 999999}`. A negative value inflates the charge instead.
There is **no coupon flow for product orders at all** (confirmed:
`lib/api/orders.ts:25` sends a hard-coded `0`, mobile `useProductsAPI.ts:286`
sends `0`, the SPA sent `0.0`) — so this field has no legitimate caller.

`tests/test_product_order_mocked.py:314` (`test_create_order_applies_discount_total`)
asserts the vulnerable behaviour, so it must be rewritten, not just deleted.

**Severity: Critical. Affects: security + correctness. Confirmed by reading, not run against a server.**

### H-6 — Vendor pays, salon never activates, and verify can never fix it

`payment_service.py:452-609`. The payment row is flipped to `success` **before**
the salon lookup. If the salon row does not exist yet (`salon_response.data`
empty at `:558`), the method returns success with `vendor_request_id` and no
`salon_id` — the salon is never activated. Every later `verify` call hits the
idempotency branch at `:506` and returns early, so activation can never be retried.
`create-order` then refuses with 400 ("Registration fee already paid",
`:383-387`), so the vendor is **hard-stuck: paid, inactive, no self-service path**.

Given [[salon-approval-email-bug]] (pincode `varchar(6)` vs `varchar(10)` breaking
salon creation at approval time), this is not hypothetical — that is exactly the
condition that leaves an approved request with no salon row.

**Severity: High. Affects: correctness + UX.**

### M-11 — Production can silently enter payment simulation mode

`product_order_service.py:29-33` treats placeholder/missing Razorpay credentials
as `is_dev_mode`, and `create_order` then returns a fake `dev_order_…` id. In
production the frontend's `dev_mode` branch calls `/product-orders/dev-verify`,
which correctly 403s (`product_orders.py:76`) and is also blocked at the proxy
(`route.ts:54,73`). So nothing can be marked paid for free — **but** the customer
gets an unexplained failure, and we have a DB order row pointing at a Razorpay
order that does not exist. Given [[vercel-prod-env-vars]] notes placeholder
Razorpay ids already sitting in production config, this is worth an explicit
production guard (503 "payments not configured") instead of a silent simulation.

### M-12 — Mobile WebView can hang forever on a slow SDK

`RazorpayCheckout.tsx:103-108` sets `startInLoadingState` + `renderLoading` with no
`onError`, no `onHttpError`, and no timeout. If `checkout.js` *fails*, the inline
script's `try/catch` posts an error (`:58-60`) — good. If it merely *hangs* (slow
or captive-portal network), the inline script never executes, nothing posts, and
the user watches a spinner with only the ✕ to escape.

### M-13 — Uncleaned timer in the vendor success path

`payment-shell.tsx:86` sets a 2 s `setTimeout` that calls `navigate` and `notify`
with no cleanup. Unmounting inside that window fires a navigation from a dead
component.

### L-1 — Signature stored in the database

`payment_service.py:521` persists `razorpay_signature`. It is a one-time HMAC over
ids we already store, so this is not a secret leak, but it is dead data in two
tables (`vendor_registration_payments`, `payments`).

### L-2 — Product orders abandoned at `pending` forever

`product_order_service.py:117-130` inserts the order before payment and nothing
ever reaps it. The orders list shows the customer stale "pending" orders they
never paid for.

---

## 9. Security / correctness concerns

| # | Concern | Severity |
|---|---|---|
| **C-5** | Client-controlled `discount_total` ⇒ ₹1 product orders (above) | Critical |
| **C-6** | **Mobile: HTML injection into the payment WebView.** `esc()` strips only `"` and `\` (`RazorpayCheckout.tsx:24`), then interpolates into a `<script>` block. `prefill.name/email/contact` come from the user's own profile. A `full_name` containing `</script><script>…` escapes the string **and** the script element, executing attacker-chosen JS in the page that renders the Razorpay checkout. Self-XSS in the normal case, but the profile name is also settable by admins/RMs on another user's behalf, and the blast radius is the payment surface. Fix: `JSON.stringify` each value (which also fixes newline-induced syntax errors). | Critical |
| **C-3** | **No webhook, no reconciliation.** A lost browser callback = captured payment with no booking and no record outside Razorpay's dashboard. Nothing detects it; nothing refunds it. *(Fixed in Phase 2 — §14. Needs the migration applied and the dashboard configured to take effect.)* | Critical |
| **H-4** | Capture mode is an unstated assumption — signature is accepted as proof of capture without checking `payment.status`. Verify auto-capture is ON in the dashboard. | High |
| **M-9** | Proxy replays non-idempotent POSTs after token refresh | Medium |
| — | **Good:** price/amount are always recomputed server-side for services; cart snapshot comparison includes unit prices; coupon limits enforced centrally in `PricingService`; credentials encrypted at rest and never in the response except the public `key_id`; the browser never holds a token. | — |

---

## 10. Recommended architecture

### 10.1 Backend: split the post-payment request at the durability line

Everything in `/customers/cart/checkout` falls into one of two groups:

**Must complete before we answer** (the customer's money depends on it):
verify signature → validate cart → INSERT booking → INSERT payments → redeem
coupon → clear cart.

**Must happen, but not before we answer:** both emails, both activity logs.

Move group 2 behind `BackgroundTasks` (FastAPI already injects it; no queue, no new
infrastructure). Target: **~8 round trips, no external calls, sub-300 ms.**

### 10.2 Backend: pin the snapshot in our own database

Replace `notes["pricing"]`/`notes["cart_snapshot"]` with a row in our own table
(`payment_intents`, or reuse `payments` with `status='pending'`) written at
order-create time. Then checkout reads it in the same query round as everything
else and the Razorpay `orders.fetch` disappears entirely. Keeps the pinned-pricing
guarantee; removes an external round trip from the post-charge path. *(Needs a
migration — stage it after the no-migration fixes.)*

### 10.3 Backend: one `PaymentService` per request

Construct it once in `checkout_cart` and pass it down, so `_initialize_razorpay`'s
existing `_razorpay_initialized` guard actually guards something. Add a
process-level TTL cache (60 s) for the two Razorpay credential reads and
`convenience_fee_percentage` — the docstring at `payment_service.py:12-15` claims
"no caching so changes take effect immediately", which is a defensible policy for
credentials but costs 4 decrypted round trips per checkout. A 60 s TTL keeps the
spirit and removes the cost.

### 10.4 Backend: stop blocking the event loop

Two options, in order of preference:

1. Wrap `.execute()` calls through a single helper that runs them in the
   threadpool, OR
2. Make the service-layer methods `def` instead of `async def` so FastAPI runs
   them in its threadpool automatically.

Option 2 is a large mechanical change; option 1 can be introduced incrementally
starting with the payment path. **This is the highest-leverage backend change and
also the riskiest — it should be its own PR, after the rest.**

### 10.5 Frontend: one `usePaymentFlow` state machine

Replace the OR-ed booleans in all three shells with one reducer shared between
them:

```
idle → preparing → awaiting_customer → confirming → confirmed
                          ↓                 ↓
                      cancelled         confirmation_failed
                          ↓                 ↓
                        idle            (recovery: payment id on screen + Retry)
                       failed
```

Required of the machine:

- `confirming` renders a **blocking, non-dismissable** overlay and registers a
  `beforeunload` guard. Nothing may navigate away between charge and confirmation.
- A terminal `succeeded` flag that makes `ondismiss` a no-op once `handler` has
  fired (fixes **H-5**).
- `confirmation_failed` keeps `razorpay_payment_id` + `razorpay_order_id` on
  screen and offers **Retry** — the backend's idempotency guard makes retry free
  and safe, and this converts the current dead end into a self-service recovery.
- Persist the in-flight attempt (payment id, order id, booking inputs) to
  `sessionStorage` on `confirming`, clear it on `confirmed`. On mount, if a stale
  attempt exists, retry the confirmation. This closes the refresh-mid-confirm hole
  without any backend change.

### 10.6 Frontend: preload the SDK

`loadRazorpayScript()` on checkout mount (idempotent already — `razorpay.ts:46-47`
short-circuits on `window.Razorpay`), plus
`<link rel="preconnect" href="https://checkout.razorpay.com">`. Loading the script
initiates nothing; by click time it is warm. Keep the `await` in the handler as a
safety net.

### 10.7 The only real fix for C-3: reconciliation

Pick one (not both, for now):

- **Webhook** (`payment.captured`): re-add the endpoint the June cleanup removed,
  signature-verified against `razorpay_webhook_secret` (the config key still
  exists), and have it complete the booking from the pinned snapshot in 10.2.
  This is the correct fix and makes the browser callback a mere optimisation.
- **Sweeper**: a scheduled job listing Razorpay payments captured in the last N
  hours with no matching booking, and alerting. Cheaper, detects rather than
  fixes.

Recommendation: the webhook, *after* 10.2 lands — the snapshot-in-our-DB work is
what makes the webhook able to complete a booking without the browser.

---

## 11. Prioritized fixes

### Phase 0 — ship now, no migration, no architecture change ✅ DONE

| # | Fix | Files | Impact |
|---|---|---|---|
| **C-5** | Drop `discount_total` from `CreateOrderRequest`; compute totals server-side only. Rewrite `test_create_order_applies_discount_total`. | `api/product_orders.py`, `services/product_order_service.py`, `tests/test_product_order_mocked.py` | security |
| **C-6** | `JSON.stringify` every interpolated value in `buildHtml`; delete `esc()`. | `RazorpayCheckout.tsx` | security |
| **C-1** | Move both booking emails to `BackgroundTasks`. | `booking_service.py`, `api/customers.py` | **latency: removes up to ~134 s worst case, ~1–3 s typical, from the post-charge wait** |
| **C-2** | Blocking overlay + `beforeunload` during `confirming`; same on mobile (disable the header back button while `isCheckingOut`). | `checkout-shell.tsx`, `checkout-products-shell.tsx`, `CheckoutScreen.tsx` | correctness/UX |
| **H-1** | Preload `checkout.js` on mount; `preconnect`. | 3 shells, `razorpay.ts` | latency: ~200–800 ms off every first payment |
| **H-5** | `succeeded` flag so `ondismiss` cannot say "Payment cancelled" after a success. | 3 shells | UX |
| **H-6** | Activate the salon **before** flipping the payment row to `success`; if the salon is missing, leave the row `pending` with a reason so verify can retry. | `payment_service.py` | correctness |
| **M-7** | Delete the 2 s success delay. | `payment-shell.tsx` | latency |
| **M-13** | Clean up the `setTimeout`. | `payment-shell.tsx` | correctness |
| **M-12** | WebView `onError`/`onHttpError` + a load timeout. | `RazorpayCheckout.tsx` | UX |

### Phase 1 — deduplicate the backend path (no migration) ✅ DONE

| # | Fix | Impact |
|---|---|---|
| **H-3** | One `PaymentService` per request. | −2 round trips |
| **M-1** | Merge `verify_token`'s profile read with `get_current_user`'s. | −1 round trip on **every** authenticated request |
| **M-2, M-3, M-4** | Pass the already-fetched salon, config and idempotency result into `create_booking`. | −3 round trips |
| ~~**M-5**~~ | ~~`asyncio.gather` the independent reads in `create-order`.~~ **Not done — see §13.** | nil as written |
| 10.3 | 60 s TTL cache for credentials + fee config. | −2 to −4 round trips |
| **M-10** | Make the two `payments` INSERTs part of the booking's failure path, or log to a durable retry table. | ledger integrity |

Expected after Phase 0+1: **~27 → ~10 round trips, no external calls in the
post-charge path.** Measured: **8 DB round trips before the response**, plus the
two auth reads and the one remaining Razorpay `orders.fetch` (H-2, Phase 2). See §13.

### Phase 2 — needs a migration ✅ DONE (except L-2)

| # | Fix | Status |
|---|---|---|
| **H-2** | `payment_intents` table; drop the Razorpay `orders.fetch`. | done — §14 |
| **C-3** | Re-add the signature-verified `payment.captured` webhook, completing bookings from the intent row. | done — §14 |
| **L-2** | Reap abandoned `pending` product orders. | **deferred by choice** — nothing in the backend schedules work, so this needs a trigger mechanism decided first (admin endpoint, expire-on-read, or `pg_cron`). Lowest severity in the audit. |

### Phase 3 — its own PR, highest risk ✅ DONE (payment path)

| # | Fix | Status |
|---|---|---|
| **C-4** | Stop blocking the event loop (threadpool wrapper for `.execute()` and the Razorpay client). | done for the payment path — §15 |

### Also do, outside the code

- **H-4**: confirm auto-capture is ON in the Razorpay dashboard.
- **M-11**: make production refuse to start a payment on placeholder credentials.
- **M-9**: consider restricting the proxy's 401-retry to idempotent methods, or
  passing an idempotency key on `create-order`.
- Set `maxDuration` explicitly on the proxy route — nothing does today
  (`route.ts` exports no config), so the platform default (10–15 s) can kill a
  slow checkout *after* the charge and before the booking is returned, producing
  exactly the "Payment succeeded, but we couldn't finish your booking" message for
  a booking that in fact exists. Phase 0's **C-1** removes the main cause.

---

## Smallest safe set, if only one phase ships

**Phase 0.** It contains both security holes, both stuck-state bugs, the single
largest latency win (emails out of the request), and the cheapest one
(SDK preload) — and none of it touches the database schema, the pinned-pricing
guarantee, the signature verification, or the idempotency guards.

---

## 12. Phase 0 — what actually shipped (2026-10-05)

Every Phase 0 row above is implemented on `dev`. No migration. Gates: backend
**767 passed / 26 skipped**, web **679 passed / 104 files**, both typechecks
clean, no new lint. Mobile has no test harness ([[module-by-module-audit]]), so
`tsc --noEmit` is its only gate and it is clean.

### Beyond the listed rows

Five things were added that the table did not call for. Each is noted here so
the diff is not surprising:

1. **Retry instead of a dead end.** C-2 only covered the window *before* the
   failure; the failure itself still ended at a "contact support" toast with the
   payment id trapped in a closure. Both web checkouts now render
   `ConfirmationRecovery` (shared, in `components/payment/confirming-overlay.tsx`)
   with the payment and order ids on screen and a Retry button; mobile offers
   Retry in the alert. Safe because both confirmation endpoints are idempotent on
   the Razorpay ids — a retry either records the booking/order or returns the one
   that already exists.
2. **The vendor registration receipt email** also moved to `BackgroundTasks`. Not
   in the C-1 row, but it is the same defect (an awaited Resend call after the
   vendor has been charged) on the same endpoint being changed for H-6.
3. **`activated` on `VendorRegistrationVerificationResponse`.** H-6's server fix
   is pointless if the client still reports an active account on `success` alone
   and redirects into a gate that bounces back. `activated: false` drives a new
   `pending_activation` step in `payment-shell.tsx`.
4. **`maybe_single()` added to `test_payment_mocked.py`'s fake DB.** The fake
   lacked it although production code already relies on it elsewhere
   (`core/auth.py`, `cancel_booking`). Four tests 500'd without it.
5. **`src/types/api.ts` regenerated** from the live schema (dumped offline via
   `app.openapi()`, then `openapi-typescript`) rather than hand-edited. The diff
   is only the three changes above, which confirms the committed types had not
   drifted.

### One decision the tests forced

`_finish_vendor_registration` short-circuits on `payment_data["salon_id"]` being
set, rather than re-running the lookup on every repeat verify.
`test_registration_verify_idempotent_when_already_success` made the case: a
linked `salon_id` *is* the proof that activation already happened, so a repeat
verify should answer from the payment row alone. The retry path is reached only
when that column is null — which is exactly the stuck state H-6 describes, and
is now covered by `test_registration_verify_retries_activation_when_salon_was_missing`.

### Still outstanding from Phase 0's surrounding notes

- **Not done: `maxDuration` on the proxy route.** It is one line, but picking the
  number is a cost decision on Vercel, so it is left for a human. C-1 removes the
  main reason the default was being hit.
- **Not done: a browser pass on the web changes.** The overlay, the
  `beforeunload` guard and the `ondismiss` suppression cannot be verified by
  typecheck or by this repo's test conventions (shells are not unit-tested; only
  pure `_lib` helpers are). Per the lesson recorded in [[nextjs-perf-plan]], these
  need throttled Playwright against a real deployment, not localhost.
- **Unchanged: H-4.** Still an unverified dashboard assumption.

---

## 13. Phase 1 — what actually shipped (2026-10-05)

Backend only; no migration, no frontend change. Gates: backend **807 passed /
26 skipped** (was 767/26 — 40 new tests), `ruff check app/ tests/` at **43
findings, one below the pre-existing 44** baseline. The 26 skips are the
integration tier, which needs a local Supabase stack (Docker is not running
here); CI runs it on the PR to `main`.

### The round-trip count, measured

The §4.1 table was counted by reading. This one was counted by running: the
in-memory fake in `tests/test_customer_mocked.py` now logs every `.execute()`,
so the sequence below is observed, not estimated.

`POST /customers/cart/checkout`, before the response:

| # | Operation |
|---|---|
| 1 | `cart_items` select (`get_cart`) |
| 2 | `salons` select |
| 3 | `system_config` select (fee percentage — cache miss only) |
| 4 | `bookings` select (idempotency) |
| 5 | `services` batch select |
| 6 | `bookings` INSERT |
| 7 | `payments` INSERT (both ledger rows, one statement) |
| 8 | `cart_items` DELETE |

Plus, outside that count: **2** auth round trips (`profiles` + `token_blacklist`,
down from 3) and **1** external Razorpay `orders.fetch`, which is H-2 and stays
until Phase 2. On a warm config cache the two Razorpay credential reads cost
nothing; cold, they add two.

Moved to *after* the response: both `profiles` reads, both Resend calls, both
`activity_logs` writes.

So: **~27 sequential round trips with 3 external calls → 11 with 1**, and the
post-charge path no longer contains an email, an activity log, or a single
duplicated read. `test_checkout_makes_eight_round_trips_before_responding` is an
exact budget, so putting a read back has to be a decision.

### How each row was done

- **10.3** — `ConfigService` gained a process-level TTL cache
  (`CONFIG_CACHE_TTL_SECONDS = 60`) over exactly three keys: the two Razorpay
  credentials and `convenience_fee_percentage`. Two properties make it safe, and
  both are tested: every write through `ConfigService` drops the key, so an admin
  edit still applies on the next request (the docstring's "changes take effect
  immediately" survives for changes made through our own API); and a `None` is
  never cached, so one transient DB error cannot become a minute of "payment
  service is not configured".
- **H-3** — `checkout_cart` builds one `PaymentService` and uses it for both the
  order fetch and the signature verification, so `_razorpay_initialized` finally
  guards something.
- **M-1** — `verify_token` already had to read the profile (deleted account,
  inactive account, `token_valid_after`). It now selects the union of its own
  columns and `get_current_user`'s, and returns the row on `TokenPayload.profile`.
  `get_current_user` and `get_optional_user` use it, with a fallback read for any
  caller that builds a `TokenPayload` elsewhere. `is_internal` still comes from
  the row per request, not from a JWT claim — that was the point of reading it
  there, and there is a test for it.
- **M-2, M-3, M-4** — `create_booking` takes `salon_data`,
  `convenience_fee_percentage` and `idempotency_checked`. All three are optional,
  so direct callers (and the integration tests) behave exactly as before.
  `checkout_cart`'s salon select now takes the union of both column sets.
- **M-10** — the two ledger rows go in as one multi-row INSERT: one statement,
  so they cannot land half-written, and one round trip instead of two. A failure
  still does not fail a paid booking, but it is now a single ERROR naming the
  booking and both amounts — enough to replay by hand and enough for a Better
  Stack alert ([[betterstack-observability]]).

### Beyond the listed rows

1. **The two profile reads moved behind the response.** The audit marked the
   customer profile read "yes (email)" and the vendor email "could join into
   #14". Neither is needed by the booking at all — only by the two confirmation
   emails, which Phase 0 had already deferred. `_send_booking_created_emails`
   now resolves both itself, and `_get_salon_details` no longer fetches the
   vendor email. −2 from the post-charge path.
2. **`clear_cart` went from two round trips to one.** It ran a `count="exact"`
   select purely to report `deleted_count`, then deleted. The DELETE already
   returns the rows it removed (`postgrest`'s default is
   `returning=representation`, and `cleanup_expired_tokens` in `core/auth.py`
   already relies on this), so the count comes from the delete. Also removes a
   race where an item added between the count and the delete was deleted but not
   counted.
3. **`/customers/cart/checkout` had no happy-path test at all** — only
   `test_checkout_empty_cart_400`. The single most important request in the
   system, the one the customer waits on after being charged, was covered
   nowhere. It now has eleven tests: pinned amounts recorded, cart cleared,
   ledger written, idempotent replay, cart-changed-since-payment rejected,
   fail-open when the order snapshot is unreadable, bad signature, salon not
   accepting bookings, missing fee config, and the two round-trip budgets.
4. **New test modules.** `tests/test_config_cache.py` (12 tests) and
   `tests/test_auth_profile_reads.py` (10 tests). The auth one drives the real
   dependency chain rather than the overridden `get_current_user` every other
   module uses, because a round-trip count is precisely what no behavioural test
   would notice losing.
5. **An autouse fixture clears the config cache between tests.** A
   process-level cache would otherwise serve one test's seeded fee to the next
   one's fake database. `seed_config` in `test_payment_mocked.py` also sets
   `is_active`, mirroring the real column's default.

### M-5 was not implemented, deliberately

The row asked for `asyncio.gather` over the independent reads in
`create-order`. It would do nothing, for two reasons, and writing it would have
produced code that looks like a concurrency win and is not one:

1. **There is no concurrency to gain.** `get_db()` returns the *synchronous*
   supabase client — verified, not assumed: `postgrest`'s
   `SyncSelectRequestBuilder.execute` is a plain method, not a coroutine.
   `asyncio.gather` over coroutines that each make a blocking call runs them one
   after another. Until **C-4** (Phase 3) puts those calls in a threadpool,
   `gather` buys exactly zero. This is the same finding as §4.2, applied to the
   proposed fix.
2. **There is almost nothing left to overlap.** After 10.3, `create-order` is
   one `cart_items` read, a cache-hit on the fee, and the Razorpay
   `orders.create` — measured by
   `test_cart_create_order_reads_the_cart_and_the_fee_once_each`. The ~10 round
   trips §4.3 counted are down to one DB read plus the one unavoidable external
   call.

**M-5 should be reconsidered as part of C-4, not before it.**

### One thing worth knowing about M-3

Skipping `create_booking`'s idempotency check does not widen any race.
`checkout_cart` and `create_booking` checked the same thing microseconds apart,
so two concurrent requests always passed *both* checks or neither; the unique
constraint from `20260122000000_add_razorpay_payment_id_idempotency.sql` was
always the actual guarantee, exactly as §6 says. In that (sub-millisecond) race
the loser now gets a 500 on an insert that violates the constraint — and Phase
0's Retry button turns that into a successful idempotent replay. Worth closing
properly when the webhook lands in Phase 2.

### Still outstanding

- Everything in §12's "still outstanding" list: the browser pass on Phase 0's
  web changes, `maxDuration` on the proxy route, and H-4.
- The integration tier has not run against a stack locally (no Docker here).
- **Phase 2 is now the next real work**, and H-2 is the last duplicated/external
  read in the post-charge path: pinning the snapshot in our own table removes the
  Razorpay `orders.fetch` *and* is what lets the C-3 webhook complete a booking
  without the browser. *(Done — §14.)*

---

## 14. Phase 2 — what actually shipped (2026-10-05)

H-2 and C-3, across the backend, the Next web app and the Expo app. L-2 was
deliberately left out (see the Phase 2 table above).

**Gates:** backend **849 passed / 26 skipped** (was 807/26 — 42 new tests),
`ruff check app/ tests/` at **43 findings, exactly the pre-existing baseline**,
web **679 passed / 104 files**, both web and mobile `tsc --noEmit` clean. The 26
skips are the integration tier, which needs a local Supabase stack.

**Not verified:** the migration has not been executed against any database —
Docker is not running here and nothing was pointed at a remote. Everything below
describes code that is tested against in-memory fakes, which by construction do
not enforce a single constraint in that migration.

### H-2 — the snapshot lives in our own table

New table `payment_intents`
(`supabase/migrations/20261005000000_create_payment_intents.sql`), written by
`PaymentService.create_cart_payment_order` and read by `checkout_cart`. It holds
the pinned priced breakdown, the cart snapshot, the coupon, the amount, and the
appointment the customer had chosen.

Three things improve at once, and the third is the reason Phase 2 exists at all:

1. **The external call is gone from the post-charge path.** Checkout reads the
   snapshot locally. `test_checkout_never_calls_razorpay_when_an_intent_exists`
   asserts Razorpay is not contacted.
2. **The snapshot can no longer truncate.** Razorpay caps a note value at 256
   characters, and `cart_snapshot` was a JSON blob in exactly such a note — a
   cart of four or five services was approaching it. `jsonb` has no such limit.
   The notes still carry the small scalars, which is what makes the Razorpay
   dashboard readable;
   `test_cart_create_order_no_longer_puts_the_snapshot_in_razorpay_notes` pins
   the split.
3. **A webhook can read it.** Which is C-3.

**The round-trip count changed shape, not size.** Before the response,
`/customers/cart/checkout` now makes **nine** local queries and **zero** external
calls, where Phase 1 made eight local and one external:

| # | Operation |
|---|---|
| 1 | `bookings` select (idempotency — **moved to first**, see below) |
| 2 | `cart_items` select (`get_cart`) |
| 3 | `salons` select |
| 4 | `system_config` select (fee percentage — cache miss only) |
| 5 | **`payment_intents` select** (was a Razorpay `orders.fetch`) |
| 6 | `services` batch select |
| 7 | `bookings` INSERT |
| 8 | `payments` INSERT (both ledger rows, one statement) |
| 9 | `cart_items` DELETE |

Trading an HTTPS round trip to Razorpay for a query alongside the other eight is
the entire point, so the budget test is renamed
`test_checkout_makes_nine_round_trips_before_responding` and now asserts the
exact *sequence*, not just the count. Closing the intent out (`status=completed`,
`booking_id`) is bookkeeping for reconciliation and runs after the response,
alongside the two profile reads the emails need.

**A deploy-window fallback exists and is temporary.** An order created before
this migration has its snapshot in the Razorpay notes and no intent row, so
`CustomerService._legacy_snapshot_from_razorpay_order` still reads the notes when
no intent is found. It is reached only for orders that predate the deploy (or one
whose intent insert failed), it never raises, and it is safe to delete once no
unpaid order predates the migration. Both paths are tested.

### C-3 — the webhook

`POST /api/v1/webhooks/razorpay` (`app/api/webhooks.py`,
`app/services/webhook_service.py`), handling `payment.captured` and
`payment.failed` for **all three flows**:

| The Razorpay order belongs to | What the webhook does |
|---|---|
| `payment_intents` | completes the cart booking from the pinned snapshot |
| `product_orders` | marks the order paid |
| `vendor_registration_payments` | records the fee and activates the salon |
| nothing | 200, and an ERROR log naming the payment — money with nothing to attach it to |

**Authentication is the HMAC and nothing else.** `X-Razorpay-Signature` is
checked with `hmac.compare_digest` against a SHA-256 HMAC over **the raw request
body bytes**, never a re-serialised copy. Nothing in the body is read before that
passes. `test_body_tampered_after_signing_is_rejected` is the test that matters
here.

**The status codes are instructions to Razorpay's retry machinery,** and are
asserted as such:

| Code | Meaning | Why |
|---|---|---|
| 200 | received (handled, or deliberately ignored) | an error on an event we do not act on would be redelivered forever |
| 400 | signature did not verify, or body is unparseable | not ours, or redelivering the same bytes cannot help |
| 503 | no webhook secret configured | **our** fault — retries keep the notification alive until someone sets it |
| 500 | we failed while handling a verified event | the only retry this path has |

The endpoint is `@limiter.exempt`: throttling it discards notifications about
money that has already moved.

### Four decisions worth knowing

1. **The appointment had to be pinned at order time, which is why the frontends
   changed.** A webhook has no browser and therefore no date or time slots — the
   customer picked them on the checkout page and only ever sent them *after*
   paying. `POST /payments/cart/create-order` now accepts optional
   `booking_date` / `time_slots`, `checkout-shell.tsx` and `CheckoutScreen.tsx`
   send what the customer already chose, and the intent stores them. Both fields
   are optional and neither is priced or validated; an older client still gets a
   working checkout, and `create_booking_from_intent` logs at ERROR with the
   payment id when it finds no appointment to book, because that is money needing
   a person.

2. **The idempotency check moved to the top of `checkout_cart`.** The webhook
   clears the paid cart items on its way through. With the cart read first, a
   browser callback arriving *after* the webhook was told "Cart is empty" — a
   failure message for a payment that worked, which is exactly what Phase 0's
   Retry button would then retry in vain. The payment-id lookup now runs before
   anything else, so an existing booking is returned whatever the cart looks
   like. `test_checkout_is_idempotent_even_with_an_empty_cart`.

3. **The webhook is deliberately more permissive about the salon than checkout
   is.** `checkout_cart` refuses a salon that is inactive or has stopped
   accepting bookings — correctly, because no money has moved yet. On the webhook
   path it already has, so the booking is recorded anyway and the discrepancy
   logged at WARNING for someone to cancel and refund. Dropping a paid booking on
   the floor is the worse failure.

4. **The webhook clears only the items that were paid for, not the whole cart.**
   `clear_cart` empties everything, which is right in the browser flow. Here the
   customer may have added something else while the webhook was in flight, and
   that is not ours to delete.

### The migration also relaxes one constraint

`payments.payment_online_requires_razorpay` demanded both `razorpay_payment_id`
**and** `razorpay_signature` on a successful `convenience_fee` row. A webhook has
no order|payment signature — its proof is an HMAC over the webhook body, a
different signature with a different meaning that does not belong in that column.
The constraint now requires the payment id alone, which is the whole of what it
was for ("never record an online platform fee as paid without a gateway
reference"); the signature was never read back after the in-process verification
that precedes the write, which is L-1.

**This matters for deploy order.** Until the migration is applied, the webhook's
`payments` INSERT violates that constraint. M-10 made that failure non-fatal, so
the symptom would be bookings created by the webhook with no ledger rows and an
ERROR in the log — recoverable, but not what anyone wants. Apply the migration
before pointing Razorpay at the endpoint.

### Deployment steps this needs (none of them done)

1. Apply `20261005000000_create_payment_intents.sql`.
2. Set `razorpay_webhook_secret` in system configuration — it is now in
   `AVAILABLE_SYSTEM_CONFIGS`, so the admin panel can set it, and it is encrypted
   like the other Razorpay secrets. Until it is set, the endpoint answers 503 and
   Razorpay keeps retrying.
3. Add the webhook in the Razorpay dashboard pointing at
   `https://<api-host>/api/v1/webhooks/razorpay`, subscribed to `payment.captured`
   and `payment.failed`, with that same secret.
4. Confirm end to end by paying and killing the browser before the callback
   returns — the booking should appear anyway. Nothing short of that exercises
   this path for real, and none of the tests above can.

### Still outstanding after Phase 2

- Everything in §12's and §13's outstanding lists, unchanged: the browser pass on
  the Phase 0 web changes, `maxDuration` on the proxy route, H-4 (auto-capture in
  the dashboard), and the integration tier.
- **L-2**, deferred with the trigger mechanism undecided.
- The webhook makes the sub-millisecond `create_booking` insert race from §13
  less interesting but does not close it; the unique constraint is still what
  guarantees it.
- **C-4 (Phase 3) is now the only phase left**, and it is the riskiest: every
  query above still blocks the whole event loop. M-5 should be reconsidered as
  part of it, never before. *(Done — §15.)*

---

## 15. Phase 3 — what actually shipped (2026-10-08)

C-4, for the payment path. Backend only; no migration, no frontend change, no
API change. Gates: backend **851 passed / 26 skipped** (was 849/26 — 2 new
tests), `ruff check app/ tests/` at **43 findings, exactly the pre-existing
baseline**, `python -c "from main import app"` boots 184 routes / 141 OpenAPI
paths.

### What was actually wrong

`get_db()` returns the **synchronous** supabase client, so `.execute()` is a
blocking call on `httpx.Client`. Called straight from `async def` — which is how
all 351 call sites in `app/` were written — it does not merely make *this*
request wait. It parks the whole event loop, so one customer's checkout froze
every other request on that worker for the duration.

That is not a theory. The negative control is in the commit: revert `db_exec` to
call `.execute()` inline and `test_checkout_leaves_the_event_loop_free_while_it_waits`
reports the heartbeat counter at `[0, 0, 0, 0, 0, 0, …]` — **zero ticks across
all twelve queries**. The loop did not run at all while a checkout was in
progress.

### The mechanism: one helper, `db_exec`

`app/core/database.py` gained:

```python
async def db_exec(query):
    return await run_in_threadpool(query.execute)
```

and every call site became `await db_exec(self.db.table(...).select(...).eq(...))`.
Only `.execute()` moves to the thread. Building the chain stays on the loop,
deliberately: it is pure object construction with no I/O, and it keeps
supabase-py's lazily-initialised `postgrest` property single-threaded, so the
one piece of shared mutable state in the client is never raced for.

Three library facts were verified rather than assumed, because the whole change
rests on them:

- `postgrest` 0.13.2's `SyncQueryRequestBuilder.execute` is a plain method, not
  a coroutine, and its body is a single `self.session.request(...)`.
- `self.session` is an `httpx.Client`, which is thread-safe, and each call builds
  its own request builder — so concurrent `db_exec` calls over the shared
  singleton share nothing mutable.
- `run_in_threadpool` passes anyio's `abandon_on_cancel=False`. **This one
  matters for money:** if the customer disconnects mid-write we still wait for
  the thread, rather than orphaning a half-applied booking insert with nothing
  awaiting its result.

Concurrency is bounded by anyio's default thread limiter (40). That is left at
the default on purpose: it is the backstop that stops a traffic spike opening
unbounded connections to PostgREST, and exceeding it queues requests instead of
blocking the loop — strictly better than the old behaviour at every load level.

### Scope — the payment path, 128 call sites

| File | Sites |
|---|---|
| `core/auth.py` | 9 |
| `services/customer_service.py` | 36 |
| `services/booking_service.py` | 15 |
| `services/payment_service.py` | 13 |
| `services/product_order_service.py` | 14 |
| `services/coupon_service.py` | 13 |
| `services/config_service.py` | 11 |
| `services/product_cart_service.py` | 10 |
| `services/payment_intent_service.py` | 3 |
| `services/activity_log_service.py` | 3 |
| `services/webhook_service.py` | 1 |

`core/auth.py` is in scope although it is not strictly payment code: it runs on
**every authenticated request**, so leaving its two round trips blocking would
have left the loop stalled on the way in to the very endpoints being fixed.
`activity_log_service.py` is in scope because §4.1's rows 23 and 25 are its
inserts — they run after the response now, but a background task that blocks the
loop still blocks it for everyone.

The rewrite was done by an AST script (exact node offsets for the receiver
expression, so multi-line chains and nested parens could not be mangled), not by
regex, and it refused to touch any call outside an `async def`. **The ten calls
it refused were the interesting part** — each was a synchronous function doing
I/O, and each had to be converted by hand along with its callers:

| Was sync, now async | Callers updated |
|---|---|
| `verify_token`, `verify_refresh_token`, `revoke_token`, `cleanup_expired_tokens` | `get_current_user`, `get_optional_user`, `auth_service` ×2, `core/tasks.py` |
| `CouponService.public_vendor_coupons_by_salon`, `public_platform_coupons` | `salon_service` ×2 |
| `CustomerService._get_existing_review` | ×2, same file |
| `PaymentIntentService._update` | `mark_captured`, `mark_completed`, `mark_failed` |

`cleanup_expired_tokens` is worth calling out: it is the periodic background
task, so it was blocking the loop of a live worker on a timer, for no request's
benefit at all.

### The Razorpay client, and the one call deliberately left alone

`razorpay.Client` is built on `requests`, so its calls block too.
`RazorpayService.create_order` is now `async` and awaits
`run_in_threadpool(self.client.order.create, …)`; the legacy `order.fetch` in
`_legacy_snapshot_from_razorpay_order` is wrapped the same way.

`verify_payment_signature` stays **synchronous, on purpose**: it makes no network
call. `utility.verify_payment_signature` is a local HMAC comparison, so there is
nothing to move off the loop and wrapping it would only add a thread hop to the
post-charge path. The docstring says so, so nobody "finishes the job" later.

### Two new tests, because the old ones could not see this

Every existing test passed before this change and after it. That is the problem:
C-4 is invisible to behavioural tests by construction — the response is
identical, only every *other* request suffers. So the fake DB in
`test_customer_mocked.py` now records `threading.get_ident()` per query
(index-aligned with the existing `queries` log), and:

1. **`test_checkout_runs_every_query_off_the_event_loop`** captures the loop's
   thread id by wrapping `checkout_cart`, then asserts no query ran on it.
   Names the offending queries on failure.
2. **`test_checkout_leaves_the_event_loop_free_while_it_waits`** is the claim
   stated as the thing a customer suffers. A heartbeat task yields in a tight
   loop; each query blocks for 20 ms in its worker thread and records the
   heartbeat's tick count. The assertion is that the count **advances** between
   the first query and the last — i.e. the loop kept running while the checkout
   waited. It asserts on direction, not duration, so it does not depend on the
   host's clock resolution or load.

Both were confirmed to fail against the pre-C-4 behaviour before being kept.

### M-5, reconsidered as the audit asked — and now worth doing

Phase 1 refused M-5 (`asyncio.gather` the independent reads) because `gather`
over a blocking sync client buys exactly zero. **Phase 3 removes that premise,
and it was re-measured rather than re-reasoned:**

```
4 x 100ms queries: serial 409ms, gathered 110ms   -> 3.7x
```

So the concurrency is real now. The opportunity is in `checkout_cart`, not
`create-order` where Phase 1 was looking. Of the nine pre-response queries, four
are mutually independent:

| Query | Depends on |
|---|---|
| `bookings` (idempotency) | the payment id, known at entry |
| `cart_items` | the customer id, known at entry |
| `system_config` (fee) | nothing |
| `payment_intents` | the order id, known at entry |
| `salons` | **the cart** (salon_id) |
| `services` | **the cart** (service ids) |

Gathering the first four would cut three round trips of wall time — perhaps
60–150 ms — off the request the customer waits on *after being charged*.

**It is not done here, and it is a decision rather than an oversight**, for three
reasons worth weighing:

1. It changes the behaviour of the most sensitive request in the system, which
   is not something to fold into a mechanical change as a bonus.
2. It makes the query *sequence* nondeterministic, so
   `test_checkout_makes_nine_round_trips_before_responding` — which asserts the
   exact order on purpose (§14) — has to be rewritten to assert a multiset plus
   the dependencies that still hold. That test is a deliberate guard; loosening
   it should be its own reviewed change.
3. It trades throughput for latency: four threadpool slots per checkout instead
   of one, out of 40. Worth it at current traffic, but it is a real trade and
   should be made knowingly.

### Still outstanding

- **C-4 elsewhere in the backend.** 223 of the 351 call sites are untouched —
  `vendor_service` (36), `rm_service` (23), `auth_service` (23), `salon_service`
  (17), `user_service` (16), the admin routers, and the rest. They still block
  the loop. Nothing on the payment path reaches them (verified:
  `customer_service`'s only use of `SalonService` is the static
  `flatten_business_type`, and `effective_unit_price` is pure), but every admin
  or vendor request still stalls payments by stalling the worker. `db_exec` and
  the AST script make this a mechanical follow-up per module, and it pairs
  naturally with [[module-by-module-audit]].
- **`core/features.py` is deliberately excluded.** `get_feature_statuses` is
  sync and does one blocking read, but it sits behind a 60 s `TTLCache`, so it
  blocks once per minute per worker at most. Making it async would ripple into
  `feature_service` and the `RequireFeature` dependency for almost no gain.
- **M-5**, above.
- Everything in §12's, §13's and §14's outstanding lists, unchanged: the browser
  pass on Phase 0's web changes, `maxDuration` on the proxy route, H-4
  (auto-capture in the dashboard), L-2, and the integration tier (26 skips —
  still no Docker here).
- **The Phase 2 deployment steps remain the gating item for all of this.** None
  of the four phases is in production, the `payment_intents` migration has not
  been applied anywhere, and the Razorpay dashboard still has no webhook. See
  §14's list, and note the order matters.
