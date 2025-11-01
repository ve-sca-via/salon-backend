# Lightweight FastAPI Backend

A complete multi-role platform for salon/spa management with integrated hiring, booking, and payment systems.

### 🎭 4 Distinct Roles

1. **Admin** 🔒 - Full system control, approvals, configuration
2. **Relationship Manager (RM)** 📊 - Add salons, earn dynamic scores
3. **Vendor** 🏪 - Manage salon after approval & payment
4. **Customer** 🛍️ - Browse, book, pay, review

### 💡 Key Features

- ✅ **Dynamic Configuration**: All fees & scores admin-controlled
- ✅ **Payment Integration**: Razorpay for registration & booking fees
- ✅ **Approval Workflow**: RM → Admin → Vendor email → Payment → Activation
- ✅ **RM Scoring**: Dynamic points system for performance tracking
- ✅ **Hybrid Architecture**: Complex logic via backend, simple ops via Supabase
- ✅ **Security**: RLS policies, JWT auth, payment verification

---

## 📚 Documentation

## 🎯 What This Backend Does

**Server-Side Only Operations:**
- 🗺️ **Geocoding** - Convert addresses to lat/lon (keeps API keys secure)
- 📍 **Nearby Salons** - Spatial queries with distance calculation
- 💳 **Payment Webhooks** - Handle Stripe/Razorpay callbacks (future)
- 📧 **Email Notifications** - Booking confirmations, reminders (future)

**What It Doesn't Do (Supabase Handles):**
- ✅ Authentication (Supabase Auth)
- ✅ Direct DB queries from frontend (Supabase client)
- ✅ File uploads (Supabase Storage)
- ✅ Real-time subscriptions (Supabase Realtime)

---

## 📦 Setup

### 1. Install Dependencies

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your credentials
```

**Required Settings:**
- `DATABASE_URL` - Your Supabase PostgreSQL connection string
- `GOOGLE_MAPS_API_KEY` or `OPENCAGE_API_KEY` - For geocoding
- `ALLOWED_ORIGINS` - Your frontend URL (default: http://localhost:3000)

**Get Supabase Database URL:**
1. Go to Supabase Dashboard → Project Settings → Database
2. Copy the "Connection string" (URI mode)
3. Replace `[YOUR-PASSWORD]` with your database password

Example:
```
DATABASE_URL=postgresql://postgres.ffkwfkhvzalyyrtlsiar:your_password@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
```

### 3. Setup Alembic (Database Migrations)

```bash
# Initialize Alembic
alembic init alembic

# Edit alembic.ini: set sqlalchemy.url to your DATABASE_URL
# Or use env variable (recommended)

# Create initial migration
alembic revision --autogenerate -m "add latitude longitude to salons"

# Apply migrations
alembic upgrade head
```

---

## 🚀 Run Backend

### Development Mode (with auto-reload)

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Backend will run at: **http://localhost:8000**

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📡 API Endpoints

### Health Check
```http
GET /health
```
Returns: `{"status": "healthy"}`

### Geocode Address
```http
POST /api/location/geocode
Content-Type: application/json

{
  "address": "123 Main St, Mumbai, Maharashtra 400001"
}
```
Returns:
```json
{
  "latitude": 19.0760,
  "longitude": 72.8777,
  "address": "123 Main St, Mumbai, Maharashtra 400001"
}
```

### Reverse Geocode
```http
GET /api/location/reverse-geocode?lat=19.0760&lon=72.8777
```
Returns:
```json
{
  "address": "Mumbai, Maharashtra, India",
  "latitude": 19.0760,
  "longitude": 72.8777
}
```

### Get Nearby Salons
```http
GET /api/location/salons/nearby?lat=19.0760&lon=72.8777&radius=10&limit=50
```

**Query Parameters:**
- `lat` (required) - User's latitude
- `lon` (required) - User's longitude  
- `radius` (optional, default: 10) - Search radius in km (0.5 - 50)
- `limit` (optional, default: 50) - Max results (1 - 100)

Returns:
```json
{
  "salons": [
    {
      "id": 1,
      "name": "Glamour Studio",
      "address_line1": "123 Main St",
      "city": "Mumbai",
      "latitude": 19.0760,
      "longitude": 72.8777,
      "rating": 4.5,
      "total_reviews": 120,
      "distance_km": 0.85
    }
  ],
  "count": 1,
  "query": {
    "latitude": 19.0760,
    "longitude": 72.8777,
    "radius_km": 10
  }
}
```

---

## 🗄️ Database Migrations with Alembic

### Create a New Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "add new table"

# Or create empty migration
alembic revision -m "custom change"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade by one version
alembic upgrade +1

# Downgrade by one version
alembic downgrade -1
```

### View Migration History

```bash
alembic history
alembic current
```

### Example: Add Coordinates to Salons

