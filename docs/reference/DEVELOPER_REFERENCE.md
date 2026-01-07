# Developer Quick Reference

**Last Updated:** December 11, 2025

---

## 🎯 Essential Commands

```powershell
# Development
.\run-local.ps1              # Start local dev server
.\run-staging.ps1            # Test with staging DB
.\run-production.ps1         # Production (careful!)

# Testing
pytest                       # Run all tests
pytest -v                    # Verbose
pytest --cov                 # With coverage
pytest tests/test_auth.py    # Specific file

# Database
supabase start               # Start local DB
supabase stop                # Stop local DB
supabase status              # Check status
supabase db push             # Apply migrations
supabase db reset            # Reset (wipes data!)
```

---

## 🔑 Environment Variables

### Core (Required)
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Admin key (bypasses RLS)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - Min 32 characters, random

### Payments
- `RAZORPAY_KEY_ID` - Razorpay API key
- `RAZORPAY_KEY_SECRET` - Razorpay secret

### Email (Optional)
- `EMAIL_ENABLED` - `true` to send emails
- `SMTP_HOST` - SMTP server (default: smtp.gmail.com)
- `SMTP_PORT` - SMTP port (default: 587)
- `SMTP_USER` - SMTP username
- `SMTP_PASSWORD` - SMTP password / app password

---

## 📁 Project Structure

```
app/
├── api/              # API routes (138 endpoints)
│   ├── auth.py       # Auth endpoints
│   ├── customers.py  # Customer endpoints
│   ├── vendors.py    # Vendor endpoints
│   ├── rm.py         # RM endpoints
│   ├── salons.py     # Public salon endpoints
│   ├── bookings.py   # Booking endpoints
│   ├── payments.py   # Payment endpoints
│   ├── careers.py    # Career endpoints
│   ├── upload.py     # File upload
│   ├── location.py   # Geocoding
│   ├── realtime.py   # WebSocket
│   └── admin/        # Admin endpoints (40+)
│       ├── dashboard.py
│       ├── users.py
│       ├── salons.py
│       ├── services.py
│       ├── staff.py
│       ├── bookings.py
│       ├── rms.py
│       ├── vendor_requests.py
│       └── config.py
├── core/             # Core functionality
│   ├── config.py     # Settings (from env vars)
│   ├── database.py   # Supabase client
│   ├── auth.py       # JWT + token blacklist
│   ├── exceptions.py # Custom exceptions
│   └── rate_limit.py # Rate limiting config
├── services/         # Business logic (16 services)
│   ├── auth_service.py
│   ├── customer_service.py
│   ├── vendor_service.py
│   ├── rm_service.py
│   ├── admin_service.py
│   ├── salon_service.py
│   ├── booking_service.py
│   ├── payment_service.py
│   ├── career_service.py
│   ├── config_service.py
│   ├── storage_service.py
│   ├── email.py (+ email_logger.py)
│   ├── location.py (+ geocoding.py)
│   └── activity_log_service.py
└── schemas/          # Pydantic models
    ├── user.py
    ├── admin.py
    └── response.py
```

---

## 🛠️ Adding New Features

### 1. Create API Endpoint
```python
# app/api/your_module.py
from fastapi import APIRouter, Depends
from app.core.auth import get_current_user

router = APIRouter(prefix="/your-module", tags=["Your Module"])

@router.get("/")
async def get_items(current_user = Depends(get_current_user)):
    return {"items": []}
```

### 2. Register in main.py
```python
# main.py
from app.api import your_module

app.include_router(your_module.router, prefix="/api/v1")
```

### 3. Add Service Layer
```python
# app/services/your_service.py
from supabase import Client

class YourService:
    def __init__(self, db: Client):
        self.db = db
    
    def get_items(self):
        return self.db.table("items").select("*").execute()
```

### 4. Create Schema
```python
# app/schemas/your_schema.py
from pydantic import BaseModel

class ItemResponse(BaseModel):
    id: str
    name: str
```

### 5. Add Tests
```python
# tests/test_your_module.py
def test_get_items(client):
    response = client.get("/api/v1/your-module/")
    assert response.status_code == 200
```

---

## 🔐 Authentication

### Get Token
```python
# POST /api/v1/auth/login
{"email": "user@example.com", "password": "password"}

# Response
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "user": {...}
}
```

### Use Token
```python
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get("/api/v1/auth/me", headers=headers)
```

### Protected Endpoint
```python
from app.core.auth import get_current_user

@router.get("/protected")
async def protected_route(current_user = Depends(get_current_user)):
    return {"user_id": current_user["id"]}
```

### Role-Based Access
```python
from app.core.auth import require_role

@router.get("/admin-only")
async def admin_route(current_user = Depends(require_role("admin"))):
    return {"message": "Admin only"}
```

---

## 💾 Database Operations

### Query
```python
# Get all
result = db.table("salons").select("*").execute()

# Filter
result = db.table("salons")\
    .select("*")\
    .eq("status", "approved")\
    .execute()

# Join
result = db.table("bookings")\
    .select("*, salon:salons(*)")\
    .execute()
```

### Insert
```python
data = {"name": "Test Salon", "status": "pending"}
result = db.table("salons").insert(data).execute()
```

### Update
```python
data = {"status": "approved"}
result = db.table("salons")\
    .update(data)\
    .eq("id", salon_id)\
    .execute()
```

