# Client Apps & Versioning

How Lubist's clients identify themselves to the backend, how we force outdated
mobile builds to update, how vendor accounts are moved into the Lubist Partner
app, and the rules that keep the API compatible with builds already on phones.

Code: `app/core/client_app.py` (policy, middleware, role rules),
`app/api/app_config.py` (endpoint). Tests: `tests/test_client_app_mocked.py`,
`tests/test_check_api_breaking.py`.

---

## 1. The contract

### Request headers (sent by every first-party client)

| Header | Values | Sent by |
| --- | --- | --- |
| `X-Client-App` | `customer-app` \| `partner-app` \| `web` \| `admin-panel` | all clients |
| `X-App-Version` | semver of the native build, e.g. `1.4.2` | native apps only (from `Constants.expoConfig.version`) |
| `X-App-Platform` | `ios` \| `android` \| `web` | all clients |

Values are case-insensitive. An unrecognised `X-Client-App` is treated exactly
like a missing one.

Who sets them:

- **Customer app / Partner app** - every API call.
- **Next.js web app** (`salon_management_next`) - the `/api/backend` proxy sets
  `X-Client-App: web` + `X-App-Platform: web` on every forwarded request,
  overwriting anything the browser sent (a page script cannot pose as a native
  app) and stripping `X-App-Version`. Server-side calls (`src/lib/http.ts`: BFF
  auth routes, token refresh, RSC fetches) send the same two headers. Source:
  `clientIdentityHeaders` in `src/config/site.ts`.
- **Admin panel** - `X-Client-App: admin-panel`, `X-App-Platform: web` on the
  RTK axios instance and the direct auth calls (`src/services/api/clientHeaders.js`).
- **Legacy SPA (salon-management-app)** - sends nothing. See the strict-mode
  precondition in the runbook.

CORS: `app/core/middleware.py` uses `allow_headers=["*"]`, which Starlette
answers by echoing the requested headers, so these pass preflight (covered by
`test_cors_preflight_allows_client_headers`). If that list is ever narrowed,
add the three headers.

### `GET /api/v1/app-config`

Public, no auth, cached (one `system_config` read per process per
`CLIENT_POLICY_CACHE_SECONDS`, default 60; response carries
`Cache-Control: public, max-age=60` and `Vary` on the three headers). Exempt from
the 426 gate - it is how an outdated build learns it is outdated.

```
GET /api/v1/app-config?client_app=customer-app&platform=android&version=1.4.2
```

Query params win; each falls back to the matching header. Response `200`:

```json
{
  "success": true,
  "client_app": "customer-app",
  "platform": "android",
  "current_version": "1.4.2",
  "min_supported_version": "1.2.0",
  "latest_version": "1.5.0",
  "update_required": false,
  "update_available": true,
  "store_url": "https://play.google.com/store/apps/details?id=...",
  "message": null
}
```

- `update_required` = `current_version < min_supported_version`
- `update_available` = `current_version < latest_version`
- No policy configured -> the version fields, `store_url` and `message` are `null`
  and both booleans `false`.
- No / unparseable `version` -> `current_version` echoes what was sent (or `null`),
  both booleans `false`.
- Unknown or missing `client_app` (only `customer-app` / `partner-app` are valid
  here) -> `422 {"message": "client_app must be one of: ...", "error_code": "INVALID_CLIENT_APP"}`.
- Unknown or missing `platform` (only `ios` / `android`) -> `422`, `error_code: "INVALID_PLATFORM"`.

The mobile apps fail open: a 404 (backend not yet deployed) or timeout on this
endpoint means "carry on".

### Global enforcement: `426 APP_UPDATE_REQUIRED`

`ClientVersionMiddleware` (pure ASGI, innermost, so the 426 still carries CORS
headers and an `X-Request-ID`) blocks a request when ALL of these hold:

1. `X-Client-App` is `customer-app` or `partner-app`;
2. `X-App-Platform` is `ios` or `android`;
3. `X-App-Version` is present and parses;
4. that app + platform has a `min_version` configured and it parses;
5. version < min;
6. the path is not exempt: `/health`, `/health/*`, `/`, `/api/v1/app-config`
   (and `OPTIONS` preflights).

