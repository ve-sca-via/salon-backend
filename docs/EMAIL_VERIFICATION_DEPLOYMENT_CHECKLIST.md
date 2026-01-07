# Email Verification - Production Deployment Checklist

## Pre-Deployment Verification

### ✅ Local Testing Complete
- [ ] Signed up with test account
- [ ] Banner appeared after signup
- [ ] Received branded email (not generic Supabase)
- [ ] Email verification link works
- [ ] Banner disappears after verification
- [ ] Resend button works
- [ ] Rate limiting tested (max 3 resends/hour)
- [ ] Banner is dismissible
- [ ] Banner reappears on refresh (if still unverified)
- [ ] Tested on mobile devices
- [ ] Tested on different browsers

### ✅ Code Review
- [ ] All files committed to git
- [ ] No console.log statements left in production code
- [ ] Error handling in place
- [ ] No hardcoded URLs or tokens
- [ ] Environment variables documented

## Supabase Production Configuration

### 1. Email Templates Upload
**Location:** Supabase Dashboard → Authentication → Email Templates

- [ ] Navigate to Supabase Dashboard
- [ ] Go to Authentication section
- [ ] Click on "Email Templates"
- [ ] Find "Confirm signup" template
  - [ ] Click "Edit"
  - [ ] Copy content from `backend/supabase/templates/confirmation.html`
  - [ ] Paste into template editor
  - [ ] Update subject to: "Welcome to Lubist - Confirm Your Email 🎉"
  - [ ] Click "Save"
- [ ] Find "Magic Link" template
  - [ ] Click "Edit"
  - [ ] Copy content from `backend/supabase/templates/magic_link.html`
  - [ ] Paste into template editor
  - [ ] Update subject to: "Sign in to Lubist - Your Magic Link ✨"
  - [ ] Click "Save"

### 2. Enable Email Confirmations
**Location:** Supabase Dashboard → Authentication → Providers

- [ ] Navigate to Authentication → Providers
- [ ] Find "Email" provider
- [ ] Click "Edit"
- [ ] Enable "Confirm email" toggle
- [ ] Set "Confirmation URL" to your production URL
- [ ] Click "Save"

### 3. Configure Redirect URLs
**Location:** Supabase Dashboard → Authentication → URL Configuration

- [ ] Navigate to Authentication → URL Configuration
- [ ] Set "Site URL" to: `https://yourdomain.com`
- [ ] Add to "Redirect URLs":
  - [ ] `https://yourdomain.com`
  - [ ] `https://yourdomain.com/**` (for wildcard)
  - [ ] `https://www.yourdomain.com` (if using www)
- [ ] Click "Save"

### 4. Email Provider Settings
**Location:** Supabase Dashboard → Project Settings → Auth

- [ ] Check email rate limits are appropriate
- [ ] Verify email from address (if custom SMTP)
- [ ] Test email deliverability
- [ ] Configure SPF/DKIM if using custom domain (optional)

## Backend Environment Variables

### Update Production .env
```env
# Frontend URLs
FRONTEND_URL=https://yourdomain.com
ADMIN_PANEL_URL=https://admin.yourdomain.com
VENDOR_PORTAL_URL=https://yourdomain.com/vendor
RM_PORTAL_URL=https://yourdomain.com/rm

# Supabase (verify these are production values)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-production-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-production-service-role-key

# JWT (ensure these are secure and different from dev)
JWT_SECRET_KEY=your-super-secure-production-jwt-key-min-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

- [ ] All URLs updated to production domains
- [ ] JWT_SECRET_KEY is secure (min 32 chars)
- [ ] Supabase keys are for production project
- [ ] No development values left

## Frontend Environment Variables

### Update Production .env
```env
VITE_API_BASE_URL=https://api.yourdomain.com
# or if backend is on same domain:
VITE_API_BASE_URL=https://yourdomain.com
```

- [ ] API URL points to production backend
- [ ] No localhost URLs
- [ ] HTTPS enabled

## DNS & Domain Configuration

### Domain Setup
- [ ] DNS records configured
- [ ] SSL certificates installed
- [ ] HTTPS redirect enabled
- [ ] WWW redirect configured (if applicable)

### CORS Configuration
**Backend:** Ensure production domains are in ALLOWED_ORIGINS

```python
# In backend/app/core/config.py
ALLOWED_ORIGINS: str = Field(
    default="https://yourdomain.com,https://www.yourdomain.com"
)
```

- [ ] Frontend domain added to CORS origins
- [ ] Admin panel domain added (if different)
- [ ] Remove any localhost/development URLs

## Database & Migration

### Production Database
- [ ] All migrations applied
- [ ] Database backup taken
- [ ] Connection pool configured
- [ ] Row-level security policies in place (if applicable)

## Deployment Steps

### Backend Deployment
```bash
# 1. Pull latest code
git pull origin main

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply migrations (if any)
# Supabase migrations are applied via Supabase CLI

# 4. Restart backend service
# (depends on your hosting - Render, Railway, etc.)
```

- [ ] Code deployed
- [ ] Dependencies updated
- [ ] Service restarted
- [ ] Health check passed

### Frontend Deployment
```bash
# 1. Pull latest code
git pull origin main

# 2. Install dependencies
npm install

# 3. Build for production
npm run build

