# Email Verification Setup - Quick Start Guide

## 🎯 What's Been Fixed

### Problem 1: Users Don't Know They Need to Verify Email
**Solution:** Orange banner now appears at the top of the page after signup with clear instructions.

### Problem 2: Generic Email Templates
**Solution:** Branded Lubist email templates with your company colors and messaging.

## 🚀 Quick Test (Local Development)

### 1. Start Supabase (if using local instance)
```bash
cd backend
supabase start
```

### 2. Start Backend Server
```bash
cd backend
# Activate virtual environment first
.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate    # Mac/Linux

# Run server
python main.py
```

### 3. Start Frontend
```bash
cd salon-management-app
npm run dev
```

### 4. Test the Flow

1. **Sign Up:**
   - Go to http://localhost:3000/signup
   - Fill in the form with a real email you can access
   - Click "Sign Up"

2. **See the Banner:**
   - After signup, you'll be redirected to the home page
   - You should see an **orange banner at the top** saying:
     > 📧 Please verify your email address
   - The banner shows your email and has a "Resend Email" button

3. **Check Your Email:**
   - Open your email inbox
   - Look for email from Supabase
   - You should see a **branded Lubist email** (not the generic one)
   - Email should have:
     - Lubist logo/branding
     - Orange gradient header
     - Clear "Confirm Your Email" button
     - List of Lubist features

4. **Verify Email:**
   - Click the "Confirm Your Email" button in the email
   - You'll be redirected back to the app
   - The banner should disappear within 30 seconds

5. **Test Resend:**
   - If you dismiss the banner or don't receive the email:
   - Click "Resend Email" button in the banner
   - You should see a success toast
   - Check your inbox for the new email

## 🔧 Configuration

### Local Supabase (Already Configured)
The local Supabase config has been updated with:
- Email confirmations enabled
- Custom branded email templates
- Redirect URLs set to localhost:3000

### Production Supabase (Action Required)

When deploying to production, you need to:

1. **Upload Email Templates:**
   ```
   Login to Supabase Dashboard
   → Authentication
   → Email Templates
   → Upload templates from backend/supabase/templates/
   ```

2. **Enable Email Confirmation:**
   ```
   Supabase Dashboard
   → Authentication
   → Providers
   → Email
   → Enable "Confirm email"
   ```

3. **Set Redirect URLs:**
   ```
   Supabase Dashboard
   → Authentication
   → URL Configuration
   → Add your production URL (e.g., https://yourdomain.com)
   ```

4. **Update Environment Variables:**
   ```env
   FRONTEND_URL=https://yourdomain.com
   ```

## 📱 What Users Will See

### 1. Banner Appearance
```
┌─────────────────────────────────────────────────────────────┐
│ 📧 Please verify your email address          [Resend Email] [X] │
│ We've sent a confirmation email to user@example.com.       │
│ Please check your inbox and click the verification link.   │
└─────────────────────────────────────────────────────────────┘
```
- **Color:** Orange gradient (matches your brand)
- **Position:** Top of page, above navbar
- **Dismissible:** Yes (with X button)
- **Persistent:** Shows on all pages until dismissed or verified

### 2. Email Content
- **Subject:** "Welcome to Lubist - Confirm Your Email 🎉"
- **Branding:** Lubist logo and orange gradient header
- **Content:**
  - Welcome message
  - Clear "Confirm Your Email" button
  - Benefits list (bookings, favorites, reviews, etc.)
  - Alternative text link if button doesn't work
  - Contact information

## 🐛 Troubleshooting

### Banner Doesn't Appear
**Cause:** Session storage flag not set
**Fix:** Check browser console for errors, verify Signup.jsx was updated

### Email Not Received
**Cause:** Email service not configured or spam folder
**Fix:** 
- Check spam/junk folder
- For local Supabase, check `supabase` container logs
- For production, check Supabase dashboard logs

### Email Looks Generic/Unbranded
**Cause:** Custom templates not loaded
**Fix:** 
- For local: Restart Supabase (`supabase stop` then `supabase start`)
- For production: Upload templates in Supabase dashboard

### Resend Button Doesn't Work
**Cause:** Backend endpoint not accessible
**Fix:**
- Check backend is running on correct port
- Check browser network tab for errors
- Verify API_BASE_URL in frontend .env

## 📝 Files Modified

### Frontend
- ✅ `src/components/shared/EmailVerificationBanner.jsx` (new)
- ✅ `src/App.jsx` (modified)
- ✅ `src/pages/auth/Signup.jsx` (modified)

### Backend
- ✅ `app/api/auth.py` (modified)
- ✅ `app/services/auth_service.py` (modified)
- ✅ `supabase/config.toml` (modified)
- ✅ `supabase/templates/confirmation.html` (new)
- ✅ `supabase/templates/magic_link.html` (new)

## 💡 Tips

1. **Test with Real Email:** Use a real email address you can access to test the full flow

2. **Check Multiple Email Clients:** Test how the email looks in:
   - Gmail
   - Outlook
   - Apple Mail
   - Mobile email apps

3. **Rate Limiting:** The resend button is rate-limited to 3 times per hour to prevent abuse

4. **Session Storage:** The banner state is stored in session storage, so it persists across page refreshes but resets when the browser/tab is closed

5. **Auto-Hide:** The banner automatically checks every 30 seconds if the email has been confirmed and hides itself

## 🎨 Customization

### Change Banner Colors
Edit `src/components/shared/EmailVerificationBanner.jsx`:
```jsx
className="bg-gradient-to-r from-accent-orange to-yellow-500"
// Change to your preferred gradient
```

### Change Email Template
Edit `backend/supabase/templates/confirmation.html`:
- Modify colors in the `<style>` section
- Update text content
- Change logo/branding

### Change Email Subject
Edit `backend/supabase/config.toml`:
```toml
[auth.email.template.confirmation]
subject = "Your Custom Subject Here"
```

## ✅ Deployment Checklist

Before deploying to production:

- [ ] Upload email templates to Supabase dashboard
- [ ] Enable email confirmation in Supabase settings
- [ ] Set production redirect URLs
- [ ] Update FRONTEND_URL environment variable
- [ ] Test signup flow in production
- [ ] Test email delivery
- [ ] Test resend functionality
- [ ] Verify banner appears and disappears correctly
- [ ] Check email rendering in different clients

## 📚 Additional Resources

- [Supabase Email Templates Docs](https://supabase.com/docs/guides/auth/auth-email-templates)
- [Supabase Auth Configuration](https://supabase.com/docs/guides/auth)
- Full implementation details: `backend/docs/EMAIL_VERIFICATION_IMPROVEMENTS.md`
