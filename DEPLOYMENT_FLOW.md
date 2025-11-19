# 🌐 Complete Staging to Production Flow

## 📊 Visual Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEVELOPMENT WORKFLOW                        │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   LOCAL DEV  │      │   STAGING    │      │  PRODUCTION  │
│              │      │              │      │              │
│  dev branch  │─────>│staging branch│─────>│ main branch  │
│              │      │              │      │              │
└──────────────┘      └──────────────┘      └──────────────┘
      │                     │                      │
      │                     │                      │
      ▼                     ▼                      ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   DOCKER     │      │  SUPABASE    │      │  SUPABASE    │
│  Supabase    │      │   STAGING    │      │ PRODUCTION   │
│   (Local)    │      │   (Cloud)    │      │   (Cloud)    │
└──────────────┘      └──────────────┘      └──────────────┘
      │                     │                      │
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ No Emails    │      │ Real Emails  │      │ Real Emails  │
│ (Logged)     │      │ (Test SMTP)  │      │  (Prod SMTP) │
└──────────────┘      └──────────────┘      └──────────────┘
      │                     │                      │
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│Test Payments │      │Test Payments │      │Live Payments │
│  (Disabled)  │      │ (rzp_test_*) │      │ (rzp_live_*) │
└──────────────┘      └──────────────┘      └──────────────┘
```

---

## 🔄 Step-by-Step Flow

### Phase 1: Local Development (dev branch)

```bash
# Developer's laptop
┌─────────────────────────────┐
│ 1. Code new feature         │
│ 2. Test with Docker         │
│ 3. Commit to dev branch     │
│ 4. Push to GitHub           │
└─────────────────────────────┘
         │
         │ git push origin dev
         ▼
   GitHub: dev branch
```

**Environment**:
- Database: Local Docker (isolated)
- Emails: Disabled/logged only
- Payments: Disabled
- Command: `.\run-local.ps1`

---

### Phase 2: Staging Deployment (staging branch)

```bash
# Merge and deploy to staging
┌─────────────────────────────┐
│ 1. Merge dev → staging      │
│ 2. Push triggers deploy     │
│ 3. Test with real services  │
│ 4. Verify all flows         │
└─────────────────────────────┘
         │
         │ git push origin staging
         ▼
┌─────────────────────────────┐
│   Auto-Deploy (Vercel)      │
│ - Backend to staging URL    │
│ - Frontend to staging URL   │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  TEST EVERYTHING:           │
│ ✓ User registration         │
│ ✓ Email delivery            │
│ ✓ Salon creation            │
│ ✓ Booking flow              │
│ ✓ Payment (test cards)      │
│ ✓ Admin dashboard           │
└─────────────────────────────┘
```

**Environment**:
- Database: Staging Supabase (online)
- Emails: Real (Gmail/SendGrid)
- Payments: Test mode (rzp_test_*)
- URL: `https://staging-api.yourdomain.com`
- Command: `.\run-staging.ps1`

**Testing Checklist**:
- [ ] All emails received?
- [ ] Payments work with test cards?
- [ ] No errors in logs?
- [ ] Frontend-backend connected?
- [ ] Mobile responsive?

---

### Phase 3: Production Deployment (main branch)

```bash
# After staging tests pass
┌─────────────────────────────┐
│ 1. Create PR: staging→main  │
│ 2. Team review & approval   │
│ 3. Merge to main            │
│ 4. Auto-deploy to prod      │
└─────────────────────────────┘
         │
         │ git push origin main
         ▼
┌─────────────────────────────┐
│  Auto-Deploy (Production)   │
│ - Live database             │
│ - Live payments             │
│ - Real customers            │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  MONITOR:                   │
│ ✓ Error rates               │
│ ✓ Response times            │
│ ✓ Payment success rate      │
│ ✓ User feedback             │
└─────────────────────────────┘
```

**Environment**:
- Database: Production Supabase (live data!)
- Emails: Real (customer-facing)
- Payments: Live mode (rzp_live_*)
- URL: `https://api.yourdomain.com`
- Command: `.\run-production.ps1`

---

## 🗄️ Database Strategy

```
┌────────────────────────────────────────────────────────┐
│                   DATABASE SETUP                       │
└────────────────────────────────────────────────────────┘

LOCAL (Docker)                         REMOTE (Supabase)
─────────────                          ─────────────────

supabase start                         Create staging project
↓                                      ↓
PostgreSQL container                   salon-platform-staging
↓                                      ↓
Migrations applied                     supabase db push
automatically                          ↓
↓                                      Migrations applied
Test data seeded                       ↓
↓                                      Empty (or seed data)
Safe to reset/destroy                  ↓
                                       Safe to test


                                       Create production project
                                       ↓
                                       salon-platform-production
                                       ↓
                                       supabase db push
                                       ↓
                                       Migrations applied
                                       ↓
                                       REAL CUSTOMER DATA
                                       ↓
                                       ⚠️  NEVER RESET! ⚠️
```

---

