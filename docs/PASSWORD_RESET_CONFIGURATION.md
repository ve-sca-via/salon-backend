# Password Reset Configuration Guide

## Problem
Password reset emails redirect users to incorrect URLs:
- **Local Development**: Redirecting to `127.0.0.1:3000` instead of `localhost:3000`
- **Production**: Not redirecting to correct production domain `www.lubist.com`

## Root Causes

### 1. Local Development Issue
The local Supabase configuration was using `127.0.0.1` instead of `localhost`, which browsers treat as different origins.

### 2. Production Issue
The production environment variables weren't correctly configured for your deployed domain.

---

## Solutions

### Local Development Setup

#### 1. Supabase Configuration (Already Fixed)
The `supabase/config.toml` file has been updated to use `localhost`:

```toml
[auth]
site_url = "http://localhost:3000"
additional_redirect_urls = ["http://localhost:3000", "https://www.lubist.com"]
```

#### 2. Backend Environment Variables
Create/update your `.env` file with:

```env
# Local Development
FRONTEND_URL="http://localhost:3000"
ADMIN_PANEL_URL="http://localhost:5174"
VENDOR_PORTAL_URL="http://localhost:3000/vendor"
RM_PORTAL_URL="http://localhost:3000/rm"
```

#### 3. Restart Supabase
After changing `config.toml`, restart your local Supabase:

```bash
# Stop Supabase
supabase stop

# Start Supabase
supabase start
```

---

### Production Deployment Setup

#### 1. Backend Environment Variables (Render/Your Hosting)
Set these environment variables in your production backend hosting (e.g., Render):

```env
ENVIRONMENT="production"
FRONTEND_URL="https://www.lubist.com"
ADMIN_PANEL_URL="https://admin.lubist.com"  # or your admin panel URL
VENDOR_PORTAL_URL="https://www.lubist.com/vendor"
RM_PORTAL_URL="https://www.lubist.com/rm"
```

**Important**: Make sure to use:
- `https://` (not `http://`)
- The exact domain without trailing slashes
- `www.lubist.com` if that's your primary domain (or `lubist.com` if you prefer without www)

#### 2. Supabase Dashboard Configuration

**Critical Step**: You must also configure your production Supabase project:

1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Select your project
3. Navigate to **Authentication** → **URL Configuration**
4. Set the following:

   - **Site URL**: `https://www.lubist.com`
   - **Redirect URLs**: Add these URLs (one per line):
     ```
     https://www.lubist.com
     https://www.lubist.com/reset-password
     https://www.lubist.com/vendor
     https://www.lubist.com/rm
     https://www.lubist.com/admin
     ```

5. Click **Save**

#### 3. Frontend Configuration (Vercel)

Make sure your frontend environment variables in Vercel are set correctly:

```env
VITE_API_BASE_URL="https://your-backend-api.onrender.com/api/v1"  # Your backend URL
VITE_SUPABASE_URL="https://your-project.supabase.co"
VITE_SUPABASE_ANON_KEY="your-anon-key"
```

---

## How Password Reset Works

### Flow Diagram
```
1. User requests password reset
   ↓
2. Backend calls Supabase auth.reset_password_for_email()
   with redirect_to = "https://www.lubist.com/reset-password"
   ↓
3. Supabase sends email with reset link
   ↓
4. User clicks link → Redirected to:
   https://www.lubist.com/reset-password#access_token=...&type=recovery
   ↓
5. Frontend extracts token from URL hash
   ↓
6. User enters new password
   ↓
7. Frontend sends token + new password to backend
   ↓
8. Backend confirms reset and returns new tokens
   ↓
9. User is logged in automatically
```

### Code Implementation

