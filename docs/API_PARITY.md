---
title: API parity report (generated)
area: cross-cutting
type: generated
status: current
updated: 2026-11-12
read_when: Checking which client (web, admin, customer app, Partner app) calls which endpoint, finding stale client calls before a release, or spotting a client that has fallen behind.
related:
  - backend/docs/QUALITY_SYSTEM.md
  - lubist_mobile_application/docs/API_CONTRACT.md
  - lubist_vendor_application/docs/API_CONTRACT.md
tags: [cross-cutting, generated, current, api]
---

# API parity report

Which client calls which backend endpoint, per feature, so a solo developer can see
where a client has fallen behind. The section between the `GENERATED` markers below is
produced by `scripts/api_parity_report.py`; everything above it (this part) is
hand-written and preserved on each run.

## How to run

From `backend/` (stdlib only, Python 3.11+; the venv is only needed for the contract export):

```bash
# 1. Make sure the contract matches the code (only needed if routes changed)
.venv/Scripts/python.exe scripts/export_openapi.py

# 2. Regenerate this file
.venv/Scripts/python.exe scripts/api_parity_report.py

# Options
#   --json parity.json                 also dump raw data (per-endpoint file:line usages)
#   --stdout                           print the generated section, write nothing
#   --web/--admin/--customer/--partner <path>   override a client repo ('' skips it)
#   --legacy ../salon-management-app   add the legacy Vite SPA as an extra column
```

Client repos default to siblings of `backend/`: `salon_management_next` (web),
`salon-admin-panel`, `lubist_mobile_application` (customer app),
`lubist_vendor_application` (partner app). A missing repo is skipped. The scan reads
each repo's **working tree as checked out** - if a repo is on a feature branch, the
report reflects that branch.

## How to read it

- **Headline** - totals. "Stale" and "dead files" should be zero before a release.
- **Gaps** - the actionable list. Each endpoint has an *audience* derived from its role
  dependency (`require_admin` / `require_rm` / `require_vendor` / `require_customer`),
  then from its path prefix (`/admin`, `/rm`, `/vendors`, `/customers`,
  `/product-orders`) and a few explicit overrides (`PATH_AUDIENCE` in the script):
  - admin -> admin panel; rm -> web; vendor -> web + partner app;
    customer / public -> web + customer app; shared (any logged-in role) -> no expectation.
  - "X behind Y" means Y calls an endpoint X is also expected to call but doesn't.
    Not every gap is a bug (the customer app has no careers page by design) - triage,
    then either build it or accept it.
- **Stale client calls** - a client calls a path/method that is not in the contract:
  an endpoint was removed/renamed, or the client is ahead of a backend change that has
  not been exported to `openapi.json` yet. High value - these are runtime 404/405s.
- **API references in dead files** - calls in files nothing imports. Not counted as
  usage; delete the file or wire it up.
- **Coverage by feature** - endpoints per OpenAPI tag used by each client.
- **Endpoint matrix** - `Y` = called with the matching method, `?` = path referenced but
  the method could not be determined (counted as used, all methods on that path).
  Role is what the router dependency enforces; `in-body check` means the handler also
  compares `user_role` itself (shown for information, not used for the audience).
- **Unresolved dynamic calls** - helper calls whose path is not a literal/template/
  file-local constant. Check by hand; they can hide real usages.

### Known scanner limitations

- Static, regex/lexer based (no TypeScript compiler). Paths are recognised in
  `apiGet/apiPost/...`, `api.get/post/...`, `apiFetch`, `fetch`, `axios.*`,
  `multipartUpload` calls, RTK Query `url:` properties, and any literal containing
  `/api/v1/` (or, for the Next app, bare `/salons/...` literals inside `src/lib/api`,
  `src/lib/auth`, `src/app/api`, `src/hooks`).
- Constants are resolved only within the same file (`const X = '...'`, simple
  `{ key: '...' }` maps). Paths built in another module and imported are missed and
  would show in "Unresolved dynamic calls".
- `${...}` interpolations become a wildcard segment; one glued to the end of the path
  (`/salons${qs}`) or that looks like a query string is dropped. A wildcard prefers a
  `{param}` slot, so `/blog/${x}` can't tell `{post_id}` from `{slug}` - the HTTP method
  disambiguates.
