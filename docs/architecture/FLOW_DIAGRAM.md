# 🗺️ COMPLETE FLOW DIAGRAM

**Last Updated:** December 11, 2025  
**Environment:** Local + Staging + Production

## 📁 File Structure & What Gets Committed

```
backend/
│
├─ .env                          ❌ NOT in Git (environment-specific)
├─ .env.staging                  ❌ NOT in Git (staging secrets)
├─ .env.production               ❌ NOT in Git (production secrets!)
│
├─ run-local.ps1                 ✅ IN Git (local dev script)
├─ run-staging.ps1               ✅ IN Git (staging script)
├─ run-production.ps1            ✅ IN Git (production script)
├─ setup-staging.ps1             ✅ IN Git (staging setup)
│
├─ main.py                       ✅ IN Git (FastAPI application)
├─ requirements.txt              ✅ IN Git (Python dependencies)
├─ requirements-test.txt         ✅ IN Git (Test dependencies)
├─ runtime.txt                   ✅ IN Git (Python version)
├─ render.yaml                   ✅ IN Git (deployment config)
│
├─ README.md                     ✅ IN Git (project overview)
├─ docs/
│   ├─ architecture/             ✅ IN Git (architecture docs)
│   ├─ deployment/               ✅ IN Git (deployment guides)
│   ├─ getting-started/          ✅ IN Git (onboarding)
│   ├─ guides/                   ✅ IN Git (how-to guides)
│   └─ reference/                ✅ IN Git (API reference)
│
├─ app/                          ✅ IN Git (application code)
│   ├─ api/                      ✅ API routes
│   ├─ core/                     ✅ Core functionality
│   ├─ schemas/                  ✅ Pydantic models
│   └─ services/                 ✅ Business logic
│
└─ supabase/
    ├─ config.toml               ✅ IN Git (Supabase config)
    └─ migrations/               ✅ IN Git (database schema)
        └─ 20251209000000_*.sql  ✅ All migrations
```

---

## 🔄 The Environment Flow (December 2025)

### VISUAL REPRESENTATION:

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR LAPTOP                                                │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Local Dev    │  │ .env.staging │  │ .env.prod    │     │
│  │              │  │              │  │              │     │
│  │ LOCAL CONFIG │  │ STAGING      │  │ PROD CONFIG  │     │
│  │ (Docker)     │  │ (Render.com) │  │ (Render.com) │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │              │
│         │                 │                 │              │
│         ▼                 ▼                 ▼              │
│  ┌────────────────────────────────────────────────────┐   │
│  │         .env (ACTIVE) - App reads this             │   │
│  │  (Gets set by run-local/staging/production.ps1)   │   │
│  └────────────────┬───────────────────────────────────┘   │
│                   │                                        │
│                   ▼                                        │
│  ┌────────────────────────────────────┐                   │
│  │     FastAPI App (main.py)          │                   │
│  │  - Uvicorn server                  │                   │
│  │  - JWT authentication              │                   │
│  │  - Rate limiting (slowapi)         │                   │
│  │  - 130+ API endpoints              │                   │
│  └────────────────┬───────────────────┘                   │
│                   │                                        │
└───────────────────┼────────────────────────────────────────┘
                    │
                    │ Connects to...
                    │
        ┌───────────┴────────────┬───────────────┐
        │                        │               │
        ▼                        ▼               ▼
┌──────────────────┐    ┌──────────────┐  ┌──────────────┐
│  LOCAL DOCKER    │    │   STAGING    │  │ PRODUCTION   │
│                  │    │              │  │              │
│  Supabase CLI    │    │ Render.com   │  │ Render.com   │
│  localhost:54321 │    │ staging DB   │  │ production DB│
│                  │    │              │  │              │
│  Test Data       │    │ Test Data    │  │ Real Data    │
│  (Your Laptop)   │    │ (Cloud)      │  │ (Cloud)      │
└──────────────────┘    └──────────────┘  └──────────────┘
```

---

## 🎯 Step-by-Step: What Happens When You Switch

### SCENARIO 1: Run Local

```bash
.\run-local.ps1
```

**What happens behind the scenes:**

```
1. Script checks: "Is Docker running?"
   ├─ ❌ No  → Shows error, exits
   └─ ✅ Yes → Continue

2. Script checks: "Is Supabase running?"
   ├─ ❌ No  → Runs 'supabase start'
   └─ ✅ Yes → Continue

3. Script executes: Copy-Item .env.local .env -Force
   
   Before:                After:
   .env (whatever)   →   .env (localhost config)
   
4. Script runs: python main.py

5. App reads .env:
   SUPABASE_URL=http://127.0.0.1:54321
   
6. App connects to Docker Supabase
   
7. You're now testing with LOCAL data! ✅
```

---

### SCENARIO 2: Run Production

```bash
.\run-production.ps1
```

**What happens behind the scenes:**

```
1. Script warns: "⚠️ CONNECTING TO REAL DATA!"

2. Script asks: "Are you sure? (yes/no)"
   ├─ Type "no"  → Cancelled, exits
   └─ Type "yes" → Continue

