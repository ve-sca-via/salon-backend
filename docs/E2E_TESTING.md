---
title: Staging end-to-end flow tests
area: backend
type: runbook
status: current
updated: 2026-11-12
read_when: Running or extending the staging E2E suite (scripts/run_e2e.py), or reading an E2E report.
related:
  - backend/docs/QUALITY_SYSTEM.md
  - backend/docs/MANUAL_QA_CHECKLIST.md
  - backend/docs/REGULAR_BUYER_WORKFLOW.md
tags: [backend, runbook, current, testing]
---

# End-to-end (E2E) API flow tests

`tests/e2e/` is a checklist-style suite that drives the **deployed** backend
(staging by default) over HTTP, flow by flow, the way the web/mobile apps do:
an RM submits a salon, the admin approves it, the vendor registers, a customer
books, a regular buyer orders at B2B prices, and so on. Each test is one
checklist step; the run ends with a ✅/❌/⏭/🐞 summary per flow and a markdown
report.

## How it differs from the other test tiers

| Tier | Where | Talks to | Data | Runs |
|---|---|---|---|---|
| Unit / smoke (`pytest -m "not integration"`) | `tests/test_*_mocked.py`, `test_smoke.py` | the app in-process, DB mocked | none | every PR (CI) |
| Integration (`pytest -m integration`) | `tests/test_integration_*.py` | the app in-process + **local** Supabase (`supabase start`) | throwaway local DB | every PR (CI) |
| **E2E** (`python scripts/run_e2e.py`) | `tests/e2e/` | the **deployed server** over HTTPS + staging Supabase (service role, for seeding/cleanup only) | fixed staging accounts + per-run data, cleaned up | **manually** (local or the `E2E (staging)` workflow) |

The E2E suite never imports `app`. It catches what the other tiers can't:
deployment config (env vars, `system_config`, CORS/proxy, rate limits), schema
drift between code and the real database, email/payment wiring, and whole
multi-role journeys.

It is **opt-in**: `tests/e2e/conftest.py` ignores its own tests unless
`E2E_RUN=1` or `--e2e` is given, so plain `pytest`, `pytest -m "not integration"`
and `pytest -m integration` never collect it.

## Setup

1. Create `tests/e2e/.env.staging` (git-ignored by the `.env.*` rule — check with
   `git check-ignore -v tests/e2e/.env.staging`). Keys:

   | Key | What | Where from |
   |---|---|---|
   | `E2E_BASE_URL` | server root (no `/api/v1`) | default `https://salon-backend-staging.up.railway.app` |
   | `E2E_SUPABASE_URL` | staging Supabase URL | Railway `SUPABASE_URL` |
   | `E2E_SUPABASE_SERVICE_ROLE_KEY` | seeding + cleanup + DB assertions | Railway `SUPABASE_SERVICE_ROLE_KEY` |
   | `E2E_SUPABASE_ANON_KEY` | proves product RPCs refuse the anon key | Railway `SUPABASE_ANON_KEY` |
   | `E2E_JWT_SECRET_KEY` | mints the two stateless proof tokens (see below) | Railway `JWT_SECRET_KEY` |
   | `E2E_JWT_ALGORITHM` | usually `HS256` | Railway `JWT_ALGORITHM` |
   | `E2E_PASSWORD` | password of every seeded account | default `Test@1234` |
   | `E2E_RAZORPAY_ENABLED` | `1` to run payment steps | off by default |
   | `E2E_RAZORPAY_KEY_SECRET` | Razorpay **TEST** key secret, to sign fake payments | Razorpay dashboard (test mode) |
   | `E2E_MIN_INTERVAL` | seconds between requests (default `0.65`) | — |

   Fetch the values with the Railway CLI from the backend folder (linked to
   project **Lubist Staging**, env `staging`, service `salon-backend` — check with
   `railway status`):

   ```powershell
   railway variables --kv   # copy SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, JWT_SECRET_KEY, JWT_ALGORITHM
   ```

   Never paste these into docs, tickets or reports. Real environment variables
   with the same names override the file (that is how CI passes them).

2. Use the backend venv: `.venv/Scripts/python.exe` (it already has `httpx`,
   `supabase`, `python-jose`, `pytest`).

## Running

```powershell
python scripts/run_e2e.py                          # all flows against staging
python scripts/run_e2e.py --flow buyer             # one flow
python scripts/run_e2e.py --flow auth,boundaries   # several
python scripts/run_e2e.py --keep-data              # keep this run's data to inspect it
python scripts/run_e2e.py --sweep-stale            # also delete leftovers of older runs
python scripts/run_e2e.py --base-url http://localhost:8000   # a local server
python scripts/run_e2e.py -- -x -vv                # extra pytest args after --
```

Flows (one file each, run in this order): `public`, `auth`, `boundaries`, `rm`,
`admin`, `buyer`, `products`, `booking`, `vendor`, `forms`. Every flow can run on
its own — anything it needs from another role is seeded or created inside it.