```json
HTTP 426
{"success": false, "message": "<customer_app_update_message or default>",
 "error_code": "APP_UPDATE_REQUIRED", "errors": null,
 "min_supported_version": "1.5.0", "store_url": "https://..."}
```

(`min_supported_version` / `store_url` are additive extras; clients only rely on
`message` + `error_code`.)

Never blocked: requests with no/unknown headers (web, admin panel, every build
shipped before this existed, curl), a missing platform or version, and an
unparseable version on either side (logged as a warning - a parse bug or an
admin typo must not lock users out). If the policy cannot be read from the DB the
middleware fails OPEN. Header-less requests never touch the policy at all.

Versions: `MAJOR[.MINOR[.PATCH]][-prerelease][+build]`, optional leading `v`;
missing parts are 0; numeric compare (`1.4.10 > 1.4.9`); a prerelease sorts
before its release (`1.5.0-beta.1 < 1.5.0`); build metadata is ignored.

### Role rules: which accounts may use which app

| Rule | Switch (env / system_config) | Effect |
| --- | --- | --- |
| Vendors out of the customer app | `ENFORCE_PARTNER_APP_FOR_VENDORS` / `enforce_partner_app_for_vendors` | `vendor` + `X-Client-App: customer-app` -> `403 {"message": "Salon partner accounts use the Lubist Partner app.", "error_code": "USE_PARTNER_APP"}`. `regular_buyer` + `customer-app` -> `403 error_code: "USE_WEB_PORTAL"` ("Business buyer accounts are managed on the Lubist website ...") |
| Partner app is vendor-only | `ENFORCE_PARTNER_APP_ROLES` / `enforce_partner_app_roles` | `X-Client-App: partner-app` + any role other than `vendor` -> `403 USE_CUSTOMER_APP`; `regular_buyer` gets `USE_WEB_PORTAL` instead |
| Strict: vendors must identify their app | `REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS` / `require_client_app_header_for_vendors` | `vendor` with no (or an unrecognised) `X-Client-App` -> `403 USE_PARTNER_APP`; `regular_buyer` -> `403 USE_WEB_PORTAL` |

All three default **off**. `web` and `admin-panel` are never blocked by any rule.
Customers, admins and RMs are only ever affected by the partner-app rule.

**Where it is enforced**

- Every token-issuing endpoint, after the tokens are minted but before they are
  returned: `POST /auth/login`, `/auth/signup`, `/auth/refresh`,
  `/auth/login/phone/verify-otp`, `/auth/password-reset/confirm`,
  `/vendors/complete-registration`. For password-reset/confirm and
  complete-registration the side effect (new password / new account) has already
  happened - the rule only withholds the auto-login tokens.
- `get_current_user` (`app/core/auth.py`), so a session restored from storage is
  refused too, on every authenticated endpoint. Exempt: `/auth/logout` and
  `/auth/logout-all`, so a blocked user can still end the session cleanly.
- NOT in `get_optional_user`: on public endpoints a blocked user is simply
  treated as anonymous (that dependency swallows auth errors by design).

**Decision: `regular_buyer` is not a Partner-app role.** Regular buyers are
onboarded by an RM, complete registration via an emailed link that opens the
website, and buy products on the website (docs/REGULAR_BUYER_WORKFLOW.md). The
Partner app (`lubist_vendor_application`) only routes `role === 'vendor'` and
rejects everything else at login. So they are kept out of both native apps and
pointed at the website with `USE_WEB_PORTAL`. Revisit if the Partner app ever
grows a buyer flow (add `regular_buyer` to `PARTNER_APP_ROLES` and drop it from
the `USE_WEB_PORTAL` branches).

---

## 2. Configuration

### Settings (`app/core/config.py`, all with defaults - no env change needed)

