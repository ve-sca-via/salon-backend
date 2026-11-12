---
title: Quality system (start here for testing)
area: backend
type: guide
status: current
updated: 2026-11-12
read_when: Before a release, when you're unsure whether flows still work, or to understand how E2E, the API contract and the parity report fit together.
related:
  - backend/docs/E2E_TESTING.md
  - backend/docs/MANUAL_QA_CHECKLIST.md
  - backend/docs/API_PARITY.md
  - backend/docs/CLIENT_APPS_AND_VERSIONING.md
  - backend/docs/MIGRATION_SAFETY.md
  - lubist_mobile_application/docs/API_CONTRACT.md
tags: [backend, guide, current, testing, release]
---

# Quality System — How Lubist Stays Working With One Developer

**Start here.** This page explains the approach and links to the detailed docs.
It was set up in November 2026 to solve two problems:

1. **"I can't tell whether whole flows still work."** Unit tests checked single
   functions. Nothing walked a real flow (RM → admin → buyer → order) against a
   deployed server.
2. **"The mobile apps fall behind and I can't keep track."** Five clients (Next
   web, admin panel, customer app, Partner app, legacy SPA) share one backend.
   Keeping them in sync depended on remembering every change.

The approach replaces *remembering* with *checks that fail*. Each layer below
catches a different kind of problem.

---

## The layers

| Layer | Catches | Runs | Doc |
|---|---|---|---|
| Unit tests (mocked) | Logic bugs in a function | Every PR (CI), ~1 min | `tests/test_*_mocked.py` |
| Integration tests | DB/migration problems against a local Supabase | Every PR (CI) | [testing in MIGRATION_SAFETY.md](MIGRATION_SAFETY.md) |
| **API contract check** | A backend change that silently breaks an app | Every PR (CI) | [CLIENT_APPS_AND_VERSIONING.md §4](CLIENT_APPS_AND_VERSIONING.md) |
| **Staging E2E flows** | A whole business flow broken or unfinished | Before every release (manual) | [E2E_TESTING.md](E2E_TESTING.md) |
| **Manual QA checklist** | UI, emails, Razorpay UI, devices | Before every release | [MANUAL_QA_CHECKLIST.md](MANUAL_QA_CHECKLIST.md) |
| **Parity report** | Features one client has and another lacks | Before each release / planning | [API_PARITY.md](API_PARITY.md) |
| **Force-update + app rules** | Old app builds in the wild, vendors in the wrong app | Always on at runtime | [CLIENT_APPS_AND_VERSIONING.md](CLIENT_APPS_AND_VERSIONING.md) |

---

## 1. Staging E2E flows: "does the whole thing work?"

`python scripts/run_e2e.py` runs about 140 checklist steps across 10 flows against
**staging** (Railway) and prints ✅ / ❌ / ⏭ / 🐞 per step. It also writes a
markdown report to `tests/e2e/reports/`.

The flows are: public discovery, auth per role, role boundaries, RM, admin
approval, regular-buyer onboarding, product selling and coupons, customer
booking, vendor, and public forms.

- It creates its own data, tagged with a run id, and deletes it afterwards.
  The fixed `e2e.*@example.com` accounts and "[E2E] Lubist Test Salon" stay on
  staging permanently.
- It refuses to run against production.
- Payment steps are skipped until staging has Razorpay **test** keys. See
  E2E_TESTING.md, "Enabling payments".
- 🐞 marks a step that exposed a known backend bug (xfail with a `BUG:`
  reason). When the bug is fixed, flip it to a normal assert.

**Rule:** before merging `staging` → `main`, run it and read the report.

## 2. The API contract: making drift fail loudly

The backend's shape is exported from code into **`openapi/openapi.json`**, which
is committed. Prod and staging have `/openapi.json` disabled, so it can't be
fetched. Run `python scripts/export_openapi.py` after changing any route or
schema, and commit the result.

- **CI fails** if the file is stale (`export_openapi.py --check`).
- **CI fails** on breaking changes compared with the base branch
  (`scripts/check_api_breaking.py`). Breaking changes include removed
  endpoints, removed response fields, newly required inputs and type changes.
  To override deliberately, use `[breaking-api-ok]` in a commit message or the
  `breaking-api-ok` PR label.
- **Both mobile apps generate their TypeScript types** from this file with
  `npm run api:types`. If the backend changes a field, `npm run typecheck`
  fails in the app, so you find out at compile time instead of from old data
  on a phone. `npm run api:check` fails if an app's generated types are stale.
- The Next web app has its own generated types in `src/types/api.ts`.

**The rule that makes a lagging app harmless: API changes are add-only.** Add
fields and endpoints. Never rename or remove anything while an installed app
build might still use it. This is the same expand/contract discipline as
[MIGRATION_SAFETY.md](MIGRATION_SAFETY.md). A mobile app that hasn't been
updated is then merely *missing a feature*, never *broken*.

## 3. Force update: the safety valve for old builds

