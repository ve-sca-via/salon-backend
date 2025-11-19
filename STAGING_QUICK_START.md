# 🎯 STAGING DEPLOYMENT - QUICK SUMMARY

## What is Staging?

**Staging** is an online testing environment that:
- ✅ Uses **real Supabase** (cloud database)
- ✅ Sends **real emails** to test email flows
- ✅ Uses **Razorpay test mode** for payments
- ✅ Tests with **deployed frontend** apps
- ⚠️ Separate from production (safe to break!)

---

## 🚀 Getting Started (5 Steps)

### 1. Create Staging Branch (GitHub)
```bash
git checkout dev
git checkout -b staging
git push -u origin staging
```

### 2. Create Staging Supabase Project
1. Go to https://supabase.com/dashboard
2. Click "New Project" → Name it `salon-platform-staging`
3. Save the database password!
4. Copy: URL, anon key, service role key

### 3. Setup Backend Environment
```bash
# Run the setup wizard (easiest!)
.\setup-staging.ps1

# Or manually:
Copy-Item .env.staging.example .env.staging
# Edit .env.staging with your Supabase credentials
```

### 4. Apply Database Migrations
```bash
supabase link --project-ref your-staging-project-ref
supabase db push
```

### 5. Deploy Frontend & Test
- Deploy admin panel to Vercel/Netlify
- Deploy salon app to Vercel/Netlify
- Update `.env.staging` with deployed URLs
- Test everything!

---

## 📧 Email Setup (Gmail)

1. Enable 2-Factor Auth on Gmail
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Add to `.env.staging`:
```env
EMAIL_ENABLED=True
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
```

---

## 💳 Payment Setup (Razorpay)

1. Go to https://dashboard.razorpay.com
2. Switch to **TEST mode** (toggle at top)
3. Copy test keys from Settings → API Keys
4. Add to `.env.staging`:
```env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=test_...
```

**Test Card**: `4111 1111 1111 1111` (always succeeds)

---

## 🔄 Daily Workflow

```bash
# 1. Work on features locally (dev branch)
git checkout dev
# ... make changes ...
git commit -am "Add feature"
git push origin dev

# 2. Deploy to staging for online testing
git checkout staging
git merge dev
git push origin staging  # Auto-deploys!

# 3. Test on staging URL
# https://staging-salon-app.vercel.app

# 4. If tests pass, merge to production
git checkout main
git merge staging
git push origin main
```

---

## ✅ What to Test on Staging

- [ ] User registration (check email)
- [ ] User login
- [ ] Password reset (check email)
- [ ] Create salon (RM portal)
- [ ] Upload images
- [ ] Search & book appointment
- [ ] Payment with test card
- [ ] Check booking confirmation email
- [ ] Admin panel dashboard

---

## 🐛 Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| CORS error | Update `ALLOWED_ORIGINS` in `.env.staging` |
| Emails not sending | Check Gmail App Password (not regular password) |
| Database error | Verify Supabase project not paused |
| 401 Unauthorized | Check JWT_SECRET_KEY matches |

---

## 🔒 Security Checklist

- ✅ Use **different** JWT secrets for staging & production
- ✅ Use Razorpay **TEST** keys (rzp_test_*)
- ✅ Keep `.env.staging` in `.gitignore`
- ✅ Never commit secrets to Git
- ✅ Separate Supabase project for staging

---

## 📚 Full Documentation

| Document | Purpose |
|----------|---------|
| **STAGING_DEPLOYMENT_GUIDE.md** | Complete step-by-step guide |
| **STAGING_CHECKLIST.md** | Quick reference checklist |
| **ENVIRONMENT_GUIDE.md** | Environment configuration details |
| **GETTING_STARTED.md** | Local development setup |

---

## 🆘 Need Help?

1. **Setup issues**: Run `.\setup-staging.ps1` for guided setup
2. **Testing locally**: Run `.\run-staging.ps1` 
3. **View logs**: `vercel logs --follow`
4. **Check Supabase**: Visit dashboard → Logs

---

## 📊 Branch Strategy

```
main (production)          ← Live system
  ↑
  merge after testing
  ↑
staging (online testing)   ← Test with real services
  ↑
  merge daily
  ↑
dev (local development)    ← Daily coding
  ↑
  PR from features
  ↑
feature/* branches         ← New features
```

---

**Ready to Deploy?** 🚀

```bash
# Quick setup
.\setup-staging.ps1

# Or manual
Copy-Item .env.staging.example .env.staging
# Fill in credentials
.\run-staging.ps1
```

**Questions?** Read [STAGING_DEPLOYMENT_GUIDE.md](./STAGING_DEPLOYMENT_GUIDE.md)
