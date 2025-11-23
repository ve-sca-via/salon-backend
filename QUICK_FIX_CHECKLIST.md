# Quick Fix Checklist - Service Role Architecture

## ✅ Completed Tasks

- [x] Created RLS disable migration
- [x] Documented architecture in `database.py`
- [x] Created comprehensive auth documentation
- [x] Added rate limiting to auth endpoints
- [x] Created security audit scripts
- [x] Validated backend security model

## 🚨 CRITICAL: Fix Before Deployment

### 1. Remove SERVICE_ROLE from Frontend (URGENT)

**Admin Panel:**
```bash
cd salon-admin-panel

# Edit .env.example - REMOVE this line:
# VITE_SUPABASE_SERVICE_ROLE_KEY=...

# Edit .env - REMOVE this line:
# VITE_SUPABASE_SERVICE_ROLE_KEY=...

# Should only have:
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...  # Public key only
VITE_BACKEND_URL=http://localhost:8000
```

**Management App:**
```bash
cd salon-management-app

# Check if it has service_role key
grep -r "SERVICE_ROLE" .env*

# If found, REMOVE IT immediately
```

### 2. Rotate Compromised Keys

Since service_role might be exposed:

**Supabase Dashboard:**
1. Go to Settings → API
2. Click "Reset service_role key"
3. Copy new key

**Backend .env:**
```bash
# Update with new key
SUPABASE_SERVICE_ROLE_KEY=<new-key-here>
```

**Also rotate:**
```bash
# Generate new JWT secret (32+ chars)
JWT_SECRET_KEY=$(openssl rand -base64 48)

# Update .env with new secret
```

### 3. Apply Database Migration

```bash
# Connect to Supabase
supabase link --project-ref <your-project-ref>

# Apply RLS disable migration
supabase db push

# Verify
supabase db diff
```

### 4. Validate Security

```bash
# Run validation
python scripts/validate_security.py

# Should show 0 critical issues
# If issues found, fix them before proceeding
```

### 5. Update .gitignore

Add to `.gitignore` in backend:
```
.env
.env.local
.env.production
.env.staging
*.pem
*.key
```

Add to `.gitignore` in frontends:
```
.env
.env.local
.env.production
```

### 6. Check Git History

```bash
# Search for accidentally committed secrets
git log --all --full-history -- "*/.env"
git log -S "SERVICE_ROLE_KEY"

# If found in history, consider:
# - Rotating all keys
# - Using git-filter-repo to clean history (DANGEROUS)
```

## 📋 Deployment Checklist

### Pre-Deployment
- [ ] Service role key removed from all frontends
- [ ] All secrets rotated (service_role, JWT_SECRET_KEY)
- [ ] Backend .env updated with new keys
- [ ] RLS migration applied to staging database
- [ ] Security validation passes (0 critical issues)
- [ ] Rate limiting tested on auth endpoints
- [ ] .gitignore updated
- [ ] No secrets in git history

### Staging Deployment
- [ ] Deploy backend to staging
- [ ] Apply RLS migration to staging DB
- [ ] Test login flow
- [ ] Test rate limiting (try 6 logins in 1 min)
- [ ] Test admin operations
- [ ] Verify no direct Supabase calls from frontend
- [ ] Check logs for errors

### Production Deployment
- [ ] Backup production database
- [ ] Apply RLS migration to production DB
- [ ] Deploy backend to production
- [ ] Deploy frontends to production
- [ ] Smoke test: Login, create booking, admin action
- [ ] Monitor error rates for 1 hour
- [ ] Verify rate limiting working

## 🔧 Testing Commands

```bash
# Backend
cd backend
python scripts/validate_security.py
python scripts/audit_security.py

# Start backend
python main.py

# Test login rate limit (should fail on 6th attempt)
for i in {1..6}; do 
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"wrong"}'; 
  echo "\nAttempt $i"; 
done
```

## 📚 Documentation Links

- **Architecture Guide:** `docs/ARCHITECTURE_AUTH.md`
- **Implementation Summary:** `IMPLEMENTATION_SUMMARY.md`
- **API Testing:** `API_TESTING_GUIDE.md`
- **Environment Setup:** `ENVIRONMENT_GUIDE.md`

## 🆘 Troubleshooting

### "Permission denied for table X"
- RLS is still enabled
- Run migration: `20251123000000_disable_rls_for_service_role_architecture.sql`

### "Rate limit exceeded" in tests
- Wait 1 minute between test runs
- Or use different IP addresses

### "Invalid token"
- JWT_SECRET_KEY mismatch
- Check backend .env matches what was used to sign tokens
- Users need to re-login after JWT_SECRET_KEY rotation

### Frontend can't access backend
- Check CORS settings in backend
- Verify VITE_BACKEND_URL in frontend .env
- Check browser console for errors

## 🎯 Success Criteria

✅ Backend security validation passes  
✅ No service_role key in frontend  
✅ Rate limiting works on auth endpoints  
✅ RLS disabled on all tables  
✅ All secrets rotated and secure  
✅ Frontend uses backend API only  
✅ Login flow works end-to-end  
✅ Admin operations work  
✅ No security warnings in logs  

---

**Remember:** This is about hardening the fortress, not just painting it. Every step matters.
