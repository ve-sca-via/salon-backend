# 🚀 Staging Deployment Guide

## 📋 Overview

This guide walks you through setting up and deploying to the **staging environment** for online testing with real integrations.

### Purpose of Staging
- ✅ Test with **real Supabase** (online database)
- ✅ Test with **real email** sending
- ✅ Test **payment flows** (using Razorpay test mode)
- ✅ Test **authentication** flows end-to-end
- ✅ Verify **frontend-backend** integration
- ⚠️ **DO NOT** use real payment cards - use test cards only!

---

## 🎯 Staging Environment Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT FLOW                          │
└─────────────────────────────────────────────────────────────┘

Local Dev          Staging             Production
(dev branch)    (staging branch)     (main branch)
    │                  │                    │
    │   Test locally   │                    │
    │   with Docker    │                    │
    │                  │                    │
    ├─────────────────>│  Deploy & test     │
    │   Push to        │  with real         │
    │   staging        │  services          │
    │                  │                    │
    │                  ├───────────────────>│
    │                  │  Merge to main     │
    │                  │  after approval    │
    │                  │                    │
```

---

## 🏗️ Step 1: Create Staging Branch

### On GitHub

1. **Create `staging` branch** from `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b staging
   git push -u origin staging
   ```

2. **Set branch protection rules** (optional):
   - Go to GitHub → Settings → Branches
   - Add rule for `staging`:
     - ✅ Require pull request before merging
     - ✅ Require status checks to pass

### Branch Strategy

```
main (production)
  ↑
  └── staging (online testing)
        ↑
        └── dev (local development)
              ↑
              └── feature/* (new features)
```

---

## 🗄️ Step 2: Setup Staging Supabase Project

### Create New Supabase Project

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard)

2. **Create new project**:
   - **Name**: `salon-platform-staging`
   - **Database Password**: Save this securely!
   - **Region**: Same as production (for consistency)
   - **Plan**: Free tier is fine for staging

3. **Wait for project to initialize** (takes 2-3 minutes)

### Get Credentials

Once ready, go to **Settings → API**:

```
Project URL:    https://xxxxx.supabase.co
anon public:    eyJhbGc...
service_role:   eyJhbGc... (keep secret!)
```

Go to **Settings → Database** for connection string:

```
postgres://postgres:[PASSWORD]@db.xxxxx.supabase.co:5432/postgres
```

### Apply Migrations

```bash
# Link to staging project
cd g:\vescavia\Projects\backend
supabase link --project-ref your-staging-project-ref

# Push all migrations to staging
supabase db push

# Verify migrations applied
supabase db diff
```

---

## 🔧 Step 3: Configure Backend for Staging

### Create `.env.staging`

```bash
cd g:\vescavia\Projects\backend
Copy-Item .env.staging.example .env.staging
```

### Edit `.env.staging` with Real Values

```env
# Supabase Staging
SUPABASE_URL="https://YOUR_STAGING_REF.supabase.co"
SUPABASE_ANON_KEY="eyJhbGc..."
SUPABASE_SERVICE_ROLE_KEY="eyJhbGc..."
DATABASE_URL="postgresql://postgres:[PASSWORD]@db.YOUR_STAGING_REF.supabase.co:5432/postgres"

# JWT (generate new secret for staging)
JWT_SECRET_KEY="<generate-random-32-char-string>"

# Email (use real SMTP)
EMAIL_ENABLED=True
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your-staging-email@gmail.com"
SMTP_PASSWORD="your-gmail-app-password"  # Use App Password!

# Razorpay TEST keys (NOT live keys!)
RAZORPAY_KEY_ID="rzp_test_..."
RAZORPAY_KEY_SECRET="test_..."

# Frontend URLs (update after deploying frontend)
FRONTEND_URL="https://staging-salon-app.vercel.app"
ADMIN_PANEL_URL="https://staging-admin.vercel.app"

# CORS
ALLOWED_ORIGINS="https://staging-salon-app.vercel.app,https://staging-admin.vercel.app,http://localhost:5173,http://localhost:5174"
```

### Generate JWT Secret

```powershell
# Generate secure random string (PowerShell)
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

---

## 📧 Step 4: Configure Email (Gmail Example)

### Option A: Gmail SMTP

1. **Enable 2-Factor Authentication** on your Gmail account

2. **Generate App Password**:
   - Go to: https://myaccount.google.com/apppasswords
   - Select app: "Mail"
   - Select device: "Other" → "Staging Backend"
   - Copy the 16-character password

3. **Update `.env.staging`**:
   ```env
   EMAIL_ENABLED=True
   SMTP_HOST="smtp.gmail.com"
   SMTP_PORT=587
   SMTP_USER="your-email@gmail.com"
   SMTP_PASSWORD="your-16-char-app-password"
   SMTP_TLS=True
   EMAIL_FROM="your-email@gmail.com"
   ```

### Option B: SendGrid (Recommended for Production)

1. Sign up at [sendgrid.com](https://sendgrid.com)
2. Create API key
3. Update `.env.staging`:
   ```env
   SMTP_HOST="smtp.sendgrid.net"
   SMTP_PORT=587
   SMTP_USER="apikey"
   SMTP_PASSWORD="your-sendgrid-api-key"
   ```

---

## 💳 Step 5: Configure Razorpay Test Mode

1. **Log in to Razorpay Dashboard**: https://dashboard.razorpay.com

2. **Switch to TEST mode** (toggle at top)

3. **Get Test Keys**:
   - Go to Settings → API Keys
   - Copy **Test Key ID** and **Test Key Secret**

4. **Update `.env.staging`**:
   ```env
   RAZORPAY_KEY_ID="rzp_test_..."
   RAZORPAY_KEY_SECRET="test_..."
   ```

5. **Test Cards** (use these for staging):
   - Success: `4111 1111 1111 1111`
   - CVV: Any 3 digits
   - Expiry: Any future date

---

## 🌐 Step 6: Deploy Frontend to Staging

### Option A: Vercel (Recommended)

#### Backend Deployment

1. **Install Vercel CLI**:
   ```bash
   npm install -g vercel
   ```

2. **Deploy Backend**:
   ```bash
   cd g:\vescavia\Projects\backend
   git checkout staging
   
   # Login to Vercel
   vercel login
   
   # Deploy
   vercel --prod
   ```

3. **Set Environment Variables** in Vercel Dashboard:
   - Go to Project → Settings → Environment Variables
   - Add all variables from `.env.staging`
   - Deploy again to apply

#### Frontend Deployments

```bash
# Main App
cd g:\vescavia\Projects\salon-management-app
git checkout staging
vercel --prod
# Note the URL: https://staging-salon-app.vercel.app

# Admin Panel
cd g:\vescavia\Projects\salon-admin-panel
git checkout staging
vercel --prod
# Note the URL: https://staging-admin.vercel.app
```

4. **Update Backend CORS**:
   - Edit `.env.staging` with actual Vercel URLs
   - Redeploy backend

### Option B: Railway

1. Go to [railway.app](https://railway.app)
2. Connect GitHub repo
3. Select `staging` branch
4. Add environment variables from `.env.staging`
5. Deploy

---

## 🧪 Step 7: Test Staging Environment

### Run Backend Locally (Connected to Staging Supabase)

```bash
cd g:\vescavia\Projects\backend
.\run-staging.ps1
```

This will:
- ✅ Connect to **staging Supabase** (online)
- ✅ Send **real emails**
- ✅ Use **test payment gateway**

### Test Checklist

- [ ] **Authentication**
  - [ ] User registration (check email received)
  - [ ] User login
  - [ ] Password reset (check email)
  - [ ] Google OAuth

- [ ] **Salon Management**
  - [ ] Create salon
  - [ ] Upload images (Supabase storage)
  - [ ] Verify salon (RM flow)
  - [ ] Check email notifications

- [ ] **Booking Flow**
  - [ ] Search salons
  - [ ] Book appointment
  - [ ] Payment with test card
  - [ ] Check booking confirmation email

- [ ] **Admin Panel**
  - [ ] View dashboard
  - [ ] Manage salons
  - [ ] View payments

---

## 🚀 Step 8: Continuous Deployment Setup

### Automatic Deployment on Push

#### For Vercel

Vercel auto-deploys when you push to `staging` branch!

```bash
# Make changes
git checkout staging
git pull origin dev  # Merge latest from dev
git push origin staging  # Auto-deploys!
```

#### For Railway

Railway also auto-deploys on push to connected branch.

---

## 🔄 Workflow Summary

### Daily Development Workflow

```bash
# 1. Work on feature locally (dev branch)
git checkout dev
git checkout -b feature/new-feature
# ... make changes ...
git commit -m "Add new feature"
git push origin feature/new-feature

# 2. Merge to dev after review
git checkout dev
git merge feature/new-feature
git push origin dev

# 3. Deploy to staging for online testing
git checkout staging
git merge dev
git push origin staging  # Auto-deploys!

# 4. Test on staging
# Visit: https://staging-salon-app.vercel.app
# Test all features with real integrations

# 5. If tests pass, merge to production
git checkout main
git merge staging
git push origin main  # Deploys to production!
```

### Branch Protection

**Recommended rules:**

- `main` (production):
  - ✅ Require PR from `staging` only
  - ✅ Require 2 approvals
  - ✅ Require status checks

- `staging`:
  - ✅ Require PR from `dev`
  - ✅ Require 1 approval

- `dev`:
  - ✅ Require PR from feature branches
  - ✅ Allow direct pushes for quick fixes

---

## 🔒 Security Checklist

- [ ] **.env.staging** is in `.gitignore`
- [ ] **Different JWT secret** for each environment
- [ ] **Razorpay TEST keys** (not live) in staging
- [ ] **Separate Supabase project** for staging
- [ ] **Email subject** shows "STAGING" prefix
- [ ] **App title** shows "STAGING" badge
- [ ] **No real customer data** in staging

---

## 🐛 Troubleshooting

### Issue: CORS Errors

**Solution**: Update `ALLOWED_ORIGINS` in `.env.staging`:
```env
ALLOWED_ORIGINS="https://your-actual-staging-url.vercel.app,http://localhost:5173"
```

### Issue: Email Not Sending

**Check**:
1. `EMAIL_ENABLED=True`
2. Gmail App Password (not regular password)
3. Check spam folder
4. Check backend logs for SMTP errors

### Issue: Database Connection Failed

**Check**:
1. Supabase project is active (not paused)
2. Database password is correct in `DATABASE_URL`
3. IP whitelist (if enabled) includes your deployment

### Issue: Migrations Not Applied

```bash
# Re-apply migrations
supabase link --project-ref your-staging-ref
supabase db reset
```

---

## 📊 Monitoring Staging

### Backend Logs

**Vercel**:
```bash
vercel logs --follow
```

**Railway**:
- View logs in Railway dashboard

### Supabase Logs

1. Go to Supabase Dashboard → Logs
2. Check:
   - API logs
   - Database logs
   - Auth logs

### Email Delivery

- Check Gmail Sent folder
- Check SendGrid dashboard
- Test with: https://mailtrap.io (for staging only)

---

## ✅ Pre-Production Checklist

Before merging `staging` → `main`:

- [ ] All features tested on staging
- [ ] No critical bugs found
- [ ] Email notifications working
- [ ] Payment flow tested (test cards)
- [ ] Authentication flows verified
- [ ] Admin panel functional
- [ ] Mobile responsiveness checked
- [ ] Performance acceptable (<3s load time)
- [ ] Database migrations successful
- [ ] Security audit passed
- [ ] Backup strategy in place

---

## 📚 Additional Resources

- [Supabase Documentation](https://supabase.com/docs)
- [Vercel Deployment Guide](https://vercel.com/docs)
- [Razorpay Test Cards](https://razorpay.com/docs/payments/payments/test-card-details/)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)

---

## 🆘 Need Help?

1. Check backend logs: `vercel logs`
2. Check Supabase dashboard for database errors
3. Test locally with staging config: `.\run-staging.ps1`
4. Review this guide's troubleshooting section

---

**Last Updated**: November 19, 2025
**Maintained By**: Backend Team
