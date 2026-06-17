# Coupon System — Audit Remediation Tracker

> Living doc. Updated as fixes land. Source audit: full production-readiness review (see conversation / this file's Findings section).
> Status legend: ⬜ not started · 🟡 in progress · ✅ done · ⏸️ blocked on decision · ❎ won't fix (by decision)

Branch: `dev` (coupon work built here). Migrations live in `supabase/migrations/`.

---

## Crucial Decisions (owner: user)

| # | Decision | Options | Chosen | Status |
|---|----------|---------|--------|--------|
| D1 | Vendor `convenience_fee` coupons (waive **platform** revenue, recorded `funded_by='vendor'`) | (a) Block vendors from `convenience_fee` · (b) Allow but record funding correctly · (c) Keep as-is | **(a) Block** | ✅ |
| D2 | Coupon redemption timing | (a) Keep at booking creation · (b) Only on payment success | **(b) On payment success** | ✅ |
| D3 | Cancelled-booking handling | (a) Reverse redemption + exclude from first-time · (b) Keep redemption (audit) but exclude cancelled from first-time · (c) Keep fully as-is | **(b) Keep redemption, exclude cancelled from first-time** | ✅ |
| D4 | TOCTOU reconciliation (charged vs recorded) | (a) Pin order amounts, trust at checkout · (b) Recompute & hard-fail on mismatch | **(a) Pin order amounts, trust at checkout** | ✅ |

---

## Fix Checklist

### P0 — Critical
- ✅ **C1. Charged-vs-recorded divergence (TOCTOU).** Pinned priced breakdown stored in order notes (`payment_service`); checkout parses it and passes `pinned_pricing` to `create_booking`, which records the exact charged amounts instead of recomputing. *Files:* `payment_service.py`, `customer_service.py`, `booking_service.py`.
- ✅ **C2. `redeem_coupon()` not authoritative.** New migration re-validates window, scope, first-time + limits under `FOR UPDATE`. *File:* `supabase/migrations/20260617000000_harden_coupon_redemption.sql`.

### P1 — High
- ✅ **H3/D2. Redeem on payment success, not booking creation.** Gated on `booking.payment_status == 'paid'`. *File:* `booking_service.py`.
- ✅ **H4. Enforce first-time atomically + per-user race closed in RPC.** *File:* migration.
- ✅ **H5/D1. Block vendor `convenience_fee` coupons.** Schema validator + service guard. *Files:* `coupon.py`, `vendor_service.py`.
- ✅ **H6. Store gross discount + snapshot (`salon_id`, `coupon_code`, `funded_by`, `scope`).** *Files:* migration, `pricing_service.py` (`coupon_gross_discount`), `booking_service.py`, `coupon_service.py`.
- ✅ **H7/D3. Cancelled bookings excluded from first-time** (app + RPC); redemption kept for audit. *Files:* `coupon_service.py`, migration.

### P2 — Medium
- ✅ **M8. Resolve coupon by indexed `code` lookup, not full scan.** *File:* `coupon_service.py`.
- ✅ **M9. Record floored convenience fee actually charged (₹1 min).** Pinned `convenience_fee_due` = charged. *File:* `payment_service.py`.
- ✅ **M10. Cart snapshot now compares unit price; content mismatch is a hard 400.** *File:* `customer_service.py`.
- ✅ **M11. Rate-limit `validate-coupon` (15/min).** *Files:* `rate_limit.py`, `customers.py`.
- ✅ **M12. Reject past `valid_until` at create/update.** *File:* `coupon.py`.
- 🟡 **M13. Coupon terms immutable-after-use / snapshot.** Partially covered by H6 redemption snapshot; live edits to coupon still allowed (acceptable now that redemptions snapshot terms). _Revisit if needed._
- ⬜ **M14. Confirm RLS posture on `coupons`/`coupon_redemptions`.** Needs ops confirmation (no code change).

### P3 — Low
- ⬜ **L15. Currency math → `Decimal`.** Deferred (rounding at each step mitigates; larger refactor). *File:* `pricing_service.py`.
- ✅ **L16. Index on `bookings.coupon_id`.** *File:* migration.
- ✅ **L17. Assert salon exists for vendor-scope create.** *File:* `coupon_service.py`.
- ✅ **L18. Redemption reporting view (`coupon_redemption_report`).** *File:* migration.
- ⬜ **L19. Confirm GST charged on post-discount fee.** Needs product confirmation (no code change identified yet).

### Tests (add alongside fixes)
- 🟡 T1. `redeem_coupon()` concurrency (two users, last coupon). _RPC now serializes via FOR UPDATE; explicit concurrency test still TODO (hard to express against live stack)._
- ✅ T2. Redemption rejects inactive/first-time at redeem time (RPC) — exercised via the live coupon integration test + first-time unit tests.
- 🟡 T3. TOCTOU: valid at order, invalid at checkout → charged == recorded. _Pinning implemented; dedicated test TODO._
- ✅ T4. Pending/unpaid booking → no redemption (D2). Added to `test_integration_booking.py` (unpaid customer2 path).
- ✅ T5. Duplicate checkout/retry → single redemption (idempotency via UNIQUE + RPC idempotency check; covered by existing idempotency tests).
- 🟡 T6. Fee coupon + ₹1 floor → recorded == charged. _Pinned; dedicated test TODO._
- ✅ T7. Cancelled booking excluded from first-time (`test_first_time_ignores_cancelled_booking`).
- ✅ T8. Gross discount exposed + snapshot recorded (`test_gross_discount_*`, integration snapshot asserts).
- ✅ Schema: vendor cannot create fee coupon; past `valid_until` rejected.

---

## Migration / Deploy Notes
- New migration: `supabase/migrations/20260617000000_harden_coupon_redemption.sql`.
  - **Applied to local stack** (`supabase migration up --local`) ✅. Must be applied to staging/prod before deploy.
  - Drops the old 4-arg `redeem_coupon` and replaces it with a 5-arg version (added `p_gross_discount`). App `CouponService.redeem` already passes the new param.
  - Adds snapshot columns to `coupon_redemptions`, indexes, and `coupon_redemption_report` view.

## Open (need product/ops, no code change)
- M14: confirm RLS posture (`coupons`/`coupon_redemptions` have RLS disabled — only safe if all access is service-role).
- L15: currency math → `Decimal` (deferred; rounding-per-step mitigates).
- L19: confirm GST is charged on the post-discount convenience fee.
- M13: live coupon edits remain allowed (acceptable now redemptions snapshot terms).

## Change Log
- _(init)_ Tracker created from audit. Awaiting D1–D4.
- D1–D4 answered (block vendor fee coupons; redeem on payment success; keep redemption but exclude cancelled from first-time; pin order amounts).
- Phase 1 done: H5, M8, M12, L17, M11.
- Phase 2 done: migration `20260617000000` (C2, H4, H6, L16, L18, D3-sql) — applied locally.
- Phase 3 done: D3 app-side first-time excludes cancelled.
- Phase 4 done: D2 redeem-on-paid + gross discount plumbed (pricing→booking→RPC).
- Phase 5 done: C1/D4 pinned pricing end-to-end + M9 floored fee + M10 price-aware cart check.
- Phase 6: unit tests added (30 pass); full non-integration suite 466 pass; live coupon integration test passes (incl. unpaid-no-redeem + snapshot asserts). Integration full-file run has pre-existing env flakiness (auth rate limit + SMTP retry delays), unrelated to these changes.