A full run takes ~6–8 minutes: requests are throttled to stay under the
server's global 100 req/min per IP limit, and the 5/min login limit is handled
by caching one session per account and backing off on 429.

**CI:** Actions → **E2E (staging)** → *Run workflow* (`.github/workflows/e2e-staging.yml`,
`workflow_dispatch` only). It needs repo secrets `E2E_SUPABASE_URL`,
`E2E_SUPABASE_SERVICE_ROLE_KEY`, `E2E_SUPABASE_ANON_KEY`, `E2E_JWT_SECRET_KEY`
(optional `E2E_PASSWORD`, `E2E_RAZORPAY_KEY_SECRET`). The report is attached as
an artifact and appended to the job summary.

## Reading the report

The console prints a checklist per flow and the same thing is written to
`tests/e2e/reports/<timestamp>.md` (git-ignored).

| Icon | Meaning | What to do |
|---|---|---|
| ✅ | step passed | — |
| ❌ | step failed (assertion or error) — the line shows the request and the response | a regression, a staging config problem, or a test bug: investigate |
| ⏭ | skipped, with the reason | usually *payments disabled* or *prerequisite not available* (an earlier step of the flow failed) |
| 🐞 | **known** backend bug / incomplete feature, reason starts `BUG:` / `INCOMPLETE:` with the code location | tracked; it only shows when the bad behaviour is actually observed |
| ✨ | a known-bug step now passes | the bug was fixed — remove the `xfail_if` |

Steps inside a flow share state; when a step can't produce what later steps
need (e.g. no order was created), the later steps **skip** with
"prerequisite not available" instead of cascading errors.

## Test data and cleanup

* **Fixed accounts** (re-used, seeded idempotently with the service role every
  run; password and role re-asserted): `e2e.admin@example.com`,
  `e2e.rm@example.com`, `e2e.vendor@example.com` (owns the public salon
  **"[E2E] Lubist Test Salon"** with one service, **"[E2E] Classic Haircut"**),
  `e2e.customer@example.com`. These are never deleted.
* **Per-run data** carries the run id `E2E-<yyyymmddHHMMSS>` in a name, email,
  title or notes field: join requests, approved salons and the vendor/buyer
  accounts they create, products, coupons, services, bookings, product orders,
  partner leads. At the end of the session everything with the run's tag is
  deleted in FK-safe order (bookings → orders → carts/intents → coupons →
  products → services → salons → RM score rows → requests → leads → users).
  `--keep-data` skips that; `--sweep-stale` additionally deletes anything tagged
  `E2E-` from older runs (crashed runs, `--keep-data` runs).
* Carts / payment intents of the fixed accounts are wiped at cleanup (those
  accounts exist only for this suite).

### Things the suite fakes, and why

| Real path | Why we can't drive it | What the suite does instead |
|---|---|---|
| Registration link from the approval email | the token is a stateless JWT that only exists in the email | signs an identical token with the server's `JWT_SECRET_KEY` (`support/tokens.py`) |
| RM OTP-verifies a regular buyer's phone | real SMS via MessageCentral | signs the same `phone_verification` JWT the OTP endpoint returns |
| Regular buyer logs in by phone OTP | real SMS | sets a known password on the auto-created account (service role), logs in with email+password |
| Paying fees/orders (Razorpay) when payments are off | staging Razorpay is blocked | marks the fee paid / calls the same post-payment RPCs (`decrement_product_stock`, `redeem_product_coupon`) with the service role, and says so in the report notes |

## Enabling the payment steps (Razorpay TEST keys)

Staging's live Razorpay keys were deliberately renamed to
`razorpay_key_id__blocked_live_on_staging` / `razorpay_key_secret__blocked_live_on_staging`
in staging `system_config`. **Never rename those back.** To turn payments on:

1. In the Razorpay dashboard switch to **Test mode** → Settings → API keys →
   generate a key pair (`rzp_test_...`).
2. Open the **staging** admin panel → System Config, and add two **new** keys:
   `razorpay_key_id` = the `rzp_test_...` id, `razorpay_key_secret` = the test
   secret. (Same keys `resolve_razorpay_credentials` reads; config is cached
   briefly, so wait ~1 minute.) Optionally add `razorpay_webhook_secret` for the
   test-mode webhook.
3. Locally add to `tests/e2e/.env.staging`:
   ```
   E2E_RAZORPAY_ENABLED=1
   E2E_RAZORPAY_KEY_SECRET=<the same test key secret>
   ```
   In CI add the repo secret `E2E_RAZORPAY_KEY_SECRET` and tick **razorpay**
   when dispatching the workflow.