3. Script checks: "Does .env.production exist?"
   ├─ ❌ No  → Shows error, exits
   └─ ✅ Yes → Continue

4. Script executes: Copy-Item .env.production .env -Force
   
   Before:                      After:
   .env (localhost config)  →  .env (production config)
   
5. Script runs: python main.py

6. App reads .env:
   SUPABASE_URL=https://xxx.supabase.co
   
7. App connects to Supabase Cloud
   
8. You're now using REAL PRODUCTION data! ⚠️
```

---

## 🏗️ Data Architecture

### WHERE DATA LIVES:

```
┌─────────────────────────────────────────────────────────────┐
│  LOCAL ENVIRONMENT (Your Laptop)                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Docker Desktop                                             │
│  └─ Supabase Containers                                     │
│      ├─ PostgreSQL Database                                 │
│      │   └─ Docker Volume: /var/lib/docker/volumes/...     │
│      │       └─ Data persists here between restarts        │
│      │                                                       │
│      ├─ Tables (from migrations/)                           │
│      │   ├─ profiles                                        │
│      │   ├─ salons                                          │
│      │   ├─ bookings                                        │
│      │   └─ ...all production tables                        │
│      │                                                       │
│      └─ Data (from seed.sql)                                │
│          └─ Fake users, fake salons, fake bookings          │
│                                                             │
│  Location: C:\Users\YourName\AppData\Local\Docker\wsl\...  │
│  Size: ~500MB - 2GB                                         │
│  Lifecycle: Survives restarts, deleted with 'docker volume rm'
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  PRODUCTION ENVIRONMENT (Supabase Cloud)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Supabase Servers (Mumbai Region)                           │
│  └─ PostgreSQL Database                                     │
│      ├─ Tables                                              │
│      │   ├─ profiles (REAL users)                           │
│      │   ├─ salons (REAL businesses)                        │
│      │   ├─ bookings (REAL appointments)                    │
│      │   └─ ...all tables                                   │
│      │                                                       │
│      └─ Data                                                 │
│          ├─ Real customer accounts                          │
│          ├─ Real salon registrations                        │
│          ├─ Real payment transactions                       │
│          └─ Real business data                              │
│                                                             │
│  Location: Supabase cloud servers                           │
│  Size: Depends on usage                                     │
│  Lifecycle: Permanent (unless manually deleted)             │
│  Backup: Automatic daily backups by Supabase                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Complete Lifecycle

### MORNING (Start Work):

```
1. Open Docker Desktop
   └─ Wait for "Engine running" ✅

2. Start Supabase:
   └─ supabase start
   
3. Run app locally:
   └─ .\run-local.ps1
   
4. Code & test with local data
   └─ Make changes, restart app, test API
   
5. Commit your changes:
   └─ git add .
   └─ git commit -m "Added new feature"
   └─ git push
```

### EVENING (Stop Work):

```
1. Stop FastAPI (Ctrl+C)

2. Stop Supabase (saves RAM):
   └─ supabase stop
   
3. Close Docker Desktop (optional)
```

### DEPLOYMENT DAY (Push to Production):

```
1. Merge code to main branch:
   └─ git checkout main
   └─ git pull origin main
   
2. Run production LOCALLY first (test):
   └─ .\run-production.ps1
   └─ Test ALL endpoints
   └─ Check logs for errors
   
3. If everything works, deploy to server:
   └─ SSH to production server
   └─ git pull
   └─ Restart FastAPI service
```

---

## 📊 Data Sync Flow

### How Database Schema Stays in Sync:

```
PRODUCTION DATABASE (Supabase Cloud)
         │
         │ 1. Someone adds a new table/column
         │
         ▼
   ┌────────────┐
   │ Run:       │
   │ supabase   │
   │ db pull    │
   └─────┬──────┘
         │
         │ 2. Downloads schema changes
         │
         ▼
   migrations/20251112173026_remote_schema.sql
         │
         │ 3. Committed to Git
         │
         ▼
   Git Repository (GitHub)
         │
         │ 4. Other teammates pull changes
         │
         ▼
   Teammate's Laptop
         │
         │ 5. They run:
         │
         ▼
   ┌────────────┐
   │ supabase   │
   │ db reset   │
   └─────┬──────┘
         │
         │ 6. Applies migrations
         │
         ▼
   LOCAL DATABASE (Their Docker)
   Now has same schema as production! ✅
```

---

## 🎓 Summary for Your Team

### **3 Simple Rules:**

1. **ALWAYS develop locally**
   - Use: `.\run-local.ps1`
   - Safe, fast, free

2. **NEVER touch .env or .env.production manually**
   - Scripts handle this
   - Less room for error

3. **Share credentials securely**
   - Use password managers (1Password, LastPass)
   - Never paste in Slack/Discord

### **Files to Share with Team:**

✅ **Commit to Git:**
- `GETTING_STARTED.md` (this guide)
- `.env.local` (safe localhost config)
- `.env.production.example` (template)
- `run-local.ps1` (automation)
- `run-production.ps1` (automation)

❌ **Share Securely (1Password, etc.):**
- `.env.production` (real credentials)

---

**Questions? Read `GETTING_STARTED.md` or ask team lead!**