Every first-party client now identifies itself with three headers:
`X-Client-App` (`customer-app` | `partner-app` | `web` | `admin-panel`),
`X-App-Version` and `X-App-Platform`. The Next proxy and the admin panel set the
first and last automatically.

- The apps call `GET /api/v1/app-config` on launch. Below
  `min_supported_version` they show a blocking **Update required** screen.
  Below `latest_version` they show a dismissible banner.
- The server also returns **426 `APP_UPDATE_REQUIRED`** for any call from an
  app below the minimum, so it holds even if the app skipped the check.
- Versions are set in the admin panel under **System Config** (e.g.
  `customer_app_android_min_version`), so no deploy is needed. The `version` in
  app.json is what gets compared, so bump it for every store build. OTA updates
  don't change it.
- Requests with no headers (old builds, legacy SPA) are never blocked by this,
  and the app check fails open if the endpoint is unreachable.

## 4. Vendors out of the customer app (server-enforced)

The client-side role checks stay. The server can now enforce the split too,
behind switches that are **all off by default**:

| Switch | Effect when on |
|---|---|
| `enforce_partner_app_for_vendors` | Vendor in the customer app → 403 `USE_PARTNER_APP`; regular buyer → `USE_WEB_PORTAL`. Applies at login, refresh, OTP login and on every authenticated call, so restored sessions are blocked too. |
| `enforce_partner_app_roles` | Non-vendors in the Partner app → `USE_CUSTOMER_APP` / `USE_WEB_PORTAL` |
| `require_client_app_header_for_vendors` | Vendor requests with no `X-Client-App` header → blocked. This closes the door on old customer-app builds. Turn it on last. |

Each one can be flipped in System Config, which takes effect within 60 seconds,
or through env vars. The apps show a screen with a store button for each error
code.

**Do these in order. Turning a switch on too early locks vendors out.** The full
runbook with rollbacks is in CLIENT_APPS_AND_VERSIONING.md §3.

1. Finish the Partner app, test a real vendor login on a device, and publish it
   on Play.
2. Merge `chore/remove-vendor-module` + `feat/api-contract-versioning` and
   release the customer app.
3. Deploy the backend and the Next app (both no-ops with switches off).
4. Set the store URLs and `customer_app_*_min_version`.
5. Turn on `enforce_partner_app_for_vendors`.
6. Once the legacy SPA is retired and old builds are gone, turn on
   `require_client_app_header_for_vendors`.

## 5. Parity report: what each client is missing

`python scripts/api_parity_report.py` scans every client repo and regenerates
[API_PARITY.md](API_PARITY.md). That file shows a matrix of endpoint × client,
the gaps by audience (e.g. "customer endpoint used by web but not the customer
app"), client calls to endpoints that no longer exist, and unused endpoints.

Don't try to keep mobile in lockstep. **Web leads and the apps follow.** Run
the report before each release and pick a batch of gaps for a mobile catch-up
sprint.

---

## Definition of done for a feature (solo-dev version)

- [ ] Backend change + unit tests; `openapi/openapi.json` regenerated and committed
- [ ] Add-only API change (or `[breaking-api-ok]` with a plan for old app builds)
- [ ] E2E step added to the relevant flow in `tests/e2e/`
- [ ] Manual-only parts added to MANUAL_QA_CHECKLIST.md
- [ ] Web (Next) done
- [ ] Mobile: done, **or** consciously deferred (it will show in the parity report)
- [ ] Staging: migrations applied, E2E run green, manual checklist done
- [ ] If a mobile release depends on new backend behaviour: raise `min_version` only after the store build is live

## Release routine

1. Merge into `dev` → CI green (unit, integration, contract, breaking-change).
2. `dev` → `staging`: apply migrations on staging, then `python scripts/run_e2e.py`
   and work through MANUAL_QA_CHECKLIST.md on the Vercel preview + staging app builds.
3. `staging` → `main` → prod. Optional: quick read-only smoke checks on prod.
4. Mobile: `npm run api:types && npm run typecheck`, then OTA (JS-only) or a store build.
5. Re-run the parity report and note the gaps you're deferring.

<!-- BEGIN RELATED: generated by backend/scripts/build_docs_hub.py from the header's `related:` -->

---

**Related:** [Staging end-to-end flow tests](E2E_TESTING.md) · [Manual QA checklist](MANUAL_QA_CHECKLIST.md) · [API parity report (generated)](API_PARITY.md) · [Client apps & versioning (force-update, Partner split)](CLIENT_APPS_AND_VERSIONING.md) · [Database migrations — workflow & safety](MIGRATION_SAFETY.md) · [Customer app — API contract, client headers, force-update](../../lubist_mobile_application/docs/API_CONTRACT.md)

**Referenced by:** [Backend local setup](../SETUP.md) · [Lubist docs hub](DOCS_HUB.md)

[↑ All docs](DOCS_HUB.md)

<!-- END RELATED -->
