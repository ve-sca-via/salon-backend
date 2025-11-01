# 🚀 QUICK START - Restructured Project

## ⚡ 5-Minute Setup

### Step 1: Database Migration
```powershell
cd G:\vescavia\Projects\salon-management-app
supabase db push
```
Creates 14 tables with RLS, triggers, and relationships.

### Step 2: Backend Dependencies
```powershell
cd G:\vescavia\Projects\backend
pip install -r requirements.txt
```

### Step 3: Configure
```powershell
Copy-Item .env.example .env
notepad .env  # Fill in Supabase & Razorpay credentials
```

### Step 4: Run
```powershell
python main.py
```
Visit: http://localhost:8000/docs

---

## 📝 What Was Created

### ✅ Database Schema (`salon-management-app/supabase/migrations/`)
- 14 tables with relationships
- 4 roles: admin, relationship_manager, vendor, customer
- RLS policies for security
- Automated triggers
- Default configurations

### ✅ Backend Updates
- **`app/core/config.py`** - All settings
- **`app/schemas/__init__.py`** - Pydantic models
- **`app/services/payment.py`** - Razorpay integration
- **`requirements.txt`** - All dependencies
- **`.env.example`** - Environment template

### ✅ Documentation
- **`IMPLEMENTATION_GUIDE.md`** - Detailed steps
- **`PROJECT_SUMMARY.md`** - Architecture overview
- **`QUICK_START_NEW.md`** - This file

---

## 🎯 Key Answers

| Question | Answer |
|----------|--------|
| Registration fee? | ✅ Dynamic (admin sets in `system_config`) |
| Convenience fee? | ✅ Dynamic percentage (admin sets) |
| RM scoring? | ✅ Dynamic points (admin sets) |
| Payment gateway? | ✅ Razorpay |
| Free services? | ✅ Yes (price = 0) |
| Staff limit? | ✅ Unlimited |
| RM = Vendor? | ❌ No, separate roles |

---

## 🏗️ Architecture

```
Admin Panel (5174) → Backend API (8000) → Supabase DB
                          ↓
            Complex: Payments, Approvals, Emails
            Simple: Direct Supabase CRUD + RLS
                          ↓
                    Frontend (5173)
```

---

## 📊 4 Roles Explained

**Admin**
- Approves vendor requests
- Sets all fees & scores dynamically
- System-wide control

**Relationship Manager (RM)**
- Adds salon details
- Gets points per approval
- Can NOT be vendor

**Vendor**
- Created via email after approval
- Pays registration fee
- Manages own salon
- Unlimited staff

**Customer**
- Books services
- Pays convenience fee
- Leaves reviews

---

## 🔑 Environment Setup

**Get from Supabase Dashboard → Settings → API:**
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJxxx
SUPABASE_SERVICE_ROLE_KEY=eyJxxx
DATABASE_URL=postgresql://postgres:xxx@db.xxx.supabase.co:5432/postgres
```

**Get from Razorpay Dashboard (use test keys):**
```env
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx
```

**Generate JWT Secret:**
```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Gmail App Password** (for emails):
1. Google Account → Security → 2FA → App Passwords
2. Generate for "Mail"
```env
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=generated-app-password
```

---

## 🧪 Test Payment

**Razorpay Test Cards:**
- Success: `4111 1111 1111 1111`, CVV: `123`, OTP: `1234`
- UPI: `success@razorpay`

---

## 📁 Tables Created (14)

1. **profiles** - All users (4 roles)
2. **system_config** - Admin settings ⚙️
3. **rm_profiles** - RM data & scores
4. **rm_score_history** - Score tracking
5. **vendor_join_requests** - Approval workflow
6. **salons** - Business entities
7. **services** - Service offerings
8. **service_categories** - Categories
9. **salon_staff** - Staff members
10. **staff_availability** - Scheduling
11. **bookings** - Customer bookings
12. **booking_payments** - Payment tracking
13. **vendor_payments** - Registration fees
14. **reviews** - Ratings & feedback

---

## 🎬 Next Steps

1. ✅ Run migration (Step 1 above)
2. ✅ Configure environment
3. ⬜ Create API endpoints (admin, rm, vendor, payments)
4. ⬜ Update admin panel to use APIs
5. ⬜ Build RM portal
6. ⬜ Add payment flows to customer app
7. ⬜ Test everything

---

## 📚 Full Docs

- **Implementation**: `IMPLEMENTATION_GUIDE.md`
- **Architecture**: `PROJECT_SUMMARY.md`
- **API**: http://localhost:8000/docs

---

**Status**: ✅ Phase 1 Complete
**Version**: 2.0.0
**Date**: Oct 31, 2025

Go to `IMPLEMENTATION_GUIDE.md` for detailed steps! 🚀
