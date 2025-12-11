# 🔧 Environment Configuration Guide

**Last Updated:** December 11, 2025  
**Platform:** Render.com  
**Email:** Resend API

## 📊 Overview

This project supports three environments:

| Environment | Purpose | Database | Email | Payments | Platform | Branch |
|------------|---------|----------|-------|----------|----------|--------|
| **Development** | Local coding | Docker Supabase | Disabled | Test/Disabled | Localhost | `dev/*` |
| **Staging** | Online testing | Supabase Cloud | Resend (Test) | Razorpay Test | Render.com | `staging` |
| **Production** | Live system | Supabase Cloud | Resend (Live) | Razorpay Live | Render.com | `main` |

---

## 🗂️ Environment Files

### File Structure

```
backend/
├── .env.example            # Template with all variables
├── .env.staging.example    # Staging template
├── .env.production.example # Production template
├── .env                    # Active config (gitignored)
├── .env.staging           # Staging config (gitignored)
└── .env.production        # Production config (gitignored)
```

### Which File to Use

- **Local Development**: Copy `.env.example` → `.env`
- **Staging**: Copy `.env.staging.example` → `.env.staging`
- **Production**: Copy `.env.production.example` → `.env.production`

---

## 🏃 Running Scripts

### Local Development
```bash
.\run-local.ps1     # Uses local Docker Supabase
```

### Staging
```bash
.\run-staging.ps1   # Uses staging Supabase + real emails
```

### Production
```bash
.\run-production.ps1  # Uses production Supabase
```

---

## 🔑 Key Environment Variables

### Required for ALL Environments

```env
# App Config
ENVIRONMENT=development|staging|production
DEBUG=true|false

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=

# JWT
JWT_SECRET_KEY=  # MUST be unique per environment!

# Frontend URLs
FRONTEND_URL=
ADMIN_PANEL_URL=
```

### Staging-Specific

```env
# Email - Resend API
RESEND_API_KEY=re_...
FROM_EMAIL=noreply@yourdomain.com

# Payments - TEST MODE
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=test_...

# Platform
ENVIRONMENT=staging
DEBUG=true

# Logging - More verbose
LOG_LEVEL=DEBUG
```

### Production-Specific

```env
# Email - Resend API
RESEND_API_KEY=re_...
FROM_EMAIL=noreply@yourdomain.com

# Payments - LIVE MODE
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=live_...

# Platform
ENVIRONMENT=production
DEBUG=false

# Logging - Production level
LOG_LEVEL=INFO
```

---

## 🔄 Environment Switching

### Backend

Scripts automatically switch for you:

```bash
# This copies .env.staging → .env
.\run-staging.ps1

# This copies .env.production → .env
.\run-production.ps1
```

### Frontend

Update environment variables in deployment platform:

- **Vercel**: Project Settings → Environment Variables (Primary)
- **Netlify**: Site Settings → Environment Variables
- **Render**: Environment → Environment Variables

---

## 🎯 Configuration Checklist

### Development Setup
- [ ] `.env` exists (copied from `.env.example`)
- [ ] Docker Desktop running
- [ ] Supabase local: `supabase start`
- [ ] `EMAIL_ENABLED=False`
- [ ] `DEBUG=True`

### Staging Setup
- [ ] `.env.staging` exists with real credentials
- [ ] Staging Supabase project created
- [ ] Migrations applied: `supabase db push`
- [ ] Gmail SMTP configured
- [ ] `EMAIL_ENABLED=True`
- [ ] Razorpay **TEST** keys
- [ ] Frontend deployed and URLs updated

### Production Setup
- [ ] `.env.production` with production credentials
- [ ] Production Supabase project
- [ ] Strong JWT secret (different from staging!)
- [ ] Production SMTP configured
- [ ] Razorpay **LIVE** keys
- [ ] Frontend production URLs
- [ ] `DEBUG=False`
- [ ] `LOG_LEVEL=INFO`

---

## 🔒 Security Best Practices

### DO ✅
- Use different JWT secrets for each environment
- Use Razorpay TEST keys in staging
- Keep `.env*` files in `.gitignore`
- Use Gmail App Passwords (not regular password)
- Rotate secrets regularly
- Use strong, random JWT secrets (32+ chars)

### DON'T ❌
- Never commit `.env*` to git
- Never use production keys in staging
- Never share JWT secrets publicly
- Never hardcode secrets in code
- Never reuse passwords across environments

---

## 📧 Email Configuration

### Development (No Emails)
```env
EMAIL_ENABLED=False
```
Emails logged to console only.

### Staging/Production (Real Emails)

**Option A: Gmail**
```env
EMAIL_ENABLED=True
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password  # From Google Account
SMTP_TLS=True
```

**Option B: SendGrid**
```env
EMAIL_ENABLED=True
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
SMTP_TLS=True
```

---

## 💳 Payment Configuration

### Razorpay Setup

**Staging (Test Mode)**:
```env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=test_...
```

**Production (Live Mode)**:
```env
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=live_...
```

Get keys from: https://dashboard.razorpay.com/app/keys

---

## 🧪 Testing Your Configuration

### Test Locally
```bash
.\run-staging.ps1

# Visit: http://localhost:8000/docs
# Test: Registration → Check email
# Test: Payment → Use test card
```

### Test Deployed
```bash
# Check health endpoint
curl https://your-staging-api.vercel.app/health

# Check environment
curl https://your-staging-api.vercel.app/api/v1/health
```

---

## 🐛 Troubleshooting

### Backend won't start
**Check**: `.env` file exists and has required variables

### Emails not sending
**Check**: 
- `EMAIL_ENABLED=True`
- Gmail App Password (not regular password)
- SMTP credentials correct

### Database connection failed
**Check**:
- Supabase URL and keys correct
- Database password in `DATABASE_URL`
- Project not paused (Supabase dashboard)

### CORS errors
**Check**: `ALLOWED_ORIGINS` includes your frontend URL

---

## 📚 Related Documentation

- [STAGING_DEPLOYMENT_GUIDE.md](./STAGING_DEPLOYMENT_GUIDE.md) - Detailed staging setup
- [STAGING_CHECKLIST.md](./STAGING_CHECKLIST.md) - Quick reference
- [GETTING_STARTED.md](./GETTING_STARTED.md) - Local development setup

---

**Last Updated**: November 19, 2025