### Delete (Soft)
```python
result = db.table("salons")\
    .update({"is_active": False})\
    .eq("id", salon_id)\
    .execute()
```

---

## 📧 Sending Emails

```python
from app.services.email import send_email

await send_email(
    to_email="user@example.com",
    subject="Welcome",
    html_content="<h1>Welcome!</h1>",
    from_name="Salon Platform"
)
```

**Email service:**
- SMTP (Gmail) as primary
- Retry logic with exponential backoff
- Logs to `email_logs` table
- Requires `EMAIL_ENABLED=true` in env

---

## 💰 Payments (Razorpay)

### Create Order
```python
from app.services.payment_service import PaymentService

service = PaymentService(db, razorpay_client)
order = service.create_booking_order(
    booking_id="booking-123",
    amount=1000  # in rupees
)
# Returns: {"order_id": "order_xxx", "amount": 100000, ...}
```

### Verify Payment
```python
is_valid = service.verify_payment(
    order_id="order_xxx",
    payment_id="pay_xxx",
    signature="signature_xxx"
)
```

---

## 🗺️ Location Services

### Geocode Address
```python
from app.services.location import geocode_address

result = geocode_address("123 Main St, New York, NY")
# Returns: {"latitude": 40.7128, "longitude": -74.0060, ...}
```

### Find Nearby Salons
```python
# Uses PostGIS extension in PostgreSQL
result = db.rpc("get_nearby_salons", {
    "user_lat": 40.7128,
    "user_lng": -74.0060,
    "radius_km": 10
}).execute()
```

---

## 🚦 Rate Limiting

**Global:** 60 requests/minute per IP

**Auth endpoints:**
- Login: 5/minute
- Signup: 3/minute  
- Password Reset: 3/minute

**Custom limit:**
```python
from app.core.rate_limit import limiter

@router.get("/custom")
@limiter.limit("10/minute")
async def custom_route(request: Request):
    return {"message": "Limited to 10/min"}
```

---

## 🔍 Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.debug("Debug message")  # Only in DEBUG=true mode
```

**Middleware logs:**
- Incoming requests: `→ GET /api/v1/salons`
- Responses: `← GET /api/v1/salons - 200 - 123.45ms`
- Errors: `✗ GET /api/v1/salons - ERROR - 45.67ms`

---

## 🧪 Testing

### Test Structure
```python
def test_endpoint(client, auth_headers):
    response = client.get("/api/v1/endpoint", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["success"] == True
```

### Fixtures (conftest.py)
- `client` - Test client
- `auth_headers` - Authenticated headers
- `db` - Database client

### Run Tests
```powershell
pytest                    # All tests
pytest -k "auth"          # Tests matching "auth"
pytest -m "unit"          # Unit tests only
pytest --cov=app          # With coverage
pytest -x                 # Stop on first failure
```

---

## 🐛 Common Errors

### AppException
Custom business logic exceptions.
```python
from app.core.exceptions import AppException

raise AppException(
    message="Salon not found",
    status_code=404
)
```

### ValidationError
Pydantic validation errors (auto-handled).

### HTTPException
FastAPI standard exceptions.
```python
from fastapi import HTTPException

raise HTTPException(
    status_code=403,
    detail="Forbidden"
)
```

---

## 📊 Background Tasks

**Token Cleanup:**
- Runs every 6 hours
- Deletes expired tokens from `blacklisted_tokens`
- Automatic on startup

**Add custom task:**
```python
# main.py
async def my_background_task():
    while True:
        # Do work
        await asyncio.sleep(3600)  # Every hour

@app.on_event("startup")
async def startup():
    app.state.my_task = asyncio.create_task(my_background_task())
```

---

## 🔧 Debugging

### Enable Debug Mode
```env
DEBUG=true
```

### Check Request/Response
Middleware logs all requests. Check terminal output.

### Database Queries
```python
# Add .execute() to see raw response
result = db.table("salons").select("*").execute()
print(result)  # Shows full response
```

### Swagger UI
http://localhost:8000/docs - Test endpoints interactively

---

## 📦 Dependencies

**Core:**
- FastAPI 0.115.0
- Uvicorn 0.32.1
- Pydantic 2.10.4

**Database:**
- Supabase 2.0.3
- psycopg2-binary 2.9.9

**Auth:**
- python-jose 3.3.0
- passlib 1.7.4
- bcrypt 4.1.1

**Payments:**
- razorpay 1.4.1

**Email:**
- resend 0.7.0 (legacy)
- emails 0.6 (SMTP)

**Location:**
- geopy 2.4.0

**Rate Limiting:**
- slowapi 0.1.9

---

## 🚀 Deployment

See `docs/deployment/DEPLOYMENT_FLOW.md` for full deployment guide.

**Quick:**
1. Push to `staging` branch → Auto-deploys to Render.com staging
2. Merge to `main` → Requires manual deployment

---

## 📚 Further Reading

- **API Endpoints:** `docs/reference/API_ENDPOINTS.md` (all 138 endpoints)
- **Architecture:** `docs/architecture/ARCHITECTURE_MAP.md`
- **Auth Flow:** `docs/architecture/ARCHITECTURE_AUTH.md`
- **Getting Started:** `docs/getting-started/GETTING_STARTED.md`
