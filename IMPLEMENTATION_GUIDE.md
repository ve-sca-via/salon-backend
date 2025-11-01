# 🚀 Implementation Guide - Phase by Phase

## Overview
This guide walks you through implementing the complete restructuring of your Salon Management & Hiring Platform.

---

## 📋 Phase 1: Database Setup (CURRENT PHASE)

### Step 1.1: Run the Migration

```powershell
# Navigate to frontend project
cd G:\vescavia\Projects\salon-management-app

# Make sure Supabase is running
# If using local Supabase:
supabase start

# Run the migration
supabase db push

# OR if using remote Supabase:
supabase db push --db-url "your-connection-string"
```

### Step 1.2: Verify Migration

```sql
-- Connect to Supabase SQL Editor and verify tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Should see these tables:
-- bookings, booking_payments, profiles, rm_profiles, rm_score_history
-- salons, salon_staff, staff_availability, services, service_categories
-- system_config, vendor_join_requests, vendor_payments, reviews
```

### Step 1.3: Create Default Admin Account

```sql
-- In Supabase SQL Editor or through Supabase Auth Dashboard
-- 1. Create user through Supabase Auth Dashboard
-- 2. Then add profile:

INSERT INTO public.profiles (id, email, full_name, role, is_active, email_verified)
VALUES (
    'auth-user-id-from-step-1',
    'admin@yourplatform.com',
    'System Administrator',
    'admin',
    true,
    true
);
```

---

## 📦 Phase 2: Backend Setup

### Step 2.1: Install Dependencies

```powershell
cd G:\vescavia\Projects\backend

# Create virtual environment if not exists
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Step 2.2: Configure Environment

```powershell
# Copy example env file
Copy-Item .env.example .env

# Edit .env with your actual values
notepad .env
```

**Required Configuration:**
```env
# Get these from Supabase Dashboard -> Settings -> API
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres

# Generate a secure JWT secret
JWT_SECRET_KEY=your-super-secret-key-min-32-chars

# Razorpay (sign up at https://razorpay.com)
RAZORPAY_KEY_ID=rzp_test_xxx
RAZORPAY_KEY_SECRET=xxx
RAZORPAY_WEBHOOK_SECRET=xxx

# SMTP for emails (use Gmail for testing)
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password  # Generate from Google Account

# Frontend URLs
FRONTEND_URL=http://localhost:5173
ADMIN_PANEL_URL=http://localhost:5174
```

### Step 2.3: Test Backend

```powershell
# Run the backend
python main.py

# Or using uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit: http://localhost:8000/docs to see API documentation

---

## 🎨 Phase 3: Admin Panel Migration

### Step 3.1: Update Admin Panel Environment

```powershell
cd G:\vescavia\Projects\salon-admin-panel

# Create/update .env.local
echo "VITE_API_URL=http://localhost:8000/api/v1" > .env.local
echo "VITE_SUPABASE_URL=https://your-project.supabase.co" >> .env.local
echo "VITE_SUPABASE_ANON_KEY=your-anon-key" >> .env.local
```

### Step 3.2: Install Dependencies

```powershell
# Install/update dependencies
npm install

# Add new dependencies for admin features
npm install @tanstack/react-query axios react-toastify lucide-react
```

### Step 3.3: Test Admin Panel

```powershell
npm run dev
```

Visit: http://localhost:5174

---

## 🌐 Phase 4: Main Frontend Setup

### Step 4.1: Update Environment

```powershell
cd G:\vescavia\Projects\salon-management-app

# Update .env.local
echo "VITE_API_URL=http://localhost:8000/api/v1" > .env.local
echo "VITE_SUPABASE_URL=https://your-project.supabase.co" >> .env.local
echo "VITE_SUPABASE_ANON_KEY=your-anon-key" >> .env.local
echo "VITE_RAZORPAY_KEY_ID=rzp_test_xxx" >> .env.local
```

### Step 4.2: Install Dependencies

```powershell
npm install

# Add required packages
npm install @tanstack/react-query axios razorpay react-toastify
```

### Step 4.3: Test Frontend

```powershell
npm run dev
```

Visit: http://localhost:5173

---

## 🔐 Phase 5: Role-Based Access Setup

### Step 5.1: Create Test Users

Execute in Supabase SQL Editor:

```sql
-- 1. Create RM (Relationship Manager)
-- First create auth user through Supabase Dashboard, then:
INSERT INTO public.profiles (id, email, full_name, role, is_active, email_verified)
VALUES ('rm-user-id', 'rm@test.com', 'Test RM', 'relationship_manager', true, true);

INSERT INTO public.rm_profiles (id, employee_id, joining_date)
VALUES ('rm-user-id', 'RM001', CURRENT_DATE);

-- 2. Create Vendor (after approval process normally)
-- First create auth user, then:
INSERT INTO public.profiles (id, email, full_name, role, is_active, email_verified)
VALUES ('vendor-user-id', 'vendor@test.com', 'Test Vendor', 'vendor', true, true);

-- 3. Create Customer
-- First create auth user, then:
INSERT INTO public.profiles (id, email, full_name, role, is_active, email_verified)
VALUES ('customer-user-id', 'customer@test.com', 'Test Customer', 'customer', true, true);
```

---

## 💰 Phase 6: Payment Integration Testing

### Step 6.1: Razorpay Test Mode Setup

