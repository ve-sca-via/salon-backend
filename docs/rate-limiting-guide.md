# Rate Limiting Guide

## Overview

Rate limiting is implemented using **SlowAPI** (FastAPI wrapper around Flask-Limiter) with a two-layer approach:

1. **Global SlowAPI middleware** - Client IP-based throttling
2. **Route-level decorators** - Specific limits on sensitive endpoints
3. **Service-level throttling** - Rate limiting at the service level (e.g., Geocoding, OTP)

---

## Current Setup

### Global Configuration
- **Backend**: In-memory storage (fixed-window strategy)
- **Key**: Client IP address
- **Default limit**: 100 requests/minute
- **Initialization**: `app/core/rate_limit.py` (loaded in `main.py` and `app/core/middleware.py`)

### Route-Level Limits (Authentication Endpoints)

**Email-based auth** (`app/api/auth.py`):
- Login: **5 requests/minute**
- Signup: **3 requests/minute**
- Password reset: **3 requests/hour**
- Token refresh: **10 requests/minute**
- Resend verification email: **3 requests/hour**

**Phone/OTP auth** (`app/api/auth.py`):
- OTP send (signup/login/verification): **5 requests/minute**
- OTP verify: **5 requests/minute**

**Other endpoints** (`app/api/*.py`):
- Booking create: **20 requests/minute**
- Payment create: **10 requests/minute**
- File upload: **10 requests/minute**
- Read-heavy: **60 requests/minute**
- Read-light: **100 requests/minute**
- Public API: **30 requests/minute**

### Service-Level Rate Limiting

**Geocoding** (`app/services/geocoding.py`):
- Uses Nominatim (OpenStreetMap) which enforces **1 request/second**
- Rate limiting is built-in (enforced in `_rate_limit()` method)

**OTP Service** (`app/services/otp_service.py`):
- Respects MessageCentral API rate limits
- Returns 429 errors from upstream API

---

## How to Configure

### 1. Modify Global Default (All Endpoints)
Edit `app/core/rate_limit.py`:
```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    strategy="fixed-window",
    default_limits=["100 per minute"]  # ← Change here
)
```

### 2. Add/Modify Route-Level Limits
In endpoint files (e.g., `app/api/auth.py`):
```python
@router.post("/login", response_model=...)
@limiter.limit("10/minute")  # ← Change this value
async def login(credentials: LoginSchema):
    ...
```

**Limit Format**: `"<count>/<period>"` where period can be:
- `second`
- `minute` (most common)
- `hour`
- `day`


### 3. Service-Level Rate Limiting
**Geocoding**: Edit `_rate_limit()` in `app/services/geocoding.py`:
```python
self._rate_limit_delay = 1.0  # seconds between requests (Nominatim requires 1.0)
```

---

## Response Format (429 - Too Many Requests)

When rate limit is exceeded, clients receive:
```json
{
  "detail": "429 Too Many Requests: 5 per 1 minute"
}
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `app/core/rate_limit.py` | Global SlowAPI setup & limit buckets |
| `app/core/middleware.py` | Middleware registration (line 79-80) |
| `app/core/handlers.py` | 429 error handler (line 105-111) |
| `app/api/auth.py` | Route decorators on auth endpoints |
| `app/services/geocoding.py` | Service-level throttling for Nominatim |
| `main.py` | SlowAPI initialization (line 46-49) |

---

## Notes

- **Client detection**: Based on client IP (set by `get_remote_address()`)
- **Storage**: In-memory (resets on app restart)
- **No persistence**: Limits are not persisted across server restarts
- **For production**: Consider implementing Redis storage for distributed rate limiting

For detailed configuration or to implement Redis-backed rate limiting, see SlowAPI documentation.
