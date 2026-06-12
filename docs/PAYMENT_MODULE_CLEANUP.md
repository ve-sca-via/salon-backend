# Payment Module — Cleanup Tracker

Audit + cleanup of the `payment` module, one module at a time. Read-only audit
completed; findings prioritized P0–P4. This file tracks execution.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` skipped/deferred

---

## P0 — Correctness (webhook) — DECISION: **REMOVE** (webhook never functioned)

Rationale: endpoint #8 + its handlers have never worked (missing
`verify_webhook_signature` method → AttributeError; `status="completed"`
violates the payments/booking_payments CHECK constraints; vendor-reg branch
queries the wrong/nonexistent tables). The live flow confirms payments
synchronously via `customers/cart/checkout` → `BookingService.create_booking`
(writes `payments` with `status="success"`). Webhook removal matches real
behavior. An async webhook safety-net is logged as a FUTURE FEATURE, not cleanup.

- [x] Remove webhook endpoint `razorpay_webhook` + WEBHOOKS section — `app/api/payments.py`
- [x] Remove now-unused imports in `app/api/payments.py`: `Request`, `HTTPException`, `import logging` + `logger = ...`
- [x] Remove handler methods from `app/services/payment_service.py`: `handle_payment_success`, `handle_payment_failure`, `handle_order_paid`, `_activate_vendor_salon`
- [x] Remove now-unused import in `app/services/payment_service.py`: `from datetime import datetime`
- [x] Verify app imports cleanly (`python -c "import app.api.payments; import app.services.payment_service"` → OK) and no dangling references
- [ ] (Future feature, not now) Re-introduce a *working* async webhook safety-net targeting the live `payments` table if/when desired

**P0 done.** Newly orphaned by this removal (folded into P2):
`RazorpayService.verify_webhook_signature` (`app/services/payment.py:300`) and the
`RAZORPAY_WEBHOOK_SECRET` setting — their only consumer was the deleted webhook.

---

## P1 — Orphaned endpoints — DONE

- [x] #7 `GET /payments/vendor/earnings` (`get_vendor_earnings`) + `VendorEarningsResponse` — removed (api + service + schema + barrels)
- [x] #1 `POST /payments/booking/create-order` (`create_booking_payment_order`) + `BookingOrderCreate` — removed; web hook `useCreateBookingOrderMutation` removed
- [x] #2 `POST /payments/booking/verify` (`verify_booking_payment`) + `PaymentVerificationResponse` — removed; web hook `useVerifyBookingPaymentMutation` removed. (`PaymentVerification` request schema KEPT — shared with #5 registration/verify)
- [x] #6 `GET /payments/history` (`get_payment_history` + `get_customer_payment_history`) + `PaymentHistoryResponse` — removed; web hook `useGetPaymentHistoryQuery` + `PaymentHistory` tagType removed
- [x] Removed now-unused `List` import in `app/schemas/response/payment.py`
- [x] Verified: `import main` OK; no dangling refs in backend or web app

**Notes / leftovers from P1:**
- `verify_cart_payment` (service) KEPT — live path, called by `CustomerService.checkout_cart`.
- DB migration RPC `verify_payment_and_confirm_booking` (`20260122000001_*.sql`) is now unused (only #2 called it). Migration left in place (applied history); flag for later DB cleanup.
- `booking_payments` table is NOT orphaned — still used by `user_service.py:220` (delete-guard). Table left as-is.
- The `payments` vs `booking_payments` duality remains: live booking writes `payments`; `booking_payments` now only touched by the delete-guard. Out of scope for code cleanup; note for a future DB-level review.

## P2 — Dead code in gateway (`app/services/payment.py`) — DONE

- [x] Removed unused `RazorpayService` methods: `get_payment_details`, `capture_payment`, `refund_payment`, `get_key_id`, `create_registration_fee_order`, `create_booking_order`
- [x] Removed unused `razorpay_service` singleton
- [x] Removed `RazorpayService.verify_webhook_signature` — orphaned after P0
- [x] Removed `RAZORPAY_WEBHOOK_SECRET` from `app/core/config.py` and `.env.example` — orphaned after P0
- [x] Removed now-unused `hmac` / `hashlib` imports; trimmed stale docstring
- [x] KEPT `create_order` + `verify_payment_signature` (used by payment_service + product_order_service)
- [x] Verified: `import main` OK; no dangling refs

## P3 — Dead schemas — DONE

- [x] Removed `PaymentDetails`, `RazorpayOrderCreate`, `PaymentBase` — `app/schemas/request/payment.py` (+ barrels). Kept `PaymentVerification`.
- [x] Removed `VendorRegistrationPaymentResponse`, `BookingPaymentResponse` — `app/schemas/response/payment.py` (+ barrels). Kept `RazorpayOrderResponse`, `VendorRegistrationVerificationResponse`.
- [x] Removed now-unused imports: request side (`Field`, `Optional`, `PaymentType`, `Dict/Any`) reduced to `BaseModel` only; response side dropped `datetime` + `PaymentStatus`.
- [x] Verified: `import main` OK; no dangling refs.
- [x] Left domain enums `PaymentType` / `PaymentStatus` alone (shared across other modules — out of payment-module scope).

## P4 — Consolidation — DONE

- [x] DUP-1: added shared `resolve_razorpay_credentials(config_service, *, allow_env_fallback=False)` in `app/services/payment.py`.
  - `PaymentService._initialize_razorpay` now calls it (DB-only, strict — behavior preserved; replaced verbose `get_config(...).get("config_value")`).
  - `ProductOrderService._get_razorpay_creds` now calls it with `allow_env_fallback=True`, keeping its placeholder/dev-mode detection. Removed its function-local `settings` import (now unused there).
  - Both services standardized on `ConfigService.get_config_value`.
- [x] DUP-2 / REDUNDANT-1: MOOT — both lived inside `verify_booking_payment`, deleted in P1.
- [x] Verified: `import main` OK.

---

## Step 7 — Tests — DONE

- [x] Backend endpoint tests — `tests/test_payment_mocked.py` (18 tests): cart create-order (happy/discount/empty-cart 400/missing-config 500/auth), registration create-order (happy/not-approved 400/already-paid 400/auth), registration verify (happy+salon activation/invalid-sig 400/idempotent/auth), plus a regression guard asserting the 5 removed endpoints now 404.
- [x] Frontend (web) integration — `salon-management-app/src/services/api/paymentApi.test.jsx` (8 tests): HTTP contract for the 3 surviving hooks + asserts the removed booking/history hooks are gone.
- [x] Admin integration — N/A: admin panel calls ZERO payment endpoints (only writes `razorpay_*` / fee config). Nothing to test here for payment.
- [x] Mobile integration — N/A: lubist app has no test harness, and the cleanup changed nothing it touches (only `cart/create-order`, unchanged, + `customers/cart/checkout` in the customer module).
- [x] All green:
  - Backend full suite: **426 passed**.
  - Web full suite: **68 passed** (11 files).
