# Incident: malformed salon ID returns 500 instead of 404

**Status: FIXED on `dev`, 2026-09-23. Not yet deployed to production.**
Found 2026-09-23 while verifying the Better Stack logging pipeline; fixed the
same day. This was the first bug surfaced by the new logging pipeline, and it
had been invisible before it.

Any request to a salon endpoint with a path ID that was not a valid UUID
returned **HTTP 500 Internal Server Error**. It now returns 422, rejected at the
routing layer before any database call.

## Reproduction

Against production (`https://lubist-p7aah.ondigitalocean.app`):

| Endpoint | malformed id (`not-a-uuid`) | valid UUID, absent |
|---|---|---|
| `GET /api/v1/salons/{id}` | **500** → now 422 | 404 |
| `GET /api/v1/salons/{id}/related` | **500** → now 422 | 404 |
| `GET /api/v1/salons/{id}/reviews` | **500** → now 422 | 200 |
| `GET /api/v1/salons/{id}/services` | **500** → now 422 | 404 |

Non-existent-but-well-formed UUIDs always behaved correctly. The fault was
purely the **format** of the ID.

## Root cause

The route declared the parameter as a plain string with no format validation
(`app/api/salons.py`, and the same on every other `{salon_id}` route):

```python
@router.get("/{salon_id}", response_model=SalonDetailResponse)
async def get_salon(
    salon_id: str,
```

That raw string was passed straight into a PostgREST filter against a `uuid`
column (`app/services/salon_service.py:223`):

```python
response = self.db.table("salons").select(select_query).eq("id", salon_id).execute()
```

Postgres rejected the comparison with `22P02 invalid input syntax for type
uuid`. That is not an `HTTPException`, so it fell through to the service's
generic handler, which converts **any** unexpected exception into a 500:

```python
except Exception as e:
    logger.error(f"Error fetching salon {salon_id}: {str(e)}")
    raise HTTPException(status_code=500, detail="Failed to fetch salon details")
```

The captured production log line, with the BOM already stripped by the new VRL
transformation:

```
app.services.salon_service - ERROR - Error fetching salon does-not-exist-vrl-test:
{'code': '22P02', 'details': None, 'hint': None,
 'message': 'invalid input syntax for type uuid: "does-not-exist-vrl-test"'}
```

## Why it mattered

- **It was reachable unauthenticated.** These are public salon endpoints, so
  anyone could trigger 500s at will.
- **It inflated the 5xx rate**, which is exactly the signal an alert should be
  built on. Left unfixed, crawler and bot traffic against stale links would have
  made the error rate meaningless.
- **A 500 is the wrong contract.** Clients could not distinguish "your input was
  malformed" from "our server is broken".

## The fix

`app/core/validators.py` holds the shared types; the sweep applies them. The
declared types stay `str` rather than `uuid.UUID` deliberately, so services keep
receiving exactly the string they always received — no `str(...)` conversions at
any service boundary, which is what made a 59-route sweep safe to do at once.

### 1. Path parameters — 59 routes, 18 files

Every path parameter that reaches a `uuid` column is now `UUIDPath` instead of
`str`. FastAPI rejects a malformed id with 422 before the handler body runs.

Seven path parameters were deliberately left as `str`, because they are text
keys, not UUIDs: `config_key` (`system_config.config_key`), `key`
(`feature_flags.key`), `slug` (blog and product), and `document_type`.

### 2. Query parameters

- `GET /salons/{id}/available-slots?service_ids=` — public, and the one case
  that was an *uncaught* 500 rather than a service-converted one: the route
  splits the CSV and passes it into `.in_("id", ...)` with no try/except above
  it. Now `uuid_csv_query`, which still accepts an empty list and empty members
  (a frontend with nothing selected sends `?service_ids=`).
- `GET /admin/coupons?salon_id=` — now `uuid_query`.

### 3. Request bodies

