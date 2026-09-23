# Incident: malformed salon ID returns 500 instead of 404

**Status: OPEN, not yet fixed.** Found 2026-09-23 while verifying the Better
Stack logging pipeline. Present in production at the time of writing.

Any request to a salon endpoint with a path ID that is not a valid UUID returns
**HTTP 500 Internal Server Error**. It should return 404 (or 422). This is the
first bug surfaced by the new logging pipeline, and it had been invisible.

## Reproduction

Against production (`https://lubist-p7aah.ondigitalocean.app`):

| Endpoint | malformed id (`not-a-uuid`) | valid UUID, absent |
|---|---|---|
| `GET /api/v1/salons/{id}` | **500** | 404 |
| `GET /api/v1/salons/{id}/related` | **500** | 404 |
| `GET /api/v1/salons/{id}/reviews` | **500** | 200 |
| `GET /api/v1/salons/{id}/services` | **500** | 404 |

Non-existent-but-well-formed UUIDs behave correctly. The fault is purely the
**format** of the ID.

## Root cause

The route declares the parameter as a plain string with no format validation
(`app/api/salons.py:147`, and the same on every other `{salon_id}` route):

```python
@router.get("/{salon_id}", response_model=SalonDetailResponse)
async def get_salon(
    salon_id: str,
```

That raw string is passed straight into a PostgREST filter against a `uuid`
column (`app/services/salon_service.py:223`):

```python
response = self.db.table("salons").select(select_query).eq("id", salon_id).execute()
```

Postgres rejects the comparison with `22P02 invalid input syntax for type
uuid`. That is not an `HTTPException`, so it falls through to the generic
handler (`app/services/salon_service.py:238-243`), which converts **any**
unexpected exception into a 500:

```python
except Exception as e:
    logger.error(f"Error fetching salon {salon_id}: {str(e)}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to fetch salon details"
    )
```

The captured production log line, with the BOM already stripped by the new VRL
transformation:

```
app.services.salon_service - ERROR - Error fetching salon does-not-exist-vrl-test:
{'code': '22P02', 'details': None, 'hint': None,
 'message': 'invalid input syntax for type uuid: "does-not-exist-vrl-test"'}
```

## Why it matters

- **It is reachable unauthenticated.** These are public salon endpoints, so
  anyone can trigger 500s at will.
- **It inflates the 5xx rate**, which is exactly the signal an alert should be
  built on. Left unfixed, crawler and bot traffic against stale links will make
  the error rate meaningless.
- **A 500 is the wrong contract.** Clients cannot distinguish "your input was
  malformed" from "our server is broken", so the web and mobile apps cannot
  render a sensible message.

## Scope

This is not confined to salons. The pattern — a user-supplied ID accepted as
`str` and passed into `.eq("id", ...)` — appears at **109 call sites** across
`app/services/`. Any endpoint taking an ID in the path is likely to behave the
same way. Salons is simply where it was first observed.

## Recommended fix

Two options, in preference order.

1. **Type the path parameters as `UUID`.** Changing `salon_id: str` to
   `salon_id: UUID` makes FastAPI reject malformed IDs with a 422 before any
   database call, for free and at the right layer. This needs a sweep across
   routes and a check that each service still receives the string form it
   expects (`str(salon_id)`).

2. **Translate `22P02` to 404 in the service layer.** Narrower and lower-risk,
   but it has to be repeated at every call site, so it treats the symptom.

Option 1 is the real fix. It touches many routes, so it wants a deliberate pass
and a test per affected endpoint rather than a blind find-and-replace — which
is why this is filed rather than patched.

## Note on detection

Before 2026-09-23 this produced no usable signal: `HTTPException` was raised
without being logged (see `docs/OBSERVABILITY.md`), so the 500 appeared in
Better Stack only as an uncorrelated uvicorn access line. The service-layer
`logger.error` above was the one reason it was traceable at all.