| Env var | Default | |
| --- | --- | --- |
| `ENFORCE_PARTNER_APP_FOR_VENDORS` | `False` | see role rules |
| `ENFORCE_PARTNER_APP_ROLES` | `False` | see role rules |
| `REQUIRE_CLIENT_APP_HEADER_FOR_VENDORS` | `False` | see role rules |
| `CLIENT_POLICY_CACHE_SECONDS` | `60` | per-process cache of the policy + flag overrides |

**Runtime override (no redeploy):** each flag can also be set through a
`system_config` row with the lower-case name. If the row exists, is active, and
its value is a boolean (`true/false/1/0/yes/no/on/off`), it wins over the env var
**in both directions** - so a `false` row is also the instant rollback for an env
var set to `true`. Delete the row (or deactivate it) to fall back to the env var.
An unreadable value logs a warning and falls back to env.

Admin-panel edits invalidate the cache immediately on the instance that served
the edit; other instances/workers see it within `CLIENT_POLICY_CACHE_SECONDS`.

### `system_config` keys (no migration - existing table)

All registered in `AVAILABLE_SYSTEM_CONFIGS`, so they appear in the admin panel
under **System Config -> Add** (served by `GET /api/v1/admin/config/available-keys`).
`config_value` is `NOT NULL`, so "unset" = no row, an empty string, or `is_active = false`.

| Key | Type | Meaning |
| --- | --- | --- |
| `customer_app_android_min_version` | string | builds below get 426 |
| `customer_app_android_latest_version` | string | builds below see "update available" |
| `customer_app_android_store_url` | string | Play Store link |
| `customer_app_ios_min_version` / `_latest_version` / `_store_url` | string | same for iOS |
| `customer_app_update_message` | string | optional text for the prompt and the 426 |
| `partner_app_android_min_version` / `_latest_version` / `_store_url` | string | Partner app, Android |
| `partner_app_ios_min_version` / `_latest_version` / `_store_url` | string | Partner app, iOS |
| `partner_app_update_message` | string | optional |
| `enforce_partner_app_for_vendors` | boolean | override of the env flag |
| `enforce_partner_app_roles` | boolean | override of the env flag |
| `require_client_app_header_for_vendors` | boolean | override of the env flag |

Setting a value: admin panel -> **System Config** -> **Add configuration** -> pick
the key -> enter the value (e.g. `1.5.0`, or `true`) -> save. Change it later
with the edit button. Or via API: `POST /api/v1/admin/config`
`{"config_key": "customer_app_android_min_version", "config_value": "1.5.0", "config_type": "string"}`,
then `PUT /api/v1/admin/config/{key}` `{"config_value": "1.6.0"}`.

**Before raising a `min_version`, check the version string** - it is what
`Constants.expoConfig.version` reports (the app.json `version`), not the
build number / versionCode. OTA (EAS Update) releases do not change it, so a
min-version bump forces a store update, never an OTA.

---

## 3. Rollout runbook: the vendor split

Do these in order. Each step is safe to stop at, and each has a rollback.

| # | Step | How | Rollback |
| --- | --- | --- | --- |
| 0 | Deploy this backend | normal dev -> staging -> main | Revert the deploy. With all flags off and no policy rows it is a no-op (see section 5). |
| 1 | Finish the Partner app | `lubist_vendor_application`; it sends the headers | n/a |
| 2 | Release the Partner app to the stores; set `partner_app_*_store_url` and `partner_app_*_latest_version` | store consoles, then admin panel | Unpublish / halt rollout. Delete the rows. |
| 3 | Release the customer app built from the vendor-removal branch (sends headers, handles `USE_PARTNER_APP` / `USE_WEB_PORTAL` / 426) | store consoles | Halt the staged rollout in the store console. |
| 4 | Set `customer_app_{android,ios}_min_version` to the step-3 version, with `_store_url` and optionally `customer_app_update_message` | admin panel | Delete the min_version row (or set it to empty). Effective within 60 s. |
| 5 | Turn on the vendor block: `enforce_partner_app_for_vendors = true` (or env `ENFORCE_PARTNER_APP_FOR_VENDORS=true` + redeploy) | admin panel | Set the row to `false` (wins over env), or delete it. |
| 5b | Optional: `enforce_partner_app_roles = true` once the Partner app is stable | admin panel | `false` / delete. |
| 6 | Strict mode: `require_client_app_header_for_vendors = true` | admin panel | `false` / delete. |

