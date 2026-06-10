# Codebase Cleanup / Audit Tracker

Tracks the read-only audit and the cleanup work that followed. Covers the backend
(`backend`) plus the three frontends (`salon-admin-panel`, `salon-management-app`,
`lubist_mobile_application`).

**Validation baseline:** `python -m pytest` → 12 passed (3 smoke + 9 integration vs local
Supabase). `ruff check` clean except the intentional `schemas/__init__.py` re-exports.
All changes live in the working tree on `dev` — **nothing committed yet**.

Legend: `[x]` done & validated · `[~]` in progress · `[ ]` todo · `[?]` needs decision

---

## P1 — Safe dead-code removal  ✅ COMPLETE (validated)

- [x] Delete `app/api/admin.py` (unreachable module — shadowed by the `app/api/admin/` package)
- [x] Remove 5 dead/broken frontend hooks (defined, never consumed, targeted non-existent endpoints):
  - [x] `useUpdateRMStatusMutation` → `PUT /admin/rms/{id}/status` (admin-panel `userApi.js`)
  - [x] `getAppointmentById` + `deleteAppointment` → `/admin/bookings/{id}` GET/DELETE (admin-panel `appointmentApi.js`)
  - [x] `useGetVendorEarningsQuery` → `/payments/vendor/{id}/earnings` (salon-management-app `paymentApi.js`)
  - [x] `useGetBookingFeePercentageQuery` → `/salons/config/booking-fee-percentage` (salon-management-app `salonApi.js`)
- [x] Remove duplicate `RMService.update_rm_profile` — kept the live copy (behavior-preserving, per decision)
- [x] `career_service.py` `email_service` — confirmed **false positive** (resolved via `globals()`); annotated with `# noqa`
- [x] ruff autofix: ~110 unused imports + targeted unused-vars (F841, calls preserved) + empty f-strings (F541)

### P1 follow-up: investigate the two flagged "latent bugs"  ✅ (both were dead code)
- [x] `booking_fee` recompute in `customer_service.checkout_cart` — dead; removed (+ orphaned `total_amount`). Fee is charged in `payment_service.create_cart_payment_order` and recorded in `booking_service.create_booking`.
- [x] `service_summaries` / `totals_obj` in `booking_service.create_booking` — dead refactor leftovers; removed (kept `ServiceSummary`/`Totals` imports, still used as type hints).
- [x] **Fix:** removed the silent `6.0%` fallback for missing `convenience_fee_percentage` config in `_calculate_booking_totals_multi_service` — now raises HTTP 500 like the other two sites. Added `HTTPException` to `create_booking` outer re-raise list. ⚠️ Side effect: the `convenience_fee_percentage` config row is now load-bearing for booking creation.

---

## P2 — Endpoint consolidation / orphan removal  🔵 PARTIALLY DONE

### Verified-orphan removals  ✅ (0 refs across all 3 frontends + tests + internal backend)
- [x] `GET /vendors/dashboard` + `VendorService.get_dashboard_stats` (frontend uses `/vendors/analytics`)
- [x] `POST /location/geocode` (forward geocode) — endpoint removed; `geocoding_service.geocode_address` kept (used by vendor approval)
- [x] `/customers/salons`, `/customers/salons/search`, `/customers/salons/{id}` + `CustomerService.browse_salons`/`search_salons`/`get_salon_details` (frontends use `/salons/*`)

### Bookings consolidation — Phase 1  ✅ (low-risk pruning, no consumer changes)
- [x] Removed 6 dead `/bookings/*` endpoints: `GET /user/{id}`, `GET /salon/{id}`, `GET /{id}`, `PATCH /{id}`, `POST /{id}/cancel`, `POST /{id}/complete`
- [x] Kept `POST /bookings/` + `GET /bookings/` (used by frontend + tests)
- [x] Removed dead `POST /customers/bookings` (`customer_create_booking`)
- [x] Removed orphaned service code: `BookingService.get_booking` / `update_booking` / `complete_booking` and the cascade `_get_booking_for_update` / `_verify_booking_access` / `_verify_rm_salon_access` (`cancel_booking` kept — used by `/customers/bookings/{id}/cancel`)
- [x] **Bug fix found here:** `BookingService._verify_salon_ownership` was defined twice — the live copy queried `salons.owner_id` (**no such column**; `salons` has `vendor_id`). Removed the broken `owner_id` copy, kept the correct `vendor_id` copy. Was latent because no test exercises the vendor+`salon_id` branch of `get_bookings`.

