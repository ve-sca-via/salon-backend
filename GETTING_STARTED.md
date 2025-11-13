# 🚀 Salon Management Backend - Quick Start Guide

## 📋 Table of Contents
1. [Prerequisites](#prerequisites)
2. [First Time Setup](#first-time-setup)
3. [Running the App](#running-the-app)
4. [Understanding Environments](#understanding-environments)
5. [Team Workflow](#team-workflow)
6. [Troubleshooting](#troubleshooting)

---

## ✅ Prerequisites

Before starting, install these on your machine:

1. **Python 3.10+** - [Download here](https://www.python.org/downloads/)
2. **Docker Desktop** - [Download here](https://www.docker.com/products/docker-desktop/)
3. **Scoop** (Windows package manager):
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
   ```
4. **Supabase CLI**:
   ```powershell
   scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
   scoop install supabase
   ```

---

## 🛠️ First Time Setup

### Step 1: Clone the Repository
```powershell
git clone https://github.com/your-org/salon-backend.git
cd salon-backend
```

### Step 2: Create Python Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Setup Environment Files

**Create `.env.production`** (for production - get credentials from team lead):
```powershell
# Copy the example file
Copy-Item .env.production.example .env.production

# Edit .env.production and fill in REAL production credentials
# Ask your team lead for these values!
```

**Local environment** (already configured in `.env.local` - no changes needed)

### Step 5: Start Supabase Local Dev
```powershell
# Initialize Supabase (creates config files)
supabase init

# Login to Supabase (one-time only)
supabase login

# Link to production project (get project-ref from team lead)
supabase link --project-ref YOUR_PROJECT_REF

# Pull production database schema
supabase db pull

# Start local Supabase
supabase start
```

---

## 🏃 Running the App

### **LOCAL Development (Recommended for Daily Work)**
```powershell
# Easy way (automated):
.\run-local.ps1

# OR Manual way:
Copy-Item .env.local .env -Force
python main.py
```

**What happens:**
- ✅ Connects to local Supabase (Docker)
- ✅ Uses fake test data on your laptop
- ✅ No internet needed
- ✅ 100% safe - can't break production

**Access:**
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Supabase Studio: http://127.0.0.1:54323

---

### **PRODUCTION (DANGEROUS - Only for Deployment)**
```powershell
# Easy way (asks for confirmation):
.\run-production.ps1

# OR Manual way:
Copy-Item .env.production .env -Force
python main.py
```

**What happens:**
- ⚠️ Connects to REAL Supabase Cloud
- ⚠️ Uses REAL customer data
- ⚠️ Requires internet
- ⚠️ Mistakes affect real users!

**⚠️ WARNING:** Only use this when deploying to production server!

---

## 🌍 Understanding Environments

### **Three Environments Explained:**

| Environment | Purpose | Data Location | Safe to Break? |
|-------------|---------|---------------|----------------|
| **LOCAL** | Daily development & testing | Your laptop (Docker) | ✅ Yes |
| **PRODUCTION** | Live app for real users | Supabase Cloud | ❌ No! |
| **TEST** (optional) | Automated unit tests | In-memory mock | ✅ Yes |

### **Environment Files:**

```
backend/
  ├─ .env                         ← Active config (auto-generated, changes)
  ├─ .env.local                   ← Local Supabase config (committed to Git)
  ├─ .env.production              ← Production secrets (NOT in Git!)
  ├─ .env.production.example      ← Template (safe to commit)
  └─ .gitignore                   ← Protects secrets
```

### **What Gets Committed to Git?**

✅ **Safe to commit:**
- `.env.local` (localhost URLs, demo keys)
- `.env.production.example` (template with placeholders)
- `run-local.ps1` and `run-production.ps1` (automation scripts)

❌ **NEVER commit:**
- `.env` (auto-generated)
- `.env.production` (real production secrets!)

---

## 👥 Team Workflow

### **For New Team Members:**

1. **Get production credentials from team lead:**
   - Supabase URL
   - Supabase Anon Key
   - Supabase Service Role Key
   - Razorpay credentials
   - Email SMTP credentials

2. **Create `.env.production`:**
   ```powershell
   Copy-Item .env.production.example .env.production
   # Edit .env.production with real values
   ```

3. **Setup local Supabase:**
   ```powershell
   supabase init
   supabase login
   supabase link --project-ref YOUR_PROJECT_REF
   supabase db pull
   supabase start
   ```

4. **Start coding:**
   ```powershell
   .\run-local.ps1
   ```

---

### **Daily Development Workflow:**

```powershell
# Morning: Start local Supabase
supabase start

# Run app locally
.\run-local.ps1

# Code, test, repeat...

# Evening: Stop Supabase (saves RAM)
supabase stop
```

---

### **Adding Test Data (Optional):**

Edit `supabase/seed.sql`:
```sql
-- Add fake users for testing
INSERT INTO profiles (id, email, full_name, role) VALUES
  ('test-customer-1', 'customer@test.com', 'Test Customer', 'customer'),
  ('test-vendor-1', 'vendor@test.com', 'Test Vendor', 'vendor'),
  ('test-admin-1', 'admin@test.com', 'Test Admin', 'admin');

-- Add fake salon
INSERT INTO salons (id, vendor_id, business_name, address, latitude, longitude, status) VALUES
  ('test-salon-1', 'test-vendor-1', 'Test Salon', '123 Test St', 40.7128, -74.0060, 'approved');
```

Then reset database:
```powershell
supabase db reset
```

---

## 🔄 How Switching Works

### **The Flow:**

```
1. You have multiple .env files:
   .env.local       (localhost config)
   .env.production  (cloud config)

2. App always reads from .env

3. To switch, copy the desired config:
   Copy-Item .env.local .env       → App uses LOCAL
   Copy-Item .env.production .env  → App uses PRODUCTION

4. Automation scripts do this for you:
   .\run-local.ps1      → Copies .env.local → .env
   .\run-production.ps1 → Copies .env.production → .env
```

### **No More Manual Copying:**

**Before (manual):**
```powershell
Copy-Item .env.local .env -Force
python main.py
```

**Now (automated):**
```powershell
.\run-local.ps1
```

---

## 🐛 Troubleshooting

### **"Docker is not running"**
```powershell
# Solution: Open Docker Desktop and wait for "Engine running" ✅
```

### **"Supabase is not running"**
```powershell
# Solution: Start Supabase
supabase start
```

### **"Invalid API key"**
```powershell
# Solution: Check .env file has correct keys
# For local: run 'supabase status' and update .env.local
# For production: verify .env.production has correct keys from Supabase dashboard
```

### **"Missing Supabase environment variables"**
```powershell
# Solution: Make sure .env has these three variables:
# SUPABASE_URL
# SUPABASE_ANON_KEY
# SUPABASE_SERVICE_ROLE_KEY
```

### **Port 54321 already in use**
```powershell
# Solution: Stop existing Supabase
supabase stop

# OR: Change port in supabase/config.toml
```

### **Database schema out of sync**
```powershell
# Solution: Pull latest schema from production
supabase db pull

# Then reset local database
supabase db reset
```

---

## 📚 Useful Commands

### **Supabase:**
```powershell
# Start local Supabase
supabase start

# Stop local Supabase (saves RAM)
supabase stop

# Check status
supabase status

# Pull latest schema from production
supabase db pull

# Reset local database (wipes data)
supabase db reset

# View logs
supabase logs
```

### **App:**
```powershell
# Run locally (automated)
.\run-local.ps1

# Run on production (with confirmation)
.\run-production.ps1

# Install new dependencies
pip install -r requirements.txt

# Update requirements file
pip freeze > requirements.txt
```

### **Git:**
```powershell
# Check what's changed
git status

# Create new branch
git checkout -b feature/your-feature-name

# Commit changes
git add .
git commit -m "Your commit message"

# Push to GitHub
git push origin feature/your-feature-name
```

---

## 🔐 Security Reminders

1. ✅ **NEVER** commit `.env` or `.env.production` to Git
2. ✅ **ALWAYS** use `.env.local` for local development
3. ✅ **NEVER** share production credentials in Slack/Discord
4. ✅ **ALWAYS** use password managers for production secrets
5. ✅ **Test locally first** before touching production

---

## 📞 Need Help?

- **Team Lead:** [Your Name] - [your-email@example.com]
- **Documentation:** `docs/SUPABASE_LOCAL_DEV_GUIDE.md`
- **Supabase Docs:** https://supabase.com/docs

---

**Happy Coding! 🚀**