Preconditions for step 4: the step-3 build is live in both stores (otherwise
users are told to update to a version they cannot download). Check that the
step-3 build actually sends `X-App-Version` (look for it in the Better Stack
request logs).

Preconditions for step 6 (strict mode), all of them:

- the Next web app with the identity headers is in production (vendors on the
  web would otherwise be locked out);
- the legacy SPA is retired for vendors, or sends `X-Client-App: web` - it
  currently sends nothing;
- the Partner app build in the stores sends the headers;
- no scripts / integrations call the API as a vendor without the header.

Why strict mode exists: customer-app builds released before the headers cannot
be identified, so neither the 426 gate nor the step-5 block can reach them. The
only way to keep vendors out of those builds is to refuse vendor traffic that
does not identify itself. Customers on old builds are unaffected by it.

---

## 4. API compatibility rules

Native builds stay installed for months. Every build at or above the minimum
supported version must keep working against the current backend.

1. **Add, don't change.** New endpoints, new optional request fields and new
   response fields are always safe. Clients must ignore unknown response fields.
2. **Never remove or rename** a path, method, or response field, never change a
   field's type (including making a response field nullable), never make an
   input newly required, and never narrow the accepted values of an input -
   while any supported build may use it.
3. **Expand / migrate / contract** for anything that must change - the same
   pattern docs/MIGRATION_SAFETY.md uses for the schema:
   - *expand*: add the new field/endpoint alongside the old; serve both;
   - *migrate*: ship app builds that use the new one; raise `min_version` past
     the last build that uses the old one;
   - *contract*: only then remove the old one (with the override below).
4. Error contract: `{message, error_code}` from `AppException`. New
   `error_code`s are additive; clients fall back to showing `message`.
5. Schema changes follow docs/MIGRATION_SAFETY.md; the API rule above is its
   client-facing twin.

### How CI enforces it (`.github/workflows/ci.yml`, smoke-build job)

1. **Contract is current**: `python scripts/export_openapi.py --check` fails if
   `openapi/openapi.json` does not match the code. Fix:
   `python scripts/export_openapi.py` and commit the file. (The mobile apps
   generate their API types from it.)
2. **No breaking changes**: `python scripts/check_api_breaking.py --base-ref origin/<base branch>`
   diffs the committed contract against the PR base branch's copy (pure Python,
   stdlib only) and fails on: removed paths or methods; a removed 2xx status;
   removed 2xx response fields; response field type changes or widening (e.g.
   `string -> string|null`); newly-required request fields, parameters or bodies;
   request types or enum values narrowed. Renaming a path parameter is not a
   break. If the base branch has no contract yet, the check passes.

   Run locally: `python scripts/check_api_breaking.py --base-ref origin/staging`
   (after `git fetch`), or `--base-file old.json [--head-file new.json]`.

   **Override** for an intentional break (step 3 *contract* above): put
   `[breaking-api-ok]` in any commit message on the branch, or add the PR label
   `breaking-api-ok` and re-run the job (labels are read at run time), or set
   `API_BREAKING_OK=1`. The report is still printed for the reviewer.

---

## 5. What happens the moment this deploys (all flags off, no rows)

- Requests without `X-Client-App` (every current client: web, admin panel,
  existing app builds): the middleware does one header lookup and passes through.
  No DB read. Role rules: `get_current_user` only consults the policy for
  `vendor`/`regular_buyer` accounts or `partner-app` requests; with no rows the
  flags resolve to the env defaults (all `False`), so nothing is blocked. The
  cost is one cached `system_config` read per process per minute while vendors
  are active.
- Requests with headers but no `min_version` rows: no 426.
- `GET /api/v1/app-config` is new; returns nulls/false until rows are set.
- The DB being unreachable for the policy read: fails open (no 426, env flags).