**Backend** ([auth_service.py](g:/vescavia/Projects/backend/app/services/auth_service.py#L612)):
```python
reset_options = {"redirect_to": f"{settings.FRONTEND_URL}/reset-password"}
self.auth_client.auth.reset_password_for_email(email, reset_options)
```

**Frontend** ([App.jsx](g:/vescavia/Projects/salon-management-app/src/App.jsx#L110)):
```jsx
// Handle password reset redirect from email
useEffect(() => {
  const hash = window.location.hash;
  if (hash && hash.includes('type=recovery')) {
    const resetPasswordUrl = `/reset-password${hash}`;
    window.location.replace(resetPasswordUrl);
  }
}, []);
```

---

## Testing

### Local Development Test
1. Start your local backend and frontend
2. Navigate to `/forgot-password`
3. Enter your email
4. Check the Supabase Inbucket at `http://localhost:54324`
5. Click the password reset link
6. Verify it redirects to `http://localhost:3000/reset-password#...`

### Production Test
1. Deploy backend with correct `FRONTEND_URL`
2. Configure Supabase dashboard redirect URLs
3. Navigate to `https://www.lubist.com/forgot-password`
4. Enter your email
5. Check your actual email inbox
6. Click the password reset link
7. Verify it redirects to `https://www.lubist.com/reset-password#...`

---

## Troubleshooting

### Issue: Still redirecting to 127.0.0.1
**Solution**: 
- Restart Supabase local instance: `supabase stop && supabase start`
- Clear browser cache and cookies

### Issue: Production redirect not working
**Solution**:
- Verify `FRONTEND_URL` is set correctly in backend environment variables
- Check Supabase dashboard → Authentication → URL Configuration
- Ensure redirect URLs are added to Supabase allowed list
- Verify domain uses `https://` not `http://`

### Issue: "Invalid redirect URL" error
**Solution**:
- Add the exact redirect URL to Supabase dashboard allowed list
- Include both with and without trailing slashes if needed
- Check for typos in domain name

### Issue: Email sent but link doesn't work
**Solution**:
- Check if token has expired (default: 1 hour)
- Verify backend and frontend are using same Supabase project
- Check browser console for errors

---

## Environment Variables Checklist

### Local Development (.env)
- [ ] `FRONTEND_URL="http://localhost:3000"`
- [ ] `SUPABASE_URL="http://127.0.0.1:54321"`
- [ ] Supabase config.toml updated with `localhost`

### Production (Render/Hosting Platform)
- [ ] `ENVIRONMENT="production"`
- [ ] `FRONTEND_URL="https://www.lubist.com"`
- [ ] `SUPABASE_URL="https://your-project.supabase.co"`
- [ ] Supabase dashboard redirect URLs configured

### Supabase Dashboard (Production)
- [ ] Site URL set to production domain
- [ ] All redirect URLs added to allowed list
- [ ] Email templates use correct domain (if customized)

---

## Additional Notes

### Domain Considerations
- If you want to support both `lubist.com` and `www.lubist.com`:
  1. Choose one as primary (recommend `www.lubist.com`)
  2. Set up 301 redirect from other to primary
  3. Use primary in all environment variables
  4. Add both to Supabase redirect URLs

### Subdomain Redirects (Recommended for Multi-Portal Apps)

You can use subdomains that redirect to your main domain paths. This provides cleaner URLs for different user types:

**Subdomain Structure:**
- `rm.lubist.com` → redirects to `https://www.lubist.com/rm-login`
- `vendor.lubist.com` → redirects to `https://www.lubist.com/vendor-login`
- `admin.lubist.com` → redirects to your admin panel

**How Password Reset Works with Subdomains:**
1. User visits `rm.lubist.com` (redirects to `www.lubist.com/rm-login`)
2. Clicks "Forgot Password" 
3. Password reset email sent with link to: `https://www.lubist.com/reset-password#token=...`
4. After reset, user is redirected to appropriate dashboard based on their role

**Setup Instructions:**

#### Option 1: Vercel Redirects (Recommended)
If your frontend is hosted on Vercel, add to `vercel.json`:

```json
{
  "redirects": [
    {
      "source": "https://rm.lubist.com/:path*",
      "destination": "https://www.lubist.com/rm-login/:path*",
      "permanent": false
    },
    {
      "source": "https://vendor.lubist.com/:path*",
      "destination": "https://www.lubist.com/vendor-login/:path*",
      "permanent": false
    }
  ]
}
```

#### Option 2: DNS CNAME + Path Redirects
1. **Add DNS CNAME Records** (in your DNS provider):
   ```
   rm.lubist.com      CNAME   cname.vercel-dns.com.
   vendor.lubist.com  CNAME   cname.vercel-dns.com.
   ```

2. **Configure in Vercel Dashboard**:
   - Go to Project → Settings → Domains
   - Add `rm.lubist.com` and `vendor.lubist.com`
   - They'll point to same project

3. **Add Redirect Rules in `vercel.json`**:
   ```json
   {
     "redirects": [
       {
         "source": "https://rm.lubist.com",
         "destination": "https://www.lubist.com/rm-login",
         "permanent": false
       },
       {
         "source": "https://vendor.lubist.com",
         "destination": "https://www.lubist.com/vendor-login",
         "permanent": false
       }
     ]
   }
   ```

#### Option 3: Nginx/Apache Redirects (If Self-Hosting)
```nginx
# Nginx configuration
server {
    listen 443 ssl;
    server_name rm.lubist.com;
    return 302 https://www.lubist.com/rm-login$request_uri;
}

server {
    listen 443 ssl;
    server_name vendor.lubist.com;
    return 302 https://www.lubist.com/vendor-login$request_uri;
}
```

**Important Supabase Configuration:**
Add ALL possible redirect URLs to Supabase dashboard:
```
https://www.lubist.com
https://www.lubist.com/reset-password
https://rm.lubist.com
https://rm.lubist.com/reset-password
https://vendor.lubist.com
https://vendor.lubist.com/reset-password
```

**Backend Environment Variables Remain Same:**
```env
FRONTEND_URL="https://www.lubist.com"
VENDOR_PORTAL_URL="https://www.lubist.com/vendor"
RM_PORTAL_URL="https://www.lubist.com/rm"
```

Password reset will always redirect to `www.lubist.com/reset-password`, and your app logic will redirect users to the appropriate portal after successful reset based on their role.

### Multiple Environments
If you have staging environment:
```env
# Staging
FRONTEND_URL="https://staging.lubist.com"
```

And add staging URLs to Supabase:
- Site URL: `https://staging.lubist.com`
- Redirect URLs: Include staging URLs

---

## Related Files
- Backend configuration: [app/core/config.py](../app/core/config.py)
- Auth service: [app/services/auth_service.py](../app/services/auth_service.py)
- Supabase config: [supabase/config.toml](../supabase/config.toml)
- Frontend reset page: `salon-management-app/src/pages/auth/ResetPassword.jsx`
- Frontend App.jsx: `salon-management-app/src/App.jsx`
