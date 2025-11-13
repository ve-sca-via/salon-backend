# 🐳 Supabase Local Development Guide

**Created:** November 12, 2025  
**For:** Salon Management Backend Testing & Development

---

## 📋 Table of Contents
1. [What is Supabase Local Dev?](#what-is-supabase-local-dev)
2. [Visual Comparison](#visual-comparison)
3. [How It Works](#how-it-works)
4. [Data Sources](#data-sources)
5. [Setup Guide](#setup-guide)
6. [Switching Between Local & Production](#switching-between-local--production)
7. [Your 3 Testing Options](#your-3-testing-options)

---

## 🤔 What is Supabase Local Dev?

**Simple Answer:** Run a complete copy of Supabase on your laptop using Docker containers.

**Benefits:**
- ✅ No internet connection needed
- ✅ **100% FREE** (no usage limits!)
- ✅ Test data completely separate from production
- ✅ Same exact setup as production Supabase
- ✅ Fast development (no network latency)
- ✅ Safe to break things (just restart containers)

---

## 📊 Visual Comparison

### PRODUCTION SETUP (Current):
```
Your Laptop
  └─ FastAPI App (main.py)
      └─ reads .env:
          SUPABASE_URL=https://xxx.supabase.co
      └─ connects to Internet ☁️
      └─ talks to Supabase Cloud
           └─ Production Database (real customer data) ⚠️
           └─ Production Auth (real users) ⚠️
```

### LOCAL DEVELOPMENT SETUP (What We Want):
```
Your Laptop
  ├─ Docker Desktop (running)
  │   └─ Supabase Containers:
  │       ├─ PostgreSQL (localhost:54322)
  │       ├─ Auth Service (localhost:54321)
  │       ├─ Storage (localhost:54321)
  │       └─ Realtime (localhost:54321)
  │
  └─ FastAPI App (main.py)
      └─ reads .env.local:
          SUPABASE_URL=http://localhost:54321
      └─ connects to localhost (no internet!) 🏠
      └─ talks to local Supabase
           └─ Test Database (fake data) ✅
           └─ Test Auth (test users) ✅
```

---

## ⚙️ How It Works

### 1. Docker Containers (Mini Virtual Machines)
Supabase Local Dev uses **Docker containers** - think of them as mini VMs that run isolated services:

| Container | Port | Purpose |
|-----------|------|---------|
| **PostgreSQL** | 54322 | Database (same as production) |
| **GoTrue** | 54321 | Authentication service |
| **PostgREST** | 54321 | REST API |
| **Kong** | 54321 | API Gateway |
| **Storage** | 54321 | File storage |
| **Realtime** | 54321 | WebSocket connections |

### 2. No Internet Needed
Everything runs on `localhost` - your FastAPI app talks to `http://localhost:54321` instead of `https://xxx.supabase.co`

### 3. Identical to Production
The Docker containers run the **exact same code** as Supabase Cloud, so your local tests are accurate!

---

## 💾 Data Sources

### "Where does local dev get data from?"

**Answer:** It starts EMPTY, then you populate it!

### Step-by-Step Data Flow:

```mermaid
Start Empty Database
    ↓
1. Apply Migrations (Schema Structure)
    ├─ Creates tables (profiles, salons, bookings, etc.)
    ├─ Creates indexes
    └─ Creates functions/triggers
    ↓
2. Run Seed File (Test Data)
    ├─ INSERT fake users
    ├─ INSERT fake salons
    └─ INSERT fake bookings
    ↓
Local Database Ready! 🎉
```

### Example: `seed.sql`
```sql
-- supabase/seed.sql

-- Add test users
INSERT INTO profiles (id, email, full_name, role) VALUES
  ('test-user-1', 'customer@test.com', 'Test Customer', 'customer'),
  ('test-user-2', 'vendor@test.com', 'Test Vendor', 'vendor'),
  ('test-user-3', 'admin@test.com', 'Test Admin', 'admin');

-- Add test salon
INSERT INTO salons (id, vendor_id, name, address, latitude, longitude, status) VALUES
  ('test-salon-1', 'test-user-2', 'Test Salon', '123 Test St', 40.7128, -74.0060, 'approved');

-- Add test booking
INSERT INTO bookings (id, customer_id, salon_id, service_id, status, booking_date) VALUES
  ('test-booking-1', 'test-user-1', 'test-salon-1', 'test-service-1', 'confirmed', NOW());
```

### Where to Get Schema (2 Options):

**Option A: Pull from Production** (Easiest)
```bash
supabase db pull
```
This copies your production database schema to `supabase/migrations/`

**Option B: Create Manually**
Write SQL migration files in `supabase/migrations/`

---

## 🚀 Setup Guide

### Prerequisites:
- Windows 10/11
- At least 4GB free RAM
- 10GB free disk space

### Step 1: Install Docker Desktop
1. Download: https://www.docker.com/products/docker-desktop/
2. Run installer
3. Restart computer
4. Open Docker Desktop → Wait for "Engine running" ✅

### Step 2: Install Supabase CLI
```powershell
npm install -g supabase
```

### Step 3: Initialize Supabase in Your Project
```powershell
cd G:\vescavia\Projects\backend
supabase init
```

**This creates:**
```
backend/
  └─ supabase/
      ├─ config.toml        # Configuration
      ├─ seed.sql           # Test data (you'll edit this!)
      └─ migrations/        # Database schema
```

### Step 4: Start Local Supabase
```powershell
supabase start
```

**Output:**
```
Started supabase local development setup.

         API URL: http://localhost:54321
          DB URL: postgresql://postgres:postgres@localhost:54322/postgres
      Studio URL: http://localhost:54323
    Inbucket URL: http://localhost:54324
        anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Step 5: Create `.env.local`
Create this file in `backend/.env.local`:

```env
# Local Development Environment
ENVIRONMENT=local
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # (copy from supabase start output)
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # (copy from output)

# Razorpay (use test keys)
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=xxx

# Other settings
JWT_SECRET_KEY=local-dev-secret-key
SMTP_HOST=localhost
SMTP_PORT=54324  # Inbucket (local email testing)
```

### Step 6: Pull Production Schema (Optional but Recommended)
```powershell
# First, connect to production
supabase link --project-ref your-project-ref

# Then pull schema
supabase db pull
```

### Step 7: Add Test Data
Edit `supabase/seed.sql` with your test data (see example above)

Then apply it:
```powershell
supabase db reset
```

### Step 8: Run Your FastAPI App
```powershell
# Use local environment
cp .env.local .env

# Start app
python main.py
```

Your app now connects to **localhost Supabase**! 🎉

---

## 🔄 Switching Between Local & Production

### Quick Switch Method:
```powershell
# Switch to LOCAL:
cp .env.local .env
python main.py

# Switch to PRODUCTION:
cp .env.production .env
python main.py
```

### Safe Method (Recommended):
Create `.env.production`:
```env
ENVIRONMENT=production
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # production anon key
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # production service key
```

Then use environment variables:
```powershell
# Local:
$env:ENV_FILE=".env.local"; python main.py

# Production:
$env:ENV_FILE=".env.production"; python main.py
```

### What Changes When You Switch?

| Setting | Local | Production |
|---------|-------|------------|
| `SUPABASE_URL` | `http://localhost:54321` | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Local anon key | Production anon key |
| Database | Test data on your laptop | Real customer data in cloud |
| Cost | FREE | Paid (after free tier) |
| Internet | Not needed | Required |

---

## 🎯 Your 3 Testing Options

### Option 1: MockSupabaseClient (Current - 6/10)
**Location:** `app/core/database.py`

**Pros:**
- ✅ Already exists in your code
- ✅ Zero setup (just set `ENVIRONMENT=test`)
- ✅ Fast (no database needed)

**Cons:**
- ❌ Returns empty data `{data: [], count: 0}`
- ❌ Can't test real queries
- ❌ Can't test business logic with actual data

**Use When:** You just want to check if the app starts without errors

**How to Use:**
```powershell
$env:ENVIRONMENT="test"; python main.py
```

---

### Option 2: Supabase Local Dev (Best - 9/10) ⭐
**Location:** Docker containers on your laptop

**Pros:**
- ✅ Real PostgreSQL database
- ✅ No internet needed
- ✅ Test with realistic data
- ✅ Same as production (accurate testing)
- ✅ Free unlimited usage
- ✅ Can test Auth, Storage, Realtime

**Cons:**
- ❌ Requires Docker Desktop (~2GB)
- ❌ 30-minute initial setup
- ❌ Uses some RAM (~1-2GB)

**Use When:** You want real integration testing before deploying

**How to Use:**
```powershell
# Start containers
supabase start

# Use local environment
cp .env.local .env

# Run app
python main.py
```

---

### Option 3: Production Database (Current - 5/10)
**Location:** Supabase Cloud

**Pros:**
- ✅ Real data
- ✅ No setup needed

**Cons:**
- ❌ Dangerous (could break real customer data!)
- ❌ Needs internet
- ❌ Slower (network latency)
- ❌ Costs money (after free tier)

**Use When:** Final checks before deploying to production

**How to Use:**
```powershell
# Use production environment
cp .env.production .env

# Run app (BE CAREFUL!)
python main.py
```

---

## 🛑 Stopping Local Supabase

### When You're Done Testing:
```powershell
supabase stop
```

This shuts down all Docker containers and frees up RAM.

### To Start Again Later:
```powershell
supabase start
```

Your data persists! Docker volumes save everything between restarts.

---

## 🆘 Common Issues

### "Docker is not running"
**Solution:** Open Docker Desktop and wait for "Engine running" ✅

### "Port 54321 already in use"
**Solution:** Stop other apps using that port or change port in `supabase/config.toml`

### "Database is empty after restart"
**Solution:** Run `supabase db reset` to reapply migrations + seed data

### "Can't connect to localhost:54321"
**Solution:** Check `supabase status` to see if containers are running

---

## 📚 Next Steps

### Recommended Priority:

**A) Setup Supabase Local Dev Now (30 minutes)**
- Best for learning and testing
- Gives you a safe playground
- No risk to production data

**B) Fix `payments.py` First (2-3 hours)**
- Critical architectural issue
- Then test with local dev

**C) Just Run with `ENVIRONMENT=test` (5 minutes)**
- Quick check to see MockSupabaseClient
- Limited functionality

**D) Ask More Questions**
- Still confused about Docker?
- Need help with specific setup steps?

---

## 🎓 Learning Resources

- **Supabase Local Dev Docs:** https://supabase.com/docs/guides/cli/local-development
- **Docker Desktop Tutorial:** https://docs.docker.com/desktop/
- **Your Current Files:**
  - `.env` (production config)
  - `app/core/database.py` (MockSupabaseClient)
  - `app/core/config.py` (settings management)

---

**Questions?** Just ask! I'm here to help. 🚀

---

_Last Updated: November 12, 2025_