UUID fields on request schemas are now `UUIDStr` (required) or
`BlankableUUIDStr` (optional). `BlankableUUIDStr` maps `""` to `None` rather
than rejecting it, because `category_id=""` alongside a typed `category_name`
resolves by name and **succeeds today** — `ServiceTaxonomy.resolve_fields` lets
a name win over an id. Rejecting `""` outright would have broken a working path.

Left as plain `str`, because they are not UUIDs: `razorpay_order_id` /
`razorpay_payment_id` (Razorpay references) and `verification_id`
(MessageCentral).

### 4. The same fault on enum columns

The sweep turned up a second family. Postgres reports an unknown enum label as
`invalid input value for enum <type>`, which is **also SQLSTATE 22P02**, so an
unvalidated `?status=` filter passed into `.eq("status", ...)` produced a 500 in
exactly the same way. Five routes were affected:

| Route | parameter | enum |
|---|---|---|
| `GET /admin/bookings/` | `status` | `booking_status` |
| `GET /admin/users/` | `role` | `user_role` |
| `GET /admin/vendor-requests` | `status_filter` | `request_status` |
| `GET /rm/vendor-requests` | `status_filter` | `request_status` |
| `GET /vendors/bookings` | `status_filter` | `booking_status` |

Each is now a `Literal` of the labels in the schema, blank-tolerant so
`?status=` still means "no filter". The careers, partner and blog `status`
filters were checked and are safe — those columns are `text`.

**This was live.** The admin panel's Appointments page offered an "In Progress"
status filter, but `booking_status` has no `in_progress` label and the backend
has no such state anywhere — selecting it returned a 500. The option and its
constant were removed (`salon-admin-panel/src/config/constants.js`,
`src/pages/Appointments.jsx`).

### 5. Backstop

`app.core.handlers.general_exception_handler` maps an uncaught 22P02 to a 400
with `error_code: INVALID_IDENTIFIER`, so anything that still reaches Postgres
with a malformed value degrades to a 4xx. It answers 400 rather than 422
deliberately: a 422 is the contract working, whereas an `INVALID_IDENTIFIER`
400 means a value got past every declared check and marks a validation gap worth
finding. Alert on it.

Note its limit: it only sees what reaches it *uncaught*. A service that wraps
the call in `except Exception` and raises its own `HTTPException(500)` — which
most of them do — still returns 500. The routing-layer types are what actually
close the hole.

## Tests

`tests/test_uuid_validation.py`, smoke tier — no Supabase stack needed, which is
itself the proof that rejection now happens before any database call.

- `test_every_id_path_param_is_uuid_validated` — introspects the live app and
  fails if any `{...id}` path parameter lacks the UUID pattern. **This is the
  guard that keeps it fixed:** a new route declaring `salon_id: str` reopens the
  incident silently, because nothing else goes red until production logs a 500.
- `test_enum_filters_publish_their_allowed_values` — the same guard for the enum
  filters, checked through the OpenAPI document.
- `test_enum_filter_labels_match_the_database_schema` — parses the `CREATE TYPE`
  statements in `db-schema/current_schema.sql` and fails if the Literals have
  drifted, so a migration that adds a label cannot silently make it a 422.
- `test_no_id_route_returns_5xx_for_a_malformed_id` — walks every id-taking
  route and asserts none answers 5xx.
- The reproduction table above, as parametrized cases.

All were confirmed to fail against the unfixed code before being kept: reverting
`get_salon` to `salon_id: str` reproduces the original log line
(`Error fetching salon not-a-uuid` → `HTTPException 500`) and turns three tests
red.

Suite: 680 passed, 26 skipped (integration tier, no local stack).
Admin panel: 147 passed.

## Note on detection

Before 2026-09-23 this produced no usable signal: `HTTPException` was raised
without being logged (see `docs/OBSERVABILITY.md`), so the 500 appeared in
Better Stack only as an uncorrelated uvicorn access line. The service-layer
`logger.error` above was the one reason it was traceable at all.

## Follow-up

- Deploy: this is on `dev` and needs the usual `dev → staging → main` chain to
  reach production, along with the structured logging it was found by.
- Once deployed, `error_kind: invalid_identifier` in Better Stack should stay at
  zero. Anything there is a validation gap.