4. Run `python scripts/run_e2e.py --flow admin,buyer,booking,products`. The
   payment steps then create real **test-mode** Razorpay orders and verify them
   with a signature computed as `HMAC_SHA256(order_id|payment_id, key_secret)` —
   exactly what Razorpay Checkout returns — so no card/UPI interaction is needed.
   The checkout UI itself (cards, UPI, netbanking) stays a manual check.

Notes: `POST /product-orders/dev-verify/{id}` exists but returns 403 because
Railway runs with `ENVIRONMENT=production` (the suite asserts that it stays
blocked). With no DB keys, product orders fall back to the env
`RAZORPAY_KEY_*` values, which are `placeholder…` on staging, so product orders
run in "simulation mode" (`dev_mode: true`, `dev_order_…` ids) — order
creation is testable, payment isn't.

## Safety rails

* **Production refusal:** the run aborts if the base URL host is under
  `ondigitalocean.app`, `lubist.com` or `lubist.app`, or if `E2E_SUPABASE_URL`
  is the production Supabase project — unless `--allow-prod` / `E2E_ALLOW_PROD=1`.
  Don't.
* **No SMS:** OTP endpoints are never called.
* **Email volume:** all seeded and per-run addresses are `@example.com`; Resend
  rejects that domain outright (HTTP 422, nothing is delivered — visible as
  `Resend rejected email ... example.com` in staging logs). The only mails that
  actually go out are the **admin notifications** to staging's `ADMIN_EMAIL`:
  ~4 per full run (2 salon requests, 1 buyer request, 1 partner lead).
* **Rate limits:** one login per account per run; global throttle; 429 backoff.
* **Concurrency:** don't run two suites against the same environment at once —
  they share the fixed accounts (the workflow has a concurrency group).

## Adding a step or a flow

* A step is a test function in the flow's file; its **docstring's first line
  is the checklist title**. Steps run in file order.
* Use `flow[...]` (module-scoped dict) to hand data to later steps and
  `flow.need("key")` to skip cleanly when a prerequisite is missing.
* Use `world.token(role)` for a cached session (`admin`, `rm`, `vendor`,
  `customer`) and `world.db` for service-role reads/asserts.
* Use `expect(resp, 200, ...)` — failures print the request and response.
* Tag everything you create with `world.cfg.run_id` in a name/title/notes/email
  field that `World.cleanup` searches, or add your table to `cleanup()`.
* Known backend bug? `xfail_if(<bad behaviour observed>, "BUG: what, where (file:line)")`.
* New flow: create `tests/e2e/test_NN_<name>.py` with `FLOW = "<key>"`,
  `FLOW_TITLE = "..."`, `pytestmark = pytest.mark.e2e`, and add the key to
  `FLOWS` in `scripts/run_e2e.py`.

See `docs/MANUAL_QA_CHECKLIST.md` for what still needs a human.

## Bugs found by the first staging run (2026-11-12)

The first full run (`E2E-20261112015224`) surfaced these. All are fixed and **deployed
to staging**; they reach production with the next `staging → main` merge.

| # | Bug | Fix | e2e step |
|---|---|---|---|
| 1 | `POST /vendors/process-payment` (DEMO) marked the fee paid with no payment | 403 unless `ENVIRONMENT=development` (`app/api/vendors.py`) | admin › process-payment |
| 2 | `POST /customers/cart/checkout` booked without paying; `payment_id` without signature recorded "paid" | order id + payment id + signature all required (`customer_service.checkout_cart`) | booking › unpaid checkout |
| 3 | `POST /product-orders/create` 500 for every B2B buyer (`salons.registration_fee_amount` doesn't exist) | fee resolved via `ConfigService.get_registration_fee_for_salon` | buyer › unpaid blocked / orders |
| 4 | access and refresh tokens interchangeable | `type` claim + check (untyped legacy tokens still accepted until they expire) | auth › token type steps |
| 5 | vendors could write `is_verified` / `is_active` / `custom_registration_fee_amount` | `VENDOR_EDITABLE_SALON_FIELDS` allowlist, others dropped + logged | vendor › cannot self-verify |
| 7 | buyer salons served `/available-slots` (and `/services` 500'd for hidden salons) | `is_publicly_visible` excludes `regular_buyer`; hidden `/services` → 404 | buyer › hidden after activation |
| 8 | anyone could open a registration order on another vendor's request | caller must own the request's salon (or match `owner_email`) | — (mocked tests only) |

**#6** (wholesale prices visible to anyone): anonymous callers no longer receive
`b2b_discount_price` / `b2b_discount_percentage` (commit `11d94a6`, staging). Any
**logged-in** user — customers included — still receives them; whether customers
should is an open product question.

<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [Quality system (start here for testing)](QUALITY_SYSTEM.md) · [Manual QA checklist](MANUAL_QA_CHECKLIST.md) · [Regular buyer (B2B) workflow](REGULAR_BUYER_WORKFLOW.md)

**Referenced by:** [Rate limiting](rate-limiting-guide.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
