# 🎯 Quick Staging Checklist

Use this quick reference when deploying to staging.

## 🚀 Initial Setup (One-Time)

### 1. Create Staging Branch
```bash
git checkout dev
git checkout -b staging
git push -u origin staging
```

### 2. Create Staging Supabase Project
- [ ] Go to [supabase.com/dashboard](https://supabase.com/dashboard)
- [ ] Create new project: `salon-platform-staging`
- [ ] Save database password
- [ ] Copy Project URL and API keys
- [ ] Apply migrations: `supabase db push`

### 3. Setup Backend Environment
- [ ] Copy: `Copy-Item .env.staging.example .env.staging`
- [ ] Fill in Supabase credentials
- [ ] Generate new JWT secret (32+ chars)
- [ ] Configure Gmail SMTP or SendGrid
- [ ] Add Razorpay TEST keys
- [ ] Set `EMAIL_ENABLED=True`

### 4. Deploy Frontend
- [ ] Deploy admin panel → Get URL
- [ ] Deploy salon app → Get URL
- [ ] Update `.env.staging` with frontend URLs
- [ ] Update `ALLOWED_ORIGINS` with deployed URLs

---

## 🔄 Regular Deployment Workflow

### When to Deploy to Staging
✅ After completing features locally
✅ Before merging to production
✅ When testing with real integrations needed

### Deployment Steps

```bash
# 1. Update staging with latest dev changes
git checkout staging
git merge dev
git push origin staging

# 2. Test locally with staging config (optional)
.\run-staging.ps1

# 3. Deploy happens automatically (Vercel/Railway)
# Or manually: vercel --prod

# 4. Test on deployed URL
# https://staging-salon-app.vercel.app
```

---

## ✅ Testing Checklist

After each staging deployment, verify:

### Core Flows
- [ ] User registration + email confirmation
- [ ] User login
- [ ] Password reset + email
- [ ] Google OAuth

### Salon Features
- [ ] Create salon (RM portal)
- [ ] Upload salon images
- [ ] Salon approval workflow
- [ ] Search salons (customer app)

### Booking Flow
- [ ] Search services
- [ ] Select time slot
- [ ] Complete booking
- [ ] Test payment (use test card: 4111 1111 1111 1111)
- [ ] Check booking confirmation email

### Admin Panel
- [ ] Login to admin panel
- [ ] View dashboard stats
- [ ] Manage salons
- [ ] View payments

---

## 🐛 Common Issues

### ❌ CORS Error
**Fix**: Update `ALLOWED_ORIGINS` in `.env.staging` with actual deployed URLs

### ❌ Emails Not Sending
**Check**:
- `EMAIL_ENABLED=True`
- Gmail App Password (not regular password)
- Check spam folder

### ❌ Database Connection Failed
**Check**:
- Supabase project is not paused
- Database URL has correct password
- Migrations applied: `supabase db push`

### ❌ 401 Unauthorized
**Check**:
- JWT_SECRET_KEY matches between backend and deployed version
- Frontend is using correct API URL
- Supabase anon key is correct

---

## 🔒 Security Reminders

- ✅ Use **TEST** Razorpay keys (rzp_test_*)
- ✅ Different JWT secret than production
- ✅ Separate Supabase project for staging
- ✅ `.env.staging` is in `.gitignore`
- ✅ No real customer data in staging

---

## 📊 Quick Commands

```bash
# View backend logs (Vercel)
vercel logs --follow

# Re-apply migrations
supabase link --project-ref YOUR_STAGING_REF
supabase db push

# Test locally with staging
.\run-staging.ps1

# Deploy backend manually
vercel --prod

# Generate JWT secret
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

---

## 🎯 Ready for Production?

Before merging `staging` → `main`:

- [ ] All staging tests pass
- [ ] No critical bugs
- [ ] Performance acceptable
- [ ] Email flows verified
- [ ] Payment flows tested
- [ ] Security review done
- [ ] Team approval received

```bash
# Merge to production
git checkout main
git merge staging
git push origin main
```

---

**For detailed instructions**, see [STAGING_DEPLOYMENT_GUIDE.md](./STAGING_DEPLOYMENT_GUIDE.md)