# 4. Deploy (Vercel, Netlify, etc.)
# (automatic if connected to git)
```

- [ ] Code deployed
- [ ] Build successful
- [ ] Assets uploaded to CDN
- [ ] DNS propagated

## Post-Deployment Testing

### Smoke Tests
- [ ] Visit production URL - site loads
- [ ] Sign up flow works
- [ ] Banner appears after signup
- [ ] Email received with branding
- [ ] Email links work and redirect correctly
- [ ] Verification completes successfully
- [ ] Banner disappears after verification
- [ ] Resend email works
- [ ] Rate limiting works

### Email Deliverability
- [ ] Test with Gmail account
- [ ] Test with Outlook account
- [ ] Test with other providers
- [ ] Check spam folder placement
- [ ] Verify SPF/DKIM (if custom domain)

### Cross-Browser Testing
- [ ] Chrome (desktop)
- [ ] Firefox (desktop)
- [ ] Safari (desktop)
- [ ] Edge (desktop)
- [ ] Chrome (mobile)
- [ ] Safari (iOS)

### Mobile Testing
- [ ] Banner displays correctly on mobile
- [ ] Email is readable on mobile
- [ ] Buttons are tappable
- [ ] Text is readable (no tiny fonts)

## Monitoring & Analytics

### Setup Monitoring
- [ ] Error tracking configured (Sentry, etc.)
- [ ] Email delivery monitoring
- [ ] API endpoint monitoring
- [ ] User signup funnel tracking

### Metrics to Track
- [ ] Signup completion rate
- [ ] Email verification rate
- [ ] Time to verification
- [ ] Resend email usage
- [ ] Banner dismissal rate

## Rollback Plan

### If Issues Occur
```bash
# 1. Revert backend code
git revert <commit-hash>
git push origin main

# 2. Revert frontend code
git revert <commit-hash>
git push origin main

# 3. Revert Supabase config (manual)
# - Disable email confirmations
# - Revert to default email templates
```

- [ ] Rollback procedure documented
- [ ] Team notified of deployment
- [ ] Backup of previous version available

## Support Preparation

### Documentation
- [ ] Update user documentation
- [ ] Add FAQ about email verification
- [ ] Create support ticket templates
- [ ] Train support team on new flow

### Common Issues & Responses

**Issue:** "I didn't receive the email"
**Response:** 
1. Check spam/junk folder
2. Use "Resend Email" button
3. Verify email address is correct
4. Wait a few minutes and try again

**Issue:** "The verification link doesn't work"
**Response:**
1. Link expires after 1 hour
2. Use "Resend Email" to get new link
3. Make sure you're clicking the latest email
4. Copy/paste link if button doesn't work

**Issue:** "Banner won't go away"
**Response:**
1. Click the verification link in your email
2. Wait up to 30 seconds for banner to disappear
3. Refresh the page
4. If still showing, contact support

## Security Checklist

### Authentication Security
- [ ] JWT_SECRET_KEY is strong and unique
- [ ] HTTPS enforced on all endpoints
- [ ] Rate limiting active
- [ ] CORS properly configured
- [ ] No sensitive data in error messages

### Email Security
- [ ] Email links expire after 1 hour
- [ ] Links are one-time use
- [ ] No sensitive data in email content
- [ ] SPF/DKIM configured (if custom domain)

## Performance

### Optimization
- [ ] Email templates are optimized (< 100KB)
- [ ] Banner component is lazy-loaded (if applicable)
- [ ] API endpoints cached appropriately
- [ ] Images optimized for email

### Load Testing
- [ ] Test with multiple simultaneous signups
- [ ] Verify email queue doesn't back up
- [ ] Check database query performance
- [ ] Monitor API response times

## Legal & Compliance

### Regulations
- [ ] Privacy policy updated (mentions email verification)
- [ ] Terms of service updated (if needed)
- [ ] GDPR compliance (if applicable)
- [ ] CAN-SPAM compliance (US)
- [ ] Email opt-out link (if required)

## Final Checks

### Before Going Live
- [ ] All above sections completed
- [ ] Team notified of deployment time
- [ ] Maintenance window scheduled (if needed)
- [ ] Support team ready
- [ ] Monitoring dashboards open

### After Going Live
- [ ] Monitor error rates for 1 hour
- [ ] Check user signup flow
- [ ] Verify emails are being sent
- [ ] Review logs for issues
- [ ] Test a real signup yourself

## Success Criteria

### Metrics to Achieve
- [ ] Email delivery rate > 95%
- [ ] Email verification rate > 70% (first 24 hours)
- [ ] Banner dismissal rate < 30%
- [ ] Zero critical errors
- [ ] User feedback is positive

## Contacts & Resources

### Key Personnel
- **Developer:** [Your Name]
- **DevOps:** [Team Contact]
- **Support Lead:** [Support Contact]
- **Product Manager:** [PM Contact]

### Important Links
- **Supabase Dashboard:** https://app.supabase.com
- **Production API:** https://api.yourdomain.com
- **Production Frontend:** https://yourdomain.com
- **Error Monitoring:** [Your monitoring tool URL]

### Documentation
- Implementation Details: `backend/docs/EMAIL_VERIFICATION_IMPROVEMENTS.md`
- Quick Start Guide: `backend/docs/EMAIL_VERIFICATION_QUICK_START.md`
- Visual Guide: `backend/docs/EMAIL_VERIFICATION_VISUAL_GUIDE.md`

---

## Sign-Off

**Deployed By:** ________________  
**Date:** ________________  
**Time:** ________________  
**Verified By:** ________________  

**Notes:**
_______________________________________________________
_______________________________________________________
_______________________________________________________
