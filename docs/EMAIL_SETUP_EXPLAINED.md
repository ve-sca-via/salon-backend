# 📧 Email Setup - BRUTAL TRUTH & How It Works

## 🔴 THE BRUTAL TRUTH - What Was Broken

### **Problem 1: The Missing Flag**
- ❌ Your `.env` file was **MISSING** `EMAIL_ENABLED=True`
- ❌ So it defaulted to `EMAIL_ENABLED=False` (from `app/core/config.py` line 61)
- ❌ Result: **ALL EMAILS WERE BEING CONSOLE LOGGED ONLY**
- ❌ Nothing was being sent to Mailpit even though it was running

### **Problem 2: Wrong Port**
- ❌ You had `SMTP_PORT=54324` (that's the **web UI** port)
- ❌ The **SMTP** port was not exposed at all
- ❌ Even if `EMAIL_ENABLED=True`, emails would have failed

### **Problem 3: SMTP Login for Mailpit**
- ❌ The code tried to login with `SMTP_USER` and `SMTP_PASSWORD`
- ❌ Mailpit doesn't need authentication
- ❌ This would have caused errors

---

## ✅ WHAT'S FIXED NOW

### **1. The Master Switch**
```bash
# In .env and .env.local
EMAIL_ENABLED=True  # ← THIS is the flag you were looking for!
```

**How it works:**
- `EMAIL_ENABLED=False` → Emails are **logged to console** only (dev mode)
- `EMAIL_ENABLED=True` → Emails are **sent via SMTP** (local Mailpit or production)

### **2. Correct SMTP Configuration**
```bash
# Mailpit Local Email Testing
EMAIL_ENABLED=True
SMTP_HOST=127.0.0.1
SMTP_PORT=54325          # ← SMTP port (NOT the web UI port!)
SMTP_USER=               # ← Empty for Mailpit (no auth needed)
SMTP_PASSWORD=           # ← Empty for Mailpit
SMTP_TLS=False           # ← Mailpit doesn't use TLS
SMTP_SSL=False           # ← Mailpit doesn't use SSL
EMAIL_FROM=noreply@localhost
EMAIL_FROM_NAME=Salon Platform (Local Dev)
```

### **3. Fixed Email Service Code**
In `app/services/email.py` line 173:
```python
# Only login if credentials are provided (Mailpit doesn't need auth)
if settings.SMTP_USER and settings.SMTP_PASSWORD:
    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
```

### **4. Enabled SMTP Port in Supabase**
In `supabase/config.toml`:
```toml
[inbucket]
enabled = true
port = 54324        # Web UI
smtp_port = 54325   # SMTP server (NOW ENABLED!)
```

---

## 🎯 HOW IT WORKS NOW

### **Email Flow**
```
Your FastAPI Code
    ↓
Calls: email_service.send_booking_confirmation_email(...)
    ↓
Checks: EMAIL_ENABLED=True ✅
    ↓
Connects to: 127.0.0.1:54325 (Mailpit SMTP)
    ↓
Mailpit receives email
    ↓
View at: http://127.0.0.1:54324 (Mailpit Web UI)
```

### **Where Emails Are Sent**

| Scenario | What Happens |
|----------|-------------|
| **Booking Created** | `booking_service.py` line 596 → `send_booking_confirmation_email()` |
| **Booking Cancelled** | `booking_service.py` line 634 → `send_booking_cancellation_email()` |
| **Vendor Approved** | `admin.py` → `send_vendor_approval_email()` |
| **Vendor Rejected** | `admin.py` → `send_vendor_rejection_email()` |
| **Payment Receipt** | `payments.py` line 185 → `send_payment_receipt_email()` |
| **Welcome Email** | `payments.py` line 203 → `send_welcome_vendor_email()` |

### **Email Templates Location**
```
app/templates/email/
├── booking_confirmation.html    ✅ Used for booking confirmations
├── booking_cancellation.html    ✅ Used for cancellations
├── vendor_approval.html          ✅ Used when RM approves salon
├── vendor_rejection.html         ✅ Used when RM rejects salon
├── payment_receipt.html          ✅ Used for payment receipts
└── welcome_vendor.html           ✅ Used for vendor welcome email
```

---

## 🧪 TESTING EMAILS LOCALLY

### **Step 1: Make Sure Supabase is Running**
```powershell
supabase status
```
You should see:
```
Mailpit URL: http://127.0.0.1:54324
```

### **Step 2: Verify Your .env**
```powershell
cat .env | Select-String "EMAIL"
```
Should show:
```
EMAIL_ENABLED=True
SMTP_HOST=127.0.0.1
SMTP_PORT=54325
EMAIL_FROM=noreply@localhost
EMAIL_FROM_NAME=Salon Platform (Local Dev)
```

### **Step 3: Start Your App**
```powershell
.\run-local.ps1
```
You should see in logs:
```
📧 Email sending: ENABLED
📧 Email Service: Using real EmailService (production mode)
```

### **Step 4: Trigger an Email**
Example: Create a booking via API
```bash
POST http://localhost:8000/api/v1/bookings
```

### **Step 5: Check Mailpit**
Open browser: **http://127.0.0.1:54324**

You'll see:
- All sent emails
- Subject, sender, recipient
- HTML preview
- Raw email source

---

## 🔄 SWITCHING BETWEEN LOCAL & PRODUCTION

### **Local Development (Mailpit)**
```powershell
.\run-local.ps1
```
This automatically sets:
- `EMAIL_ENABLED=True`
- `SMTP_HOST=127.0.0.1`
- `SMTP_PORT=54325`
- Emails go to Mailpit (http://127.0.0.1:54324)

### **Production (Real SMTP)**
In `.env.production` (you need to create this):
```bash
EMAIL_ENABLED=True
SMTP_HOST=smtp.gmail.com          # Or SendGrid, AWS SES, etc.
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_TLS=True
SMTP_SSL=False
EMAIL_FROM=noreply@yourplatform.com
EMAIL_FROM_NAME=Salon Management Platform
```

Then:
```powershell
.\run-production.ps1
```

### **Development (Console Logging Only)**
If you want to test WITHOUT sending emails:
```bash
EMAIL_ENABLED=False  # Emails only logged to console
```

---

## 🎨 CUSTOMIZING EMAIL TEMPLATES

All templates use **Jinja2** syntax and are in `app/templates/email/`.

### **Example: booking_confirmation.html**
```html
<h1>Hi {{ customer_name }}!</h1>
<p>Your booking at <strong>{{ salon_name }}</strong> is confirmed.</p>
<ul>
  <li>Service: {{ service_name }}</li>
  <li>Date: {{ booking_date }}</li>
  <li>Time: {{ booking_time }}</li>
  <li>Staff: {{ staff_name }}</li>
  <li>Total: ₹{{ total_amount }}</li>
</ul>
```

### **Variables Available**
Check each method in `app/services/email.py` to see what variables are passed to templates.

---

## 🐛 TROUBLESHOOTING

### **"Email not sent" in logs**
```
📧 DEV MODE - Email not sent to customer@test.com: Booking Confirmed
```
**Solution:** Check `EMAIL_ENABLED=True` in your `.env`

### **Connection refused to 127.0.0.1:54325**
```
Failed to send email: [Errno 111] Connection refused
```
**Solution:** 
1. Check Supabase is running: `supabase status`
2. Check SMTP port is exposed: `docker ps | Select-String "inbucket"`
3. Should see: `0.0.0.0:54325->1025/tcp`

### **SMTP authentication error**
```
SMTPAuthenticationError: Username and Password not accepted
```
**Solution:** For Mailpit, set `SMTP_USER=` and `SMTP_PASSWORD=` (empty)

### **No emails in Mailpit**
1. ✅ Check `EMAIL_ENABLED=True`
2. ✅ Check `SMTP_PORT=54325` (not 54324)
3. ✅ Check Mailpit running: http://127.0.0.1:54324
4. ✅ Check app logs for "Email sent successfully"

---

## 📋 QUICK REFERENCE

| Port | Service | URL |
|------|---------|-----|
| 54321 | Supabase API | http://127.0.0.1:54321 |
| 54322 | PostgreSQL | postgresql://postgres:postgres@127.0.0.1:54322/postgres |
| 54323 | Supabase Studio | http://127.0.0.1:54323 |
| **54324** | **Mailpit Web UI** | **http://127.0.0.1:54324** |
| **54325** | **Mailpit SMTP** | **smtp://127.0.0.1:54325** |

---

## ✅ CHECKLIST FOR TEAM MEMBERS

When setting up email locally:

- [ ] Run `supabase start`
- [ ] Verify Mailpit is running: http://127.0.0.1:54324
- [ ] Check `.env` has `EMAIL_ENABLED=True`
- [ ] Check `.env` has `SMTP_PORT=54325`
- [ ] Run `.\run-local.ps1`
- [ ] Look for "📧 Email sending: ENABLED" in logs
- [ ] Trigger a test booking
- [ ] Check Mailpit UI for the email

---

## 🎓 THE FLAG YOU FORGOT

**Location:** `app/core/config.py` line 61

```python
EMAIL_ENABLED: bool = Field(default=False)  # Toggle email sending (False = log only)
```

**This is the boolean flag you created!**

- `False` (default) = Console logging only
- `True` = Actually send via SMTP

You can control this per environment:
- `.env.local` → `EMAIL_ENABLED=True` (Mailpit)
- `.env.production` → `EMAIL_ENABLED=True` (Real SMTP)
- `.env` (dev) → `EMAIL_ENABLED=False` (Console only)

---

## 🚀 YOU'RE ALL SET!

Now when you run locally with `.\run-local.ps1`:
1. ✅ Emails will be sent to Mailpit
2. ✅ You can see them at http://127.0.0.1:54324
3. ✅ All 6 email templates will work
4. ✅ No real emails sent to customers during testing

**Open Mailpit now:** http://127.0.0.1:54324 🎉
