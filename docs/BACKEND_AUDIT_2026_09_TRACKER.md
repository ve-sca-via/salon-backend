# Backend Maintainability Audit — Sept 2026 Tracker

Cross-session checklist from the full-backend audit on 2026-09-05 (endpoint caller
cross-reference across all 3 frontends + service-layer duplication review + newer-feature
debt review). Builds on `CLEANUP_AUDIT_TRACKER.md` (auth/bookings/payments/storage, done
~2026-06) and `PAYMENT_MODULE_CLEANUP.md` (payment module, done ~2026-06).

**Status:** P0, P1, and P2 fully fixed & tested on `dev` 2026-09-05. P3 still pending
(deliberately deferred — marked low-urgency in this doc).

Legend: `[x]` done & validated · `[~]` in progress · `[ ]` todo · `[?]` needs a decision first

---

## P0 — Live bugs (functional defects, not just cleanup)

- [x] **Stale `booking_payments` guard silently disables user-deletion safety check**
  Fixed 2026-09-05: `app/services/user_service.py:220` and
  `app/services/auth_service.py:1294` now query `payments` instead of the retired
  `booking_payments` table. Regression test added:
  `tests/test_user_mocked.py::test_delete_blocked_by_payment_history_is_400`.

- [x] **Broken Cloudinary image cleanup on vendor-request rejection**
  Fixed 2026-09-05: added `CloudinaryService.delete_file()` (reuses
  `_extract_from_cloudinary_url`); `rm_service.py`'s
  `_cleanup_vendor_request_images` now calls it instead of the Supabase Storage
  no-op. Regression test added:
  `tests/test_rm_mocked.py::test_delete_draft_cleans_up_cloudinary_images`.

- [x] **Unescaped user input in transactional emails (XSS-in-email risk)**
  Fixed 2026-09-05: added `booking_confirmation.html`, `new_booking_vendor.html`,
  `booking_cancellation_vendor.html` templates (Jinja2 autoescaped); the 3 functions
  now render through them instead of raw f-string HTML. `send_booking_confirmation_to_customer`
  gained a `booking_id` param (threaded through from `booking_service.py`) so
  `related_entity_id` is no longer dropped. Manually verified script/img-tag payloads
  come back escaped.

- [x] **Hardcoded "© 2025" in every transactional email footer**
  Fixed 2026-09-05: added `EmailService._render(template_name, **ctx)` which injects
  `current_year=datetime.now().year`; all 8 template-based sends (including
  `_send_admin_notification`) now route through it instead of passing
  `current_year=2025` individually.

- [x] **Verify `partner_requests` table exists in every deployed environment**
  Resolved 2026-09-05 — this was never a real gap, just `supabase/schema.sql` being
  a stale, never-auto-regenerated `pg_dump` snapshot (it also predates `blog_posts`,
  `feature_flags`, `blog_post_faqs`). Checked the actual linked DB instead:
  `supabase migration list` shows `20260701000000_create_partner_requests_table.sql`
  applied remotely, and `supabase db dump --linked` confirms `partner_requests`
  exists in `lubist_staging` with its real constraints. See `db-schema/current_schema.sql`
  (new, generated straight from the linked DB — a live reference to check "does this
  table/column actually exist" against, instead of tracing migration files by hand).

---

## P1 — Confirmed dead code (safe, mechanical, low-risk removal)

- [x] Delete `POST /admin/config/cleanup/expired-tokens` — removed 2026-09-05, along
  with the now-unused `cleanup_expired_tokens` import.
- [x] Delete `GET /careers/applications/{id}` — removed 2026-09-05 (route + its 3
  tests; `CareerService.get_application_by_id` kept, still used internally by
  `update_application_status`).
- [x] Delete `GET /partners/requests/{id}` — removed 2026-09-05 (route, its
  now-dead `PartnerService.get_request_by_id`, and its 3 tests).
- [x] Delete `GET /admin/service-categories/subcategories/{id}` — removed 2026-09-05.
- [x] Merge the duplicate `from app.api import ...` line in `main.py` — done 2026-09-05.
- [x] Remove unused `get_current_user` import in `app/api/features.py` — done 2026-09-05.
- [x] Remove dead `is_feature_enabled()` helper in `app/core/features.py` — removed
  2026-09-05. (`get_feature_status()` turned out to still be used internally by
  `is_feature_visible_to()` — kept.)
- [x] Remove leftover `# DEBUG:` block in `app/services/vendor_service.py` —
  removed 2026-09-05 (comment + the two `logger.debug` calls it justified).

---

## P2 — Duplicate logic to consolidate (no urgency, do when convenient)

- [x] `app/services/otp_service.py:239-253` and `:365-379` — send and verify each
  hand-rolled an identical "refresh stale token, retry once on 401/403" block.
  Fixed 2026-09-05: extracted `OTPService._call_with_token_refresh()`.
- [x] `app/services/auth_service.py:1741-1757` and `:1843-1860` — "phone already
  registered" guard copy-pasted across send-OTP and verify-OTP paths.
  Fixed 2026-09-05: extracted `AuthService._ensure_phone_available()`.
- [x] `app/services/booking_service.py:230-234` reimplemented the discounted-price
  fallback that `customer_service._get_effective_service_price` already provided.
  Fixed 2026-09-05: moved to a module-level `effective_service_price()` in
  `pricing_service.py`; `booking_service.py` and `customer_service.py` both call
  it now, and the dead private method on `CustomerService` was removed.

---

## P3 — Backlog items surfaced during the audit (not urgent, just noted)

- [ ] `app/services/payment_service.py:581` — `# TODO: Send payment receipt and
  welcome emails` — pre-existing, still open; post-payment emails may not currently
  fire. Worth its own ticket.

---

## Checked and confirmed clean (no action needed — listed so we don't re-audit these)

- Endpoint inventory: 175/181 routes confirmed used by at least one of the 3
  frontends (`salon-admin-panel`, `salon-management-app`, `lubist_mobile_application`).
  Only the 4 P1 orphans above, plus `/health` and `/` (expected infra checks), have no
  caller.
- Previously-open items from `CLEANUP_AUDIT_TRACKER.md` P2 are now resolved: bare
  `GET /salons/` root no longer exists in code; the two cart subsystems
  (`/customers/cart` vs `/customers/product-cart`) are both genuinely separate and used.
- `PricingService` is the single source of truth for all fee/discount math —
  `booking_service`, `customer_service`, `payment_service` all route through it.
- `coupon_service.py` — well-factored, no function over ~150 lines, no redundant
  repeated queries.
- `service_taxonomy.py` vs `config_service.py` — no overlap, clean separation.
- Feature-flags/entitlements system — intentionally narrow (only gates `blog` today),
  matches its own docs (`FEATURE_FLAGS.md`); not an abandoned system.
- Push notifications — zero orphan code; planning doc only (`NOTIFICATIONS_FEATURE_PLAN.md`),
  nothing built yet, nothing to clean up.
- Career applications, partner-with-us, blog/FAQ modules — fully wired to their
  admin-panel UIs, no half-finished code, no leftover duplicate endpoints from earlier
  iterations.
- ruff/vulture at import/unused-variable level — already clean aside from the two P1
  import nits above.

---

_Created 2026-09-05 from a 3-agent audit pass (endpoint cross-reference, service-layer
duplication, newer-feature debt). Keep this file in sync as items are completed, same
convention as `CLEANUP_AUDIT_TRACKER.md`._