1. Sign up at https://razorpay.com
2. Go to Dashboard -> Settings -> API Keys
3. Use **Test Mode** keys for development
4. Add webhook URL in Dashboard -> Settings -> Webhooks
   - URL: `http://your-backend-url/api/v1/payments/webhook`
   - Events: payment.captured, payment.failed, refund.created

### Step 6.2: Test Payment Flow

**Test Card Details** (Razorpay Test Mode):
- Card Number: `4111 1111 1111 1111`
- CVV: Any 3 digits
- Expiry: Any future date
- OTP: `1234`

### Step 6.3: Test Scenarios

1. **Vendor Registration Fee**:
   - RM creates join request
   - Admin approves
   - Vendor receives email with registration link
   - Vendor pays registration fee
   - Test with Razorpay test card

2. **Customer Booking**:
   - Customer browses salons
   - Selects service
   - Pays convenience fee
   - Booking confirmed

---

## 📧 Phase 7: Email Setup

### Step 7.1: Gmail App Password (for testing)

1. Go to Google Account -> Security
2. Enable 2-Factor Authentication
3. Go to "App Passwords"
4. Generate password for "Mail"
5. Use this in `SMTP_PASSWORD` in `.env`

### Step 7.2: Test Email Templates

The system will send emails for:
- Vendor registration link (after approval)
- Booking confirmation
- Booking cancellation
- Payment receipts

---

## 🧪 Phase 8: Testing Checklist

### Backend API Testing

```powershell
# Test health endpoint
curl http://localhost:8000/health

# Test auth
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"password123"}'
```

### Database Testing

```sql
-- Test RLS policies
-- Login as different users and verify they can only access their data

-- Test triggers
-- Create a review and verify salon rating updates

-- Test functions
-- Verify booking number generation
```

### Frontend Testing

1. **Admin Panel**: 
   - ✅ Login as admin
   - ✅ View pending vendor requests
   - ✅ Approve/reject requests
   - ✅ Manage system config
   - ✅ View all salons

2. **RM Portal**:
   - ✅ Login as RM
   - ✅ Add salon/spa details
   - ✅ Submit join request
   - ✅ View own score

3. **Vendor Portal**:
   - ✅ Receive registration email
   - ✅ Complete registration
   - ✅ Pay registration fee
   - ✅ Add services
   - ✅ Add staff
   - ✅ View bookings

4. **Customer App**:
   - ✅ Register/Login
   - ✅ Search nearby salons
   - ✅ View services
   - ✅ Book appointment
   - ✅ Pay convenience fee
   - ✅ View booking history
   - ✅ Cancel booking
   - ✅ Leave review

---

## 🐛 Common Issues & Solutions

### Issue 1: Migration Fails

```sql
-- Check for existing tables
DROP TABLE IF EXISTS public.bookings CASCADE;
-- Repeat for all tables, then run migration again
```

### Issue 2: RLS Policies Block Access

```sql
-- Temporarily disable RLS for testing (DEV ONLY)
ALTER TABLE public.salons DISABLE ROW LEVEL SECURITY;

-- Re-enable after testing
ALTER TABLE public.salons ENABLE ROW LEVEL SECURITY;
```

### Issue 3: CORS Errors

```python
# In backend main.py, verify CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Issue 4: Payment Test Fails

- Verify Razorpay test keys are used
- Check webhook URL is accessible (use ngrok for local testing)
- Verify webhook signature validation

---

## 📊 Monitoring & Logs

### Backend Logs

```powershell
# View logs
tail -f logs/app.log

# Or on Windows
Get-Content logs/app.log -Wait
```

### Database Logs

```sql
-- Check recent activities
SELECT * FROM public.vendor_join_requests ORDER BY created_at DESC LIMIT 10;
SELECT * FROM public.bookings ORDER BY created_at DESC LIMIT 10;
SELECT * FROM public.vendor_payments ORDER BY created_at DESC LIMIT 10;
```

---

## 🚀 Deployment Checklist

### Before Production:

1. ✅ Change all default passwords
2. ✅ Use production Razorpay keys
3. ✅ Configure production SMTP
4. ✅ Set secure JWT_SECRET_KEY (min 32 chars)
5. ✅ Enable HTTPS
6. ✅ Configure proper CORS origins
7. ✅ Set up error tracking (Sentry)
8. ✅ Configure backup strategy
9. ✅ Set up monitoring
10. ✅ Test all email flows
11. ✅ Test all payment flows
12. ✅ Load testing

### Production Environment Variables:

```env
ENVIRONMENT=production
DEBUG=False
ALLOWED_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com
RAZORPAY_KEY_ID=rzp_live_xxx
# ... all production values
```

---

## 📚 Next Steps

After completing all phases:

1. **Performance Optimization**
   - Add Redis caching
   - Optimize database queries
   - Add CDN for static assets

2. **Advanced Features**
   - SMS notifications (Twilio)
   - Push notifications
   - Advanced analytics
   - Loyalty programs

3. **Security Hardening**
   - Rate limiting
   - API key authentication for admin
   - Regular security audits
   - Penetration testing

---

## 🆘 Getting Help

If you encounter issues:

1. Check logs first (`logs/app.log`)
2. Verify environment variables
3. Check Supabase dashboard for database issues
4. Review Razorpay dashboard for payment issues
5. Test with Postman/curl for API debugging

---

## 📞 Support Contacts

- **Manager**: [Your manager's contact]
- **Razorpay Support**: https://razorpay.com/support
- **Supabase Support**: https://supabase.com/support

---

**Last Updated**: October 31, 2025
**Version**: 2.0.0
**Status**: Phase 1 Complete - Database Migration Ready
