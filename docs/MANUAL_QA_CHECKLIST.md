---
title: Manual QA checklist
area: cross-cutting
type: runbook
status: current
updated: 2026-11-12
read_when: Before a release — the human-only checks (UI, real email, Razorpay screens, OTP, mobile apps) the E2E suite can't do.
related:
  - backend/docs/E2E_TESTING.md
  - backend/docs/QUALITY_SYSTEM.md
  - lubist_mobile_application/docs/RELEASING.md
tags: [cross-cutting, runbook, current, testing, release]
---

# Manual QA checklist (what the E2E suite can't check)

The automated suite (`python scripts/run_e2e.py`, see `docs/E2E_TESTING.md`)
covers the API contract of every flow. This list is the **human-only** part:
UI, real email delivery/rendering, Razorpay checkout screens, SMS/OTP, and the
mobile apps. Each section names the E2E flow that already covers its API side.

Use real inboxes/phones you control (not `@example.com` — Resend refuses that
domain). Tick items per release; note the build/URL you tested.

## Public discovery — E2E flow `public`
- [ ] Home page: banner carousel renders, swipes, links open the right page (web + customer app)
- [ ] City picker / "use my location" fills the city; nearby salons appear
- [ ] Salon card shows offer badge / max-discount % for a salon with a coupon
- [ ] Salon detail: photos, hours, services, reviews, related salons, offers carousel
- [ ] Blog list + article page render (web); FAQ section expands; page has correct `<title>`/meta
- [ ] Product list/detail: images, sale price strike-through, "out of stock" state
- [ ] Invalid URLs (bad salon/product id) show a friendly 404 page, not a crash

## Auth — E2E flow `auth`
- [ ] Email signup → **confirmation email arrives**, link confirms, then login works (unconfirmed login shows the "confirm your email" message)
- [ ] Phone OTP signup/login (India number): **SMS arrives**, wrong OTP message, resend cooldown
- [ ] Password reset email arrives, link works, old password stops working
- [ ] Session survives reload; expired session silently refreshes; logout returns to home
- [ ] Delete account (Profile → Delete, and public `/delete-account` page): OTP/confirm, user can no longer log in

## Role boundaries — E2E flow `boundaries`
- [ ] Customer visiting `/admin`, `/rm`, `/vendor` URLs is redirected, no data flashes
- [ ] Vendor in the admin panel URL is refused

## RM — E2E flow `rm`
- [ ] Add Salon form (all steps): image upload, business hours picker, map pin, validation messages
- [ ] Add Regular Buyer form (`?type=regular_buyer`): age/gender fields, **phone OTP verification step sends a real SMS** and blocks submit until verified
- [ ] Duplicate owner email/phone shows the 409 message naming the conflict
- [ ] Drafts: save, reopen, submit, delete
- [ ] RM dashboard numbers/leaderboard look right after an approval

## Admin approval & vendor onboarding — E2E flow `admin`
- [ ] Admin receives the **"new vendor request" email** (staging `ADMIN_EMAIL`)
- [ ] Pending Salons: Approve (with and without a custom registration fee), Reject (reason required)
- [ ] Vendor receives the **approval email**; it renders (logo, fee amount), link opens `/vendor/complete-registration?token=…` in **both** the Next web app and the legacy path
- [ ] RM receives the **"salon approved" email**
- [ ] Complete registration page: password rules, success → lands on the payment page
- [ ] **Registration fee checkout (Razorpay UI):** card, **UPI (intent/QR/collect)**, netbanking; success, failure and "closed the popup" paths; payment receipt email
- [ ] After payment the salon appears publicly; admin "send payment reminder" email arrives for an unpaid salon

## Regular buyer — E2E flow `buyer`
- [ ] Approve Buyer in admin shows the "Regular Buyer" badge and creates the account (no email link needed)
- [ ] Buyer logs in **by phone OTP** (real SMS) on web and app
- [ ] Unpaid buyer sees the registration-fee prompt with the correct (overridden) amount; products page blocks checkout with that message
- [ ] Buyer pays the fee in Razorpay — **check UPI is offered** (open bug report: UPI missing for buyers; note the order amount when it is missing — UPI caps at ~₹1 lakh)
- [ ] Product prices show the **B2B price** and "wholesale" label; cart and checkout totals match
- [ ] Product checkout (Razorpay UI incl. UPI) → order confirmation screen + order in "My orders"
- [ ] Buyer's shop never appears in salon search/listing/map

## Products & product coupons — E2E flow `products`
- [ ] Admin Products page: create/edit with image upload (Cloudinary), B2B price fields, stock, featured toggle, soft delete/restore
- [ ] Admin Coupons: create a product coupon; customer sees it under "available offers" at product checkout; apply/remove; "already used" message
- [ ] Product order emails (if any) and admin Product Orders page status changes (shipped/delivered)

## Customer booking — E2E flow `booking`
- [ ] Book flow: pick services → date → time slots (max 3) → offers list → apply coupon → price breakdown (service due at salon vs convenience fee now)
- [ ] **Convenience-fee Razorpay checkout**: card + **UPI** + netbanking, success/failure/cancel; booking confirmation screen
- [ ] **Booking confirmation emails** to customer and vendor arrive and render
- [ ] My bookings: upcoming/past tabs, cancel within/outside the cancellation window shows the right message
- [ ] Review request email after the vendor marks "completed"; feedback link works without login

## Vendor dashboard — E2E flow `vendor`
- [ ] Salon settings edit (hours, photos, facilities) saves and shows publicly
- [ ] Services: add via the 4-step batch flow, edit, delete; category/subcategory pickers
- [ ] Bookings list: filters, confirm/complete/no-show buttons, customer contact info
- [ ] Coupons: create/deactivate; analytics page (if the flag is on)
- [ ] **Lubist Partner** (vendor) mobile app: login, bookings, status updates, push notification on a new booking

## Partner-with-us & careers — E2E flow `forms`
- [ ] Partner form on the public site: validation, success message, admin receives the lead email, lead shows in admin
- [ ] **Careers application with real files** (resume, Aadhaar, photo upload to Cloudinary): success page, HR/admin email, admin can download the documents (signed URL)

## Mobile apps (customer app + Lubist Partner)
- [ ] Fresh install from the store/internal track; login with email and phone OTP
- [ ] OTA update (`npm run ota`) is picked up after restart
- [ ] Razorpay native checkout incl. **UPI app switch** and return to the app
- [ ] Deep links from emails open the app (or web fallback)
- [ ] Location permission prompt + nearby salons

<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [Staging end-to-end flow tests](E2E_TESTING.md) · [Quality system (start here for testing)](QUALITY_SYSTEM.md) · [Releasing the customer app (OTA, builds, Play Store)](../../lubist_mobile_application/docs/RELEASING.md)

**Referenced by:** [Lubist Web — open work](../../salon_management_next/docs/BACKLOG.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