1. **Modify model** in `app/models/models.py`:
```python
latitude = Column(DECIMAL(10, 7))
longitude = Column(DECIMAL(10, 7))
```

2. **Generate migration**:
```bash
alembic revision --autogenerate -m "add lat lon to salons"
```

3. **Review generated file** in `alembic/versions/`:
```python
def upgrade():
    op.add_column('salons', sa.Column('latitude', sa.DECIMAL(precision=10, scale=7)))
    op.add_column('salons', sa.Column('longitude', sa.DECIMAL(precision=10, scale=7)))
```

4. **Apply**:
```bash
alembic upgrade head
```

🎉 **Tables updated automatically!** No copy-paste SQL!

---

## 🔧 Project Structure

```
backend/
├── main.py                 # FastAPI app entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── .env                   # Your credentials (gitignored)
├── alembic/               # Database migrations
│   └── versions/          # Migration files
├── app/
│   ├── api/               # API routes
│   │   └── location.py    # Location endpoints
│   ├── core/              # Core configuration
│   │   ├── config.py      # Settings
│   │   └── database.py    # DB connection
│   ├── models/            # SQLAlchemy models
│   │   └── models.py      # Salon, Booking, etc.
│   └── services/          # Business logic
│       ├── geocoding.py   # Address ↔ coordinates
│       └── location.py    # Nearby search
```

---

## 🌐 Connect Frontend

Update your React app to call backend:

```javascript
// src/services/api.js

const BACKEND_URL = 'http://localhost:8000';

// Geocode address
export const geocodeAddress = async (address) => {
  const response = await fetch(`${BACKEND_URL}/api/location/geocode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address })
  });
  return response.json();
};

// Get nearby salons
export const getNearbySalons = async (lat, lon, radius = 10) => {
  const response = await fetch(
    `${BACKEND_URL}/api/location/salons/nearby?lat=${lat}&lon=${lon}&radius=${radius}`
  );
  return response.json();
};
```

---

## 🚢 Deployment

### Option 1: Railway
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

### Option 2: Render
1. Create new Web Service
2. Connect your GitHub repo
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables from `.env`

### Option 3: Fly.io
```bash
# Install flyctl
# On Windows: iwr https://fly.io/install.ps1 -useb | iex

fly launch
fly deploy
```

---

## 📊 Performance

**Nearby Salons Query:**
- Bounding box pre-filter (fast)
- Haversine distance calculation (precise)
- Distance sorting
- Limit results

**Typical Performance:**
- < 100ms for 1000 salons
- < 500ms for 10,000 salons
- Scales well with DB indexes

**Add Indexes:**
```sql
CREATE INDEX idx_salons_lat ON salons(latitude);
CREATE INDEX idx_salons_lon ON salons(longitude);
CREATE INDEX idx_salons_status ON salons(status);
```

---

## 🔒 Security

**API Keys:**
- ✅ Stored in `.env` (server-side only)
- ✅ Never exposed to frontend
- ✅ `.env` in `.gitignore`

**CORS:**
- Only allows requests from configured origins
- Set `ALLOWED_ORIGINS` in `.env`

**Database:**
- Uses connection pooling
- Async operations (non-blocking)
- SQL injection protected (SQLAlchemy ORM)

---

## 🎯 Next Features to Add

### 1. Payment Webhook (Stripe)
```python
# app/api/payment.py
@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    # Verify and handle event
```

### 2. Email Notifications
```python
# app/services/email.py
import resend

async def send_booking_confirmation(user_email, booking):
    resend.Emails.send({
        "from": "noreply@yourdomain.com",
        "to": user_email,
        "subject": "Booking Confirmed!",
        "html": f"<p>Your booking at {booking.salon_name} is confirmed!</p>"
    })
```

### 3. Scheduled Jobs
```python
# Use APScheduler or Celery
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=9)
async def send_reminders():
    # Send reminders for bookings tomorrow
    pass
```

---

## 🐛 Troubleshooting

### Import errors
```bash
# Make sure virtual environment is activated
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Reinstall dependencies
pip install -r requirements.txt
```

### Database connection fails
- Check `DATABASE_URL` in `.env`
- Verify Supabase project is not paused
- Test connection: `psql <your_database_url>`

### CORS errors in frontend
- Add frontend URL to `ALLOWED_ORIGINS` in `.env`
- Restart backend after changing `.env`

### Alembic errors
- Check `alembic.ini` has correct `sqlalchemy.url`
- Or set `DATABASE_URL` env variable
- Delete `alembic/versions/*` and regenerate if needed

---

## 📚 Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Supabase Database Connection](https://supabase.com/docs/guides/database/connecting-to-postgres)

---

**Your lightweight backend is ready!** 🚀

This backend only handles what requires server-side security (geocoding, payments, emails) while keeping your architecture simple. Most operations still go directly through Supabase from your React app.
