# Observability: Better Stack logging

How production logs reach Better Stack, what was wrong with the setup, and how
to query them. Written 2026-09-23.

## Current setup

| | |
|---|---|
| Source | `lubist` (id `1751804`, team `506833`) |
| Platform | `digitalocean` — App Platform forwards stdout over RFC 5424 syslog |
| Region | `eu-central-1a` |
| Log table | `t506833_lubist_logs` |
| Metrics table | `t506833_lubist_metrics` |
| **Log retention** | **3 days** |
| Metrics retention | 30 days |
| Ingesting | active (`ingesting_paused: false`) |

Read access is via the **SQL API** only. The older REST query endpoints
(`/api/v1/query`, `/api/v2/query/live-tail`) have been removed and now return
404 — any guide referencing them is out of date.

## What was wrong

Four problems, in the order they hurt.

### 1. Errors were logged nowhere

`app_exception_handler` and `http_exception_handler` in `app/core/handlers.py`
built a JSON response and returned it without logging anything. Every
`HTTPException` and `AppException` the codebase raises — which is how nearly all
deliberate failures are expressed — produced **zero log output**. Only the
catch-all `general_exception_handler` logged.

This was confirmed against live data: in the first 30 minutes of ingestion,
across 521 log lines of real traffic, there were **zero ERROR lines** and a
single WARNING. That is not a healthy service; it is a blind one.

### 2. Every line arrives tagged `info`

The syslog wrapper sets `level` on every event, and it is always `"info"` —
the application's real severity was buried inside the message string:

```
INFO - <- GET /api/v1/vendors/coupons - 200 - 229.08ms
```

Query result over all ingested data at the time of writing:

| syslog level | real level | lines |
|---|---|---|
| info | INFO/other | 520 |
| info | WARNING | 1 |

So **filtering or alerting by severity in Better Stack was impossible.**

### 3. Logs were unstructured text

The production formatter was
`"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`. Better Stack indexes
fields, not prose, so there was no way to query `status_code:500`, group by
endpoint, or chart an error rate.

### 4. No correlation between lines

Each request produced separate inbound/outbound lines with nothing linking
them, and no user or request identifier. A report of "it failed around 3pm" had
no thread to pull.

## What changed in the code

- **`app/core/request_context.py`** (new) — a `ContextVar` holding a per-request
  correlation ID, so service-layer code can log with the right ID without
  threading `Request` through every call.
- **`app/core/logging.py`** — added `JsonFormatter`, which emits one JSON object
  per line outside development and promotes anything passed via `extra={...}`
  to a top-level field. Development keeps the existing human-readable output.
  No new dependency; it is stdlib `json`.
- **`app/core/middleware.py`** — `LoggingMiddleware` now mints (or honours an
  upstream) `X-Request-ID`, echoes it on the response, and logs one structured
  completion line per request carrying `method`, `path`, `status_code`,
  `duration_ms` and `client_ip`. Requests over `SLOW_REQUEST_MS` (2s) or
  returning 5xx are logged at WARNING. The old inbound `->` line dropped to
  DEBUG, halving ingest volume for no loss of signal.
- **`app/core/handlers.py`** — every handler now logs. Severity is mapped by
  status: 5xx at ERROR with a traceback, 404 at INFO (crawlers make a constant
  background of them), other 4xx at WARNING. Error responses carry the
  `X-Request-ID` header so support can quote it.

Verified: 634 tests pass, every emitted line parses as JSON, correlation IDs
propagate across a request's lines, and upstream-supplied IDs are honoured.

One duplication was found and fixed during verification: Starlette's
`ServerErrorMiddleware` wraps our middleware, so an unhandled exception was
logged twice with two full tracebacks. The middleware now logs the timing
without `exc_info`; `general_exception_handler` owns the traceback. The two
lines are joined by `request_id`.

## The BOM problem (fixed 2026-09-23)

**This would have silently prevented the structured logging above from working.**

RFC 5424 prefixes a UTF-8 `MSG` with a byte-order mark, and DigitalOcean's
forwarder does exactly that. Measured against live data: **521 of 521 messages
begin with `EF BB BF`.**

