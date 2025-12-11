# 🚀 Quick Start Guide

**Last Updated:** December 11, 2025  
**Stack:** Python 3.11.9 | FastAPI 0.115.0 | Supabase PostgreSQL

---

## ⚡ TL;DR - Get Running Fast

```powershell
# 1. Clone & Setup
git clone <repo-url>
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Run Local (uses .env.local - no setup needed)
.\run-local.ps1

# 3. Access
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

That's it for local development. Skip to [API Testing](#api-testing) below.

---

## 📋 What You Need

**Required:**
- Python 3.11.9
- Git
- Text editor

**Optional:**
- Supabase CLI (for database migrations)
- Docker (for local Supabase instance)

---

## 🛠️ Detailed Setup

### 1. Clone Repository
```powershell
git clone https://github.com/ve-sca-via/salon-backend.git
cd backend
```

### 2. Create Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Verify:**
```powershell
python --version  # Should show 3.11.9
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

**What gets installed:**
- FastAPI 0.115.0
- Supabase client 2.0.3
- Razorpay 1.4.1
- JWT, bcrypt (auth)
- Geopy (location services)
- Resend/SMTP (email)
- SlowAPI (rate limiting)

---

## 🏃 Running the Backend

### Local Development
```powershell
.\run-local.ps1
```

**What this does:**
1. Copies `.env.local` → `.env`
2. Activates virtual environment
3. Runs `uvicorn main:app --reload --port 8000`

**Access:**
- API Base: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

### Staging (Online Testing)
```powershell
.\run-staging.ps1
```

Uses Supabase staging database. Get credentials from team lead.

### Production
```powershell
.\run-production.ps1
```

⚠️ **WARNING:** Uses live production database. Be careful!

---

## 🧪 API Testing

### Option 1: Swagger UI (Easiest)
1. Start backend: `.\run-local.ps1`
2. Open: http://localhost:8000/docs
3. Click "Authorize" button
4. Get token: Try `/auth/login` endpoint
5. Paste token and test other endpoints

### Option 2: cURL
```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'

# Use token
curl -H "Authorization: Bearer <your_token>" \
  http://localhost:8000/api/v1/auth/me
```

---

## 🗄️ Database

Backend connects to Supabase PostgreSQL (cloud or local Docker).

**Environment files contain:**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key-here
DATABASE_URL=postgresql://...
```

**Run migrations:**
```powershell
supabase db push
```

---

## 📚 Next Steps

- **API Reference:** `docs/reference/API_ENDPOINTS.md` - All 138 endpoints
- **Architecture:** `docs/architecture/` - System design
- **Deployment:** `docs/deployment/DEPLOYMENT_FLOW.md`

---

## 🆘 Getting Help

1. Check docs in `docs/` folder
2. Review error logs in terminal
3. Ask team lead

---

**Ready to code?** Run `.\run-local.ps1` and start building!
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