### Bookings consolidation — Phase 2  ✅ DONE (validated)
- [x] Re-added `POST /customers/bookings` (`create_booking`) as the canonical booking-create endpoint (delegates to `BookingService.create_booking`)
- [x] Migrated salon-management-app `bookingApi.createBooking` → `/api/v1/customers/bookings`; removed dead duplicate `getCustomerBookings` hook
- [x] Migrated `tests/test_integration_booking.py`: all `POST /bookings/` → `/customers/bookings`; `GET /bookings/?user_id` → `GET /customers/bookings/my-bookings` (list lives under `data`)
- [x] Deleted the entire `/bookings` router (`app/api/bookings.py` + main.py import/registration)
- [x] Removed orphaned `BookingService.get_bookings` + cascade `_verify_salon_ownership` (only caller was `get_bookings`)
- [x] Fixed pre-existing unused `logging` import in `main.py`
- Result: single customer-facing booking surface under `/customers/bookings/*` (create, my-bookings, cancel). Vendors use `/vendors/bookings`, admins use `/admin/bookings`. 14/14 tests pass.

### "Nearby salons" dedup  ✅ DONE (canonical: `/location/salons/nearby`)
- [x] Rewired `/location/salons/nearby` to delegate to `SalonService.get_nearby_salons` (gained discount-flag parity + single source of truth; removed the inline RPC/regular_buyer duplication from `location.py`)
- [x] Migrated salon-management-app `salonApi` nearby branch → `/api/v1/location/salons/nearby`
- [x] Removed `GET /salons/search/nearby` route (kept `SalonService.get_nearby_salons` — now shared by `/location`)
- [x] Added `tests/test_integration_location.py` (2 tests) — endpoint had zero coverage; validates shape + required coords against the real stack
- Note: lubist already used `/location/salons/nearby`; its results now also include `has_discounted_services` (additive, non-breaking).

### Other near-duplicate endpoints noted in audit (no action taken yet)  [?]
- [ ] Salon listing: `GET /salons/` vs `GET /salons/public` (frontends use `/public`; `/salons/` root may be orphan — verify before removing)
- [ ] Two cart subsystems (`/customers/cart` services vs `/customers/product-cart` products) — likely intentional; left as-is

---

## P3 — Hygiene  ✅ DONE (validated)

- [x] `app/schemas/__init__.py`: added explicit `__all__` (130 names) — silences all re-export F401s; also deduped `NearbySalonsResponse` (was imported from both `response.vendor` and `response.location`; kept location's, which already won). Validated every `__all__` name resolves.
- [x] Fixed E402 — moved the `logger = logging.getLogger(__name__)` assignment below the imports in `app/api/rm.py` and `app/api/salons.py`.
- [x] Deduped public-config in salon-management-app: removed the dead `getPublicConfig` query + `useGetPublicConfigQuery` from `salonApi.js` (unused); `configApi.useGetPublicConfigsQuery` is the live one (Checkout.jsx).
- [x] Bonus: eliminated the `career_service` `email_service` F811 properly — renamed the constructor param to `email_service_override`, dropping the `globals()['email_service']` hack and the `# noqa`. **Whole app is now ruff-clean (F401/F811/F841/E402/F541) with zero excludes/suppressions.**
- [ ] (Deferred, low value) Remove unused `GeocodeRequest`/`GeocodeResponse` classes — would touch 5 aggregator files for 2 trivial dead classes, and `reverse-geocode` is still live so forward-geocode may return. Left in place.

---

## Out of scope / noted for later (not part of the audit)
- [ ] Frontend unused-import lint (eslint) — not run this pass; the dead exported hooks were the higher-value finding
- [ ] Pydantic v2 deprecation warnings (`.dict()`, class-based `Config`) across handlers/schemas — pre-existing tech debt
- [ ] Commit the cleanup (currently uncommitted on `dev`)

---

_Last updated after P2 Phase 1 + the `_verify_salon_ownership` bug fix. Keep this file in sync as items are completed._