A BOM before `{` makes the line invalid JSON, so Better Stack's parser will
fail on the new structured logs and `message_json.*` will stay empty — the
fields would silently never appear.

The fix belongs in the source's **VRL transformation** (currently empty), not in
the app, because the BOM is added by the transport. Proposed transformation:

```vrl
# DigitalOcean forwards over RFC 5424 syslog, which prefixes the UTF-8 MSG with
# a BOM. Strip it so the JSON the application emits can be parsed.
if is_string(.message) {
    .message = replace(string!(.message), "\u{FEFF}", "")

    parsed, err = parse_json(.message)
    if err == null && is_object(parsed) {
        # Promotes level, request_id, status_code, path, duration_ms, etc. to
        # top-level fields. Non-JSON lines (uvicorn access logs) fall through
        # unchanged, minus the BOM.
        . = merge(., object!(parsed))
        if exists(.level) {
            .level = downcase(string!(.level))
        }
    }
}
```

**Applied** to source `1751804` via
`PATCH /api/v1/sources/1751804` (field: `vrl_transformation_logs`), and verified
against live traffic: in the minute spanning the change, 42 of 58 rows carried a
BOM and the newest 16 did not.

To change it later, edit the source's VRL in the Better Stack UI, which previews
against real events before saving. Note the field is `vrl_transformation_logs`,
not `vrl_transformation`.

## Uptime monitoring (added 2026-09-23)

Before this, the Uptime side of the account had exactly one monitor:
`google.com`, **paused since 2026-05-31**. Nothing watched the Lubist backend,
which is the real reason no incident had ever been raised.

Monitor `4967543` now watches production:

| | |
|---|---|
| URL | `https://lubist-p7aah.ondigitalocean.app/health` |
| Type | `keyword` matching `healthy` |
| Frequency | every 180s, 15s timeout |
| Confirmation / recovery | 60s / 180s |
| Regions | eu, us, as |
| Alerting | email |

Keyword rather than status code on purpose: a 200 with a broken body should
still raise an incident. `/health` returns a minimal body in production, so it
is safe to expose.

Note: `recovery_period` and `confirmation_period` only accept
`[0, 60, 180, 300, 900, 1800, 3600, 7200]`; other values are rejected with 422.

## Querying logs

Use `scripts/betterstack_query.py`. It reads credentials from
`.betterstack.env` in the repo root (gitignored; never commit it).

```bash
python scripts/betterstack_query.py --schema          # table columns
python scripts/betterstack_query.py --sample 20       # most recent rows
python scripts/betterstack_query.py --errors --hours 24
python scripts/betterstack_query.py --endpoints --hours 24
python scripts/betterstack_query.py --sql "SELECT count() FROM {table}"
```

`{table}` expands to `remote(t506833_lubist_logs)`.

### Gotcha: the documented URL parameter breaks the API

Better Stack's own docs show:

```
POST https://<region>-connect.betterstackdata.com?output_format_pretty_row_numbers=0
```

That parameter causes a **pre-auth HTTP 500** — `{"exception":"Failed to
connect: fetch failed"}` — which looks exactly like a credential failure and is
not. Omit it; use a `FORMAT` clause instead. The script already does.

Distinguishing the failures:

| Response | Meaning |
|---|---|
| 403 `AUTHENTICATION_FAILED` | username/password wrong |
| 500 `Failed to connect: fetch failed` | the bad URL param, **or** a connection still provisioning |

A newly created SQL API connection takes a few minutes to become usable, and
returns the 500 in the meantime.

## Findings so far

- `docs/INCIDENT_salon_id_500.md` — any non-UUID salon ID returns 500 instead of
  404, on every public salon endpoint, unauthenticated. Found within minutes of
  the pipeline working. **Open.**

## Retention caveat

Logs are kept **3 days**. Any incident investigation must pull the evidence out
within that window, or it is gone. Incident write-ups should quote the relevant
log lines inline rather than linking to Better Stack.

## Security note

The Telemetry API's `/api/v1/sources` response includes the source's **ingest
token** in plaintext. Treat that endpoint's output as a secret; anyone holding
that token can write logs into the source.
