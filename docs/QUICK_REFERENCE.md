# ⚡ Quick Reference Card

## 🚀 Most Common Commands

```powershell
# ===== DAILY WORKFLOW =====

# 1. Start local development
.\run-local.ps1

# 2. Stop Supabase when done
supabase stop

# ===== WHEN SCHEMA CHANGES =====

# Pull latest schema from production
supabase db pull

# Apply to local database
supabase db reset

# ===== TROUBLESHOOTING =====

# Check Supabase status
supabase status

# Restart Supabase
supabase stop
supabase start

# View Supabase logs
supabase logs

# ===== RARELY USED =====

# Run on production (DANGEROUS!)
.\run-production.ps1
```

---

## 📁 File Meanings

| File | Safe to Commit? | Purpose |
|------|----------------|---------|
| `.env` | ❌ No | Active config (auto-generated) |
| `.env.local` | ✅ Yes | Localhost config (for team) |
| `.env.production` | ❌ No | Real production secrets |
| `.env.production.example` | ✅ Yes | Template (no secrets) |

---

## 🌍 Environment Quick Check

**Which environment am I using?**

```powershell
# Check your .env file:
Get-Content .env | Select-String "SUPABASE_URL"

# If you see:
# http://127.0.0.1:54321  → LOCAL ✅
# https://xxx.supabase.co → PRODUCTION ⚠️
```

---

## 🆘 Emergency Reset

**Something broken? Start fresh:**

```powershell
# 1. Stop everything
supabase stop

# 2. Remove Docker volumes
docker volume rm supabase_db_backend supabase_storage_backend supabase_config_backend supabase_edge_runtime_backend

# 3. Start fresh
supabase start

# 4. Apply schema
supabase db reset
```

---

## 📞 Quick Links

- **API Docs (Local):** http://localhost:8000/docs
- **Supabase Studio (Local):** http://127.0.0.1:54323
- **Production Dashboard:** https://supabase.com/dashboard

---

**Print this and keep it handy! 📋**