## 📧 Email Configuration

```
┌────────────────────────────────────────────────────────┐
│                   EMAIL STRATEGY                       │
└────────────────────────────────────────────────────────┘

ENVIRONMENT     EMAIL_ENABLED    RECIPIENT         PURPOSE
───────────     ─────────────    ─────────         ───────
Local Dev       False            N/A               No emails sent
                                                   (logged only)

Staging         True             Test emails       Verify templates
                                 Dev team          Test flows
                                                   QA testing

Production      True             Real customers    Live emails
                                                   Transactional
```

---

## 💳 Payment Configuration

```
┌────────────────────────────────────────────────────────┐
│                  PAYMENT STRATEGY                      │
└────────────────────────────────────────────────────────┘

ENVIRONMENT     RAZORPAY MODE    TEST CARDS        REAL CARDS
───────────     ─────────────    ──────────        ──────────
Local Dev       Disabled/Test    ✅ Yes            ❌ No

Staging         Test Mode        ✅ Yes            ❌ No
                (rzp_test_*)     Always succeed    Rejected

Production      Live Mode        ❌ No             ✅ Yes
                (rzp_live_*)     Rejected          Real charges


Test Cards for Staging:
─────────────────────────
Success:  4111 1111 1111 1111
Failed:   4000 0000 0000 0002
```

---

## 🚀 Deployment Commands

### Setup (One-Time)

```bash
# 1. Create staging branch
git checkout dev
git checkout -b staging
git push -u origin staging

# 2. Setup staging environment
.\setup-staging.ps1

# 3. Link Supabase staging
supabase link --project-ref YOUR_STAGING_REF
supabase db push
```

### Regular Workflow

```bash
# Local development
git checkout dev
# ... code changes ...
git commit -am "Add feature"
git push origin dev
.\run-local.ps1  # Test locally

# Deploy to staging
git checkout staging
git merge dev
git push origin staging  # Auto-deploys!
# Visit: https://staging-app.vercel.app
# Test everything

# Deploy to production (after approval)
git checkout main
git merge staging
git push origin main  # Auto-deploys!
# Monitor production
```

---

## 🔒 Security & Best Practices

```
┌────────────────────────────────────────────────────────┐
│              ENVIRONMENT ISOLATION                     │
└────────────────────────────────────────────────────────┘

1. SEPARATE DATABASES
   ✅ Different Supabase projects
   ✅ Different passwords
   ✅ No production data in staging

2. SEPARATE API KEYS
   ✅ Different JWT secrets
   ✅ Test Razorpay keys for staging
   ✅ Live Razorpay keys for production only

3. SEPARATE ENVIRONMENTS
   ✅ .env (local)
   ✅ .env.staging (staging)
   ✅ .env.production (production)
   ⚠️  ALL in .gitignore!

4. ACCESS CONTROL
   ✅ Staging: All devs
   ✅ Production: Senior devs only
   ✅ Database: Service role key protected
```

---

## 📊 Monitoring & Logs

### Staging

```bash
# Backend logs
vercel logs --follow

# Supabase logs
# Visit: supabase.com/dashboard → Logs

# Test endpoints
curl https://staging-api.vercel.app/health
```

### Production

```bash
# Same as staging + additional monitoring
# - Sentry for error tracking
# - Datadog/New Relic for APM
# - Supabase dashboard for DB metrics
```

---

## ✅ Pre-Production Checklist

Before merging staging → main:

### Functionality
- [ ] All features work as expected
- [ ] No broken links
- [ ] All forms validate correctly
- [ ] Email templates render properly
- [ ] Payment flow completes successfully

### Performance
- [ ] Page load < 3 seconds
- [ ] API response < 500ms
- [ ] Images optimized
- [ ] No memory leaks

### Security
- [ ] Authentication works
- [ ] Authorization enforced
- [ ] SQL injection protected
- [ ] XSS protected
- [ ] CORS configured correctly
- [ ] Environment variables secure

### Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual QA complete
- [ ] Mobile tested
- [ ] Cross-browser tested

### Documentation
- [ ] API docs updated
- [ ] Changelog updated
- [ ] Team notified of changes

---

## 🔄 Rollback Strategy

If production deployment fails:

```bash
# Option 1: Revert merge commit
git checkout main
git revert HEAD
git push origin main

# Option 2: Force rollback to previous version
git reset --hard HEAD~1
git push origin main --force  # ⚠️  Use with caution!

# Option 3: Redeploy previous version
vercel rollback
```

---

## 📚 Related Documentation

| Document | Purpose |
|----------|---------|
| **STAGING_QUICK_START.md** | 5-minute setup guide |
| **STAGING_DEPLOYMENT_GUIDE.md** | Detailed deployment steps |
| **STAGING_CHECKLIST.md** | Quick testing checklist |
| **ENVIRONMENT_GUIDE.md** | Environment configuration |
| **GETTING_STARTED.md** | Local development setup |

---

**Questions?** Check the guides above or run `.\setup-staging.ps1` for help!