- Usage means "the code references it", not "a screen reaches it": a hook that no
  screen calls still counts (only whole files imported by nothing are excluded, and that
  check is by module name, so it errs towards "imported").
- Role inference reads `Depends(...)` in the decorator, handler params, router-level
  `dependencies=` and the package `__init__` router; dependencies nested inside other
  service dependencies are not followed. In-handler role logic is shown, not enforced.
- Type-only references to the generated contract (`ApiResponse<'/api/v1/...', 'get'>`)
  and path lists in array literals (e.g. no-auth path lists) are ignored on purpose.

## Definition of done for a feature (solo-dev checklist)

A feature touching the API is done when every box that applies is ticked:

1. [ ] **Backend** - router + service + tests; role dependency on the route
       (`require_*`), not only an in-handler check, so this report can see it.
2. [ ] **Contract regenerated** - `scripts/export_openapi.py` run and `openapi/openapi.json`
       committed (CI's `--check` fails otherwise). Mobile apps: `npm run api:types`.
3. [ ] **Web (Next)** - customer/vendor/RM flows wired in `salon_management_next`.
4. [ ] **Customer app** - if the audience is customer/public (or a conscious "web only"
       decision recorded in the feature's memory/doc).
5. [ ] **Partner app** - if the audience is vendor (or a conscious "web only" decision).
6. [ ] **Admin panel** - if it adds admin endpoints or admin-managed data.
7. [ ] **E2E step** - the golden path exercised once against staging (or local) in
       every client that got the feature; payment flows with the real gateway.
8. [ ] **Parity re-run** - `scripts/api_parity_report.py` shows no new stale calls,
       no new dead-file references, and every new gap is either closed or deliberate.

### Cadence

- **Before every release** (dev -> staging -> main): regenerate the contract and this
  report; stale calls and dead-file references must be zero.
- **After each backend feature lands on `dev`**: run it once to capture the new gaps
  while the context is fresh.
- **Mobile catch-up in batches**: don't chase every gap per feature. Let customer/partner
  app gaps accumulate, then clear them in one mobile release (one store review / OTA
  cycle) roughly every 2-4 weeks, using the "behind web" lists as the backlog.

<!-- BEGIN GENERATED: api_parity_report.py -->

_Generated 2026-11-12 17:44 UTC by `scripts/api_parity_report.py` - do not edit by hand (everything between the GENERATED markers is overwritten on each run)._

Scanned: **Web (Next)** `salon_management_next`; **Admin panel** `salon-admin-panel`; **Customer app** `lubist_mobile_application`; **Partner app** `lubist_vendor_application`

## Headline

- Endpoints in contract: **183** (method + path)
- Used by Web (Next): **101**
- Used by Admin panel: **76**
- Used by Customer app: **63**
- Used by Partner app: **28**
- Used by no client (excl. infra): **4**
- Client calls with no matching endpoint/method (stale): **0**
- Helper calls whose path could not be resolved statically: **0**
- API references in dead files (imported by nothing; not counted as usage): **3**

## Gaps (expected-audience heuristic)

Audience: admin -> admin panel; rm -> web; vendor -> web + partner app; customer/public -> web + customer app; mobile -> both apps; shared (any logged-in role) and infra -> no expectation.

### Customer app behind web (customer/public endpoint used by web, not by customer app) (14)

| Endpoint | Feature | Role | Used by |
|---|---|---|---|
| `POST /careers/apply` | Careers | public | Web (Next) |
| `POST /partners/apply` | Partners | public | Web (Next) |
| `GET /blog` | blog | public | Web (Next) |
| `GET /blog/sitemap-data` | blog | public | Web (Next) |
| `GET /blog/tags` | blog | public | Web (Next), Admin panel |
| `GET /blog/{slug}` | blog | public | Web (Next) |
| `GET /location/pincode/{pincode}` | location | public | Web (Next) |
| `GET /product-orders/available-coupons` | product-orders | authenticated | Web (Next) |
| `GET /product-orders/my-orders` | product-orders | authenticated | Web (Next) |
| `POST /product-orders/validate-coupon` | product-orders | authenticated | Web (Next) |
| `GET /product-orders/{order_id}` | product-orders | authenticated | Web (Next) |
| `GET /salons/popular-cities` | salons | public | Web (Next) |
| `GET /salons/{salon_id}/feedback` | salons | public | Web (Next) |
| `POST /salons/{salon_id}/feedback` | salons | public | Web (Next) |

### Web behind customer app (customer/public endpoint used by customer app, not by web) (5)

| Endpoint | Feature | Role | Used by |
|---|---|---|---|
| `GET /customers/favorites/products` | Customer Portal | authenticated | Customer app |
| `POST /customers/favorites/products` | Customer Portal | authenticated | Customer app |
| `DELETE /customers/favorites/products/{product_id}` | Customer Portal | authenticated | Customer app |
| `POST /customers/reviews` | Customer Portal | authenticated | Customer app |
| `GET /products/{product_id}` | products | public (optional auth) (in-body check: admin) | Customer app |

### Partner app behind web (vendor endpoint used by web, not by partner app) (3)

| Endpoint | Feature | Role | Used by |
|---|---|---|---|
| `POST /payments/registration/create-order` | Payments | authenticated | Web (Next) |
| `POST /payments/registration/verify` | Payments | authenticated | Web (Next) |
| `POST /vendors/complete-registration` | Vendor Management | public | Web (Next) |

### Web behind partner app (vendor endpoint used by partner app, not by web) (0)

_none_

### Vendor/RM/admin endpoints still referenced in the customer app (should be gone after the vendor split) (0)

_Plus 3 reference(s) in dead customer-app files - see "API references in dead files" below._

_none_

### Customer/RM/admin endpoints referenced in the partner app (0)

_none_

### Admin endpoints not used by the admin panel (1)

| Endpoint | Feature | Role | Used by |
|---|---|---|---|
| `POST /admin/service-categories/reorder` | admin | admin | - |

### Admin endpoints called from non-admin clients (0)

_none_

### Endpoints used by no client (excl. infra) (4)

| Endpoint | Feature | Role | Used by |
|---|---|---|---|
| `GET /rm/salons` | Relationship Manager | rm | - |
| `GET /rm/score-history` | Relationship Manager | rm | - |
| `POST /vendors/process-payment` | Vendor Management | vendor | - |
| `POST /admin/service-categories/reorder` | admin | admin | - |

## Stale client calls (no matching backend endpoint)

_none_

## API references in dead files

These files are imported by no other source file and are not framework entry points, so their calls are NOT counted above. Delete the file, or wire it up.

| Client | Call | Where |
|---|---|---|
| Customer app | `POST /upload/salon-image` | `src/services/upload/uploadService.ts:111` |
| Customer app | `POST /upload/agreement-document` | `src/services/upload/uploadService.ts:126` |
| Customer app | `GET /upload/agreement-document/signed-url` | `src/services/upload/uploadService.ts:132` |

## Coverage by feature (OpenAPI tag)

Counts are endpoints in the tag used by each client.

| Feature | Endpoints | Web (Next) | Admin panel | Customer app | Partner app | Unused |
|---|---:|---:|---:|---:|---:|---:|
| App Config | 1 | 0 | 0 | 1 | 1 | 0 |
| Authentication | 18 | 17 | 4 | 18 | 7 | 0 |
| Careers | 4 | 1 | 3 | 0 | 0 | 0 |
| Customer Portal | 24 | 20 | 0 | 24 | 0 | 0 |
| Health & Status | 2 | 0 | 0 | 0 | 0 | 2 |
| Partners | 3 | 1 | 2 | 0 | 0 | 0 |
| Payments | 3 | 3 | 0 | 1 | 0 | 0 |
| Relationship Manager | 10 | 8 | 0 | 0 | 0 | 2 |
| Upload | 6 | 3 | 4 | 0 | 3 | 0 |
| Vendor Management | 19 | 18 | 0 | 0 | 17 | 1 |
| admin | 45 | 0 | 44 | 0 | 0 | 1 |
| banners | 6 | 1 | 5 | 1 | 0 | 0 |
| blog | 9 | 4 | 6 | 0 | 0 | 0 |
| features | 3 | 0 | 3 | 0 | 0 | 0 |
| location | 3 | 3 | 0 | 2 | 0 | 0 |
| product-orders | 7 | 7 | 0 | 3 | 0 | 0 |
| products | 9 | 4 | 5 | 5 | 0 | 0 |
| salons | 11 | 11 | 0 | 8 | 0 | 0 |

## Endpoint matrix

`Y` = called with a matching method; `?` = path referenced but method not determinable statically. Role is inferred from the router's dependencies.

### App Config

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /app-config` | public | mobile |  |  | Y | Y |

### Authentication

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `POST /auth/login` | public | public | Y | Y | Y | Y |
| `POST /auth/login/phone/send-otp` | public | public | Y |  | Y |  |
| `POST /auth/login/phone/verify-otp` | public | public | Y |  | Y |  |
| `POST /auth/logout` | authenticated | shared | Y | Y | Y | Y |
| `POST /auth/logout-all` | authenticated | shared |  |  | Y |  |
| `DELETE /auth/me` | authenticated | shared | Y |  | Y |  |
| `GET /auth/me` | authenticated | shared | Y | Y | Y | Y |
| `PUT /auth/me` | authenticated (in-body check: customer) | shared | Y |  | Y | Y |
| `POST /auth/me/delete/send-otp` | authenticated | shared | Y |  | Y |  |
| `POST /auth/password-reset` | public | public | Y |  | Y | Y |
| `POST /auth/password-reset/confirm` | public | public | Y |  | Y | Y |
| `POST /auth/refresh` | public | public | Y | Y | Y | Y |
| `POST /auth/resend-verification` | authenticated | shared | Y |  | Y |  |
| `POST /auth/signup` | public | public | Y |  | Y |  |
| `POST /auth/signup/phone/send-otp` | public | public | Y |  | Y |  |
| `POST /auth/signup/phone/verify-otp` | public | public | Y |  | Y |  |
| `POST /auth/verify-phone/confirm-otp` | authenticated | shared | Y |  | Y |  |
| `POST /auth/verify-phone/send-otp` | authenticated | shared | Y |  | Y |  |

### Careers

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /careers/applications` | admin | admin |  | Y |  |  |
| `PATCH /careers/applications/{application_id}` | admin | admin |  | Y |  |  |
| `GET /careers/applications/{application_id}/download/{document_type}` | admin | admin |  | Y |  |  |
| `POST /careers/apply` | public | public | Y |  |  |  |

### Customer Portal

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /customers/available-coupons` | authenticated | customer | Y |  | Y |  |
| `GET /customers/bookings/my-bookings` | authenticated | customer | Y |  | Y |  |
| `PUT /customers/bookings/{booking_id}/cancel` | authenticated | customer | Y |  | Y |  |
| `GET /customers/cart` | authenticated | customer | Y |  | Y |  |
| `POST /customers/cart` | authenticated | customer | Y |  | Y |  |
| `POST /customers/cart/checkout` | authenticated | customer | Y |  | Y |  |
| `DELETE /customers/cart/clear/all` | authenticated | customer | Y |  | Y |  |
| `POST /customers/cart/validate-coupon` | authenticated | customer | Y |  | Y |  |
| `DELETE /customers/cart/{item_id}` | authenticated | customer | Y |  | Y |  |
| `PUT /customers/cart/{item_id}` | authenticated | customer | Y |  | Y |  |
| `GET /customers/favorites` | authenticated | customer | Y |  | Y |  |
| `POST /customers/favorites` | authenticated | customer | Y |  | Y |  |
| `GET /customers/favorites/products` | authenticated | customer |  |  | Y |  |
| `POST /customers/favorites/products` | authenticated | customer |  |  | Y |  |
| `DELETE /customers/favorites/products/{product_id}` | authenticated | customer |  |  | Y |  |
| `DELETE /customers/favorites/{salon_id}` | authenticated | customer | Y |  | Y |  |
| `GET /customers/product-cart` | authenticated | customer | Y |  | Y |  |
| `POST /customers/product-cart` | authenticated | customer | Y |  | Y |  |
| `DELETE /customers/product-cart/clear/all` | authenticated | customer | Y |  | Y |  |
| `DELETE /customers/product-cart/{item_id}` | authenticated | customer | Y |  | Y |  |
| `PUT /customers/product-cart/{item_id}` | authenticated | customer | Y |  | Y |  |
| `POST /customers/reviews` | authenticated | customer |  |  | Y |  |
| `GET /customers/reviews/my-reviews` | authenticated | customer | Y |  | Y |  |
| `PUT /customers/reviews/{review_id}` | authenticated | customer | Y |  | Y |  |

### Health & Status

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /` | public | infra |  |  |  |  |
| `GET /health` | public | infra |  |  |  |  |

### Partners

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `POST /partners/apply` | public | public | Y |  |  |  |
| `GET /partners/requests` | admin | admin |  | Y |  |  |
| `PATCH /partners/requests/{request_id}` | admin | admin |  | Y |  |  |

### Payments

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `POST /payments/cart/create-order` | authenticated | customer | Y |  | Y |  |
| `POST /payments/registration/create-order` | authenticated | vendor | Y |  |  |  |
| `POST /payments/registration/verify` | authenticated | vendor | Y |  |  |  |

### Relationship Manager

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /rm/dashboard` | rm | rm | Y |  |  |  |
| `GET /rm/leaderboard` | public | rm | Y |  |  |  |
| `PUT /rm/profile` | rm | rm | Y |  |  |  |
| `GET /rm/salons` | rm | rm |  |  |  |  |
| `GET /rm/score-history` | rm | rm |  |  |  |  |
| `GET /rm/vendor-requests` | rm | rm | Y |  |  |  |
| `POST /rm/vendor-requests` | rm | rm | Y |  |  |  |
| `DELETE /rm/vendor-requests/{request_id}` | rm | rm | Y |  |  |  |
| `GET /rm/vendor-requests/{request_id}` | rm | rm | Y |  |  |  |
| `PUT /rm/vendor-requests/{request_id}` | rm | rm | Y |  |  |  |

### Upload

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `POST /upload/agreement-document` | authenticated | vendor | Y |  |  | Y |
| `GET /upload/agreement-document/signed-url` | authenticated | vendor | Y | Y |  | Y |
| `POST /upload/cloudinary-banner-image` | authenticated | admin |  | Y |  |  |
| `POST /upload/cloudinary-blog-image` | admin (feature-gated) | admin |  | Y |  |  |
| `POST /upload/cloudinary-product-image` | authenticated | admin |  | Y |  |  |
| `POST /upload/salon-image` | authenticated | vendor | Y |  |  | Y |

### Vendor Management

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /vendors/analytics` | vendor | vendor | Y |  |  | Y |
| `GET /vendors/bookings` | vendor | vendor | Y |  |  | Y |
| `PUT /vendors/bookings/{booking_id}/status` | vendor | vendor | Y |  |  | Y |
| `POST /vendors/complete-registration` | public | vendor | Y |  |  |  |
| `GET /vendors/coupons` | vendor | vendor | Y |  |  | Y |
| `POST /vendors/coupons` | vendor | vendor | Y |  |  | Y |
| `DELETE /vendors/coupons/{coupon_id}` | vendor | vendor | Y |  |  | Y |
| `PATCH /vendors/coupons/{coupon_id}` | vendor | vendor | Y |  |  | Y |
| `POST /vendors/process-payment` | vendor | vendor |  |  |  |  |
| `GET /vendors/promotions` | vendor | vendor | Y |  |  | Y |
| `GET /vendors/promotions/active` | vendor | vendor | Y |  |  | Y |
| `POST /vendors/promotions/apply` | vendor | vendor | Y |  |  | Y |
| `GET /vendors/salon` | vendor | vendor | Y |  |  | Y |
| `PUT /vendors/salon` | vendor | vendor | Y |  |  | Y |
| `GET /vendors/service-categories` | vendor | vendor | Y |  |  | Y |
| `GET /vendors/services` | vendor | vendor | Y |  |  | Y |
| `POST /vendors/services` | vendor | vendor | Y |  |  | Y |
| `DELETE /vendors/services/{service_id}` | vendor | vendor | Y |  |  | Y |
| `PUT /vendors/services/{service_id}` | vendor | vendor | Y |  |  | Y |

### admin

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /admin/bookings/` | admin | admin |  | Y |  |  |
| `GET /admin/config` | admin | admin |  | Y |  |  |
| `POST /admin/config` | admin | admin |  | Y |  |  |
| `GET /admin/config/available-keys` | admin | admin |  | Y |  |  |
| `DELETE /admin/config/{config_key}` | admin | admin |  | Y |  |  |
| `GET /admin/config/{config_key}` | admin | admin |  | Y |  |  |
| `PUT /admin/config/{config_key}` | admin | admin |  | Y |  |  |
| `GET /admin/coupons` | admin | admin |  | Y |  |  |
| `POST /admin/coupons` | admin | admin |  | Y |  |  |
| `DELETE /admin/coupons/{coupon_id}` | admin | admin |  | Y |  |  |
| `GET /admin/coupons/{coupon_id}` | admin | admin |  | Y |  |  |
| `PATCH /admin/coupons/{coupon_id}` | admin | admin |  | Y |  |  |
| `GET /admin/product-orders/` | admin | admin |  | Y |  |  |
| `PATCH /admin/product-orders/{order_id}/status` | admin | admin |  | Y |  |  |
| `GET /admin/recent-activity` | admin | admin |  | Y |  |  |
| `GET /admin/rms` | admin | admin |  | Y |  |  |
| `PUT /admin/rms/{rm_id}` | admin | admin |  | Y |  |  |
| `GET /admin/salons/` | admin | admin |  | Y |  |  |
| `DELETE /admin/salons/{salon_id}` | admin | admin |  | Y |  |  |
| `PUT /admin/salons/{salon_id}` | admin | admin |  | Y |  |  |
| `POST /admin/salons/{salon_id}/send-payment-reminder` | admin | admin |  | Y |  |  |
| `PUT /admin/salons/{salon_id}/status` | admin | admin |  | Y |  |  |
| `GET /admin/service-categories` | admin | admin |  | Y |  |  |
| `POST /admin/service-categories` | admin | admin |  | Y |  |  |
| `GET /admin/service-categories/all-subcategories` | admin | admin |  | Y |  |  |
| `POST /admin/service-categories/reorder` | admin | admin |  |  |  |  |
| `DELETE /admin/service-categories/subcategories/{subcategory_id}` | admin | admin |  | Y |  |  |
| `PUT /admin/service-categories/subcategories/{subcategory_id}` | admin | admin |  | Y |  |  |
| `PATCH /admin/service-categories/subcategories/{subcategory_id}/toggle-status` | admin | admin |  | Y |  |  |
| `POST /admin/service-categories/upload-icon` | admin | admin |  | Y |  |  |
| `DELETE /admin/service-categories/{category_id}` | admin | admin |  | Y |  |  |
| `GET /admin/service-categories/{category_id}` | admin | admin |  | Y |  |  |
| `PUT /admin/service-categories/{category_id}` | admin | admin |  | Y |  |  |
| `GET /admin/service-categories/{category_id}/subcategories` | admin | admin |  | Y |  |  |
| `POST /admin/service-categories/{category_id}/subcategories` | admin | admin |  | Y |  |  |
| `PATCH /admin/service-categories/{category_id}/toggle-status` | admin | admin |  | Y |  |  |
| `GET /admin/stats` | admin | admin |  | Y |  |  |
| `GET /admin/users/` | admin | admin |  | Y |  |  |
| `POST /admin/users/` | admin | admin |  | Y |  |  |
| `DELETE /admin/users/{user_id}` | admin | admin |  | Y |  |  |
| `PUT /admin/users/{user_id}` | admin | admin |  | Y |  |  |
| `GET /admin/vendor-requests` | admin | admin |  | Y |  |  |
| `POST /admin/vendor-requests/{request_id}/approve` | admin | admin |  | Y |  |  |
| `POST /admin/vendor-requests/{request_id}/reject` | admin | admin |  | Y |  |  |
| `POST /admin/vendor-requests/{request_id}/resend-approval-email` | admin | admin |  | Y |  |  |

### banners

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /banners` | public | public | Y |  | Y |  |
| `POST /banners` | admin | admin |  | Y |  |  |
| `GET /banners/admin/all` | admin | admin |  | Y |  |  |
| `PUT /banners/reorder` | admin | admin |  | Y |  |  |
| `DELETE /banners/{banner_id}` | admin | admin |  | Y |  |  |
| `PUT /banners/{banner_id}` | admin | admin |  | Y |  |  |

### blog

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /blog` | public | public | Y |  |  |  |
| `POST /blog` | admin (feature-gated) | admin |  | Y |  |  |
| `GET /blog/admin/all` | admin (feature-gated) | admin |  | Y |  |  |
| `GET /blog/admin/{post_id}` | admin (feature-gated) | admin |  | Y |  |  |
| `GET /blog/sitemap-data` | public | public | Y |  |  |  |
| `GET /blog/tags` | public | public | Y | Y |  |  |
| `DELETE /blog/{post_id}` | admin (feature-gated) | admin |  | Y |  |  |
| `PUT /blog/{post_id}` | admin (feature-gated) | admin |  | Y |  |  |
| `GET /blog/{slug}` | public | public | Y |  |  |  |

### features

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /features` | admin | admin |  | Y |  |  |
| `GET /features/admin/all` | internal | admin |  | Y |  |  |
| `PATCH /features/admin/{key}` | internal | admin |  | Y |  |  |

### location

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /location/pincode/{pincode}` | public | public | Y |  |  |  |
| `GET /location/reverse-geocode` | public | public | Y |  | Y |  |
| `GET /location/salons/nearby` | public | public | Y |  | Y |  |

### product-orders

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /product-orders/available-coupons` | authenticated | customer | Y |  |  |  |
| `POST /product-orders/create` | authenticated | customer | Y |  | Y |  |
| `POST /product-orders/dev-verify/{order_id}` | authenticated | customer | Y |  | Y |  |
| `GET /product-orders/my-orders` | authenticated | customer | Y |  |  |  |
| `POST /product-orders/validate-coupon` | authenticated | customer | Y |  |  |  |
| `POST /product-orders/verify` | authenticated | customer | Y |  | Y |  |
| `GET /product-orders/{order_id}` | authenticated | customer | Y |  |  |  |

### products

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /products` | public (optional auth) | public | Y |  | Y |  |
| `POST /products` | admin | admin |  | Y |  |  |
| `GET /products/admin/all` | admin | admin |  | Y |  |  |
| `GET /products/categories` | public | public | Y | Y | Y |  |
| `GET /products/slug/{slug}` | public (optional auth) | public | Y |  | Y |  |
| `DELETE /products/{product_id}` | admin | admin |  | Y |  |  |
| `GET /products/{product_id}` | public (optional auth) (in-body check: admin) | public |  |  | Y |  |
| `PUT /products/{product_id}` | admin | admin |  | Y |  |  |
| `GET /products/{product_id}/related` | public (optional auth) | public | Y |  | Y |  |

### salons

| Endpoint | Role | Audience | Web (Next) | Admin panel | Customer app | Partner app |
|---|---|---|---|---|---|---|
| `GET /salons/config/public` | public | public | Y |  | Y |  |
| `GET /salons/popular-cities` | public | public | Y |  |  |  |
| `GET /salons/public` | public | public | Y |  | Y |  |
| `GET /salons/search/query` | public | public | Y |  | Y |  |
| `GET /salons/{salon_id}` | public | public | Y |  | Y |  |
| `GET /salons/{salon_id}/available-slots` | public | public | Y |  | Y |  |
| `GET /salons/{salon_id}/feedback` | public | public | Y |  |  |  |
| `POST /salons/{salon_id}/feedback` | public | public | Y |  |  |  |
| `GET /salons/{salon_id}/related` | public | public | Y |  | Y |  |
| `GET /salons/{salon_id}/reviews` | public | public | Y |  | Y |  |
| `GET /salons/{salon_id}/services` | public | public | Y |  | Y |  |

## Unresolved dynamic calls

Helper calls whose path argument is not a literal/template/file-local const. Check these by hand; they may hide real usages.

_none_

<!-- END GENERATED: api_parity_report.py -->
<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [Quality system (start here for testing)](QUALITY_SYSTEM.md) · [Customer app — API contract, client headers, force-update](../../lubist_mobile_application/docs/API_CONTRACT.md) · [Partner app — API contract, client headers, force-update](../../lubist_vendor_application/docs/API_CONTRACT.md)

**Referenced by:** [Coupons & discounts](COUPONS.md) · [Product favorites API](PRODUCT_FAVORITES_API.md) · [Lubist customer app — README](../../lubist_mobile_application/README.md) · [Lubist Web — architecture & decisions](../../salon_management_next/docs/ARCHITECTURE.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
