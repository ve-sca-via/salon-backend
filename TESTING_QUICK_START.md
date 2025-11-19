# 🧪 Quick Start Testing Guide

## Overview

You have **THREE OPTIONS** to test your backend API without manual database seeding:

---

## Option 1: 🚀 Quick Automated Seeding (Recommended)

**Use this when:** You want test data created automatically in seconds

### Steps:

1. **Start your backend server:**
   ```powershell
   cd g:\vescavia\Projects\backend
   python main.py
   ```

2. **Run the seeding script** (in a new terminal):
   ```powershell
   cd g:\vescavia\Projects\backend
   python seed_database.py
   ```

3. **What it creates:**
   - ✅ 3 user accounts (Admin, RM, Customer)
   - ✅ 5 services (Hair Cut, Styling, Facial, Manicure, Pedicure)
   - ✅ 3 salons (with different locations)

4. **Use the credentials shown** to login via Postman

**Time: ~10 seconds**

---

## Option 2: 📮 Postman Collection (Most Flexible)

**Use this when:** You want full control and manual testing

### Steps:

1. **Start your backend:**
   ```powershell
   python main.py
   ```

2. **Import Postman Collection:**
   - Open Postman
   - Import: `Salon_API_Postman_Collection.json`

3. **Follow the testing guide:**
   - Open: `API_TESTING_GUIDE.md`
   - Follow "Scenario 1: Complete Customer Journey"
   - Data is created as you test!

4. **No pre-seeding needed** - The collection creates data as you go!

**Time: ~5 minutes for first complete flow**

---

## Option 3: 🧪 Run Unit Tests

**Use this when:** You want to verify code functionality

### Steps:

```powershell
cd g:\vescavia\Projects\backend
pip install -r requirements-test.txt
pytest tests/ -v
```

Tests use **mock data** so no database seeding is required.

---

## 📁 Files Reference

| File | Purpose |
|------|---------|
| `Salon_API_Postman_Collection.json` | Complete API endpoint collection |
| `API_TESTING_GUIDE.md` | Detailed testing scenarios and workflows |
| `seed_database.py` | Automated database seeding script |
| `TESTING_QUICK_START.md` | This file - quick reference |

---

## 🎯 Recommended Testing Flow

### For First-Time Testing:

```
1. Run seed_database.py (creates test data)
   ↓
2. Import Postman collection
   ↓
3. Login with test credentials
   ↓
4. Explore all endpoints
```

### For Development Testing:

```
1. Import Postman collection
   ↓
2. Create data as needed via API
   ↓
3. Test specific features
```

---

## 🔐 Default Test Credentials

After running `seed_database.py`:

| Role | Email | Password |
|------|-------|----------|
| **Admin** | admin@salon.com | Admin123! |
| **RM** | rm@salon.com | RM123456! |
| **Customer** | customer@test.com | Password123! |

---

## 🎬 Quick Demo Flow

Want to see the complete flow? Follow these steps:

1. **Start backend:** `python main.py`
2. **Seed data:** `python seed_database.py`
3. **Open Postman** and import collection
4. **Run these requests in order:**
   - Login as Customer
   - Get All Salons
   - Get Salon Details
   - Get Salon Services
   - Create Booking
   - Create Payment Order
   - Verify Payment

**Result:** You've completed a full customer booking flow! 🎉

---

## 🐛 Troubleshooting

### "Connection refused"
- ✅ Make sure backend is running: `python main.py`
- ✅ Check port: Should be `http://localhost:8000`

### "Authentication failed"
- ✅ Run seeding script first
- ✅ Check credentials match the test data
- ✅ Token might be expired - login again

### "Salon/Service not found"
- ✅ Run seeding script to create test data
- ✅ Or create manually via Admin endpoints

### "Database errors"
- ✅ Check `.env` file has correct Supabase credentials
- ✅ Verify Supabase project is active
- ✅ Check database tables exist

---

## 📊 What Gets Created?

### After `seed_database.py`:

**Users:**
- 1 Admin (full access)
- 1 RM (relationship manager)
- 1 Customer (booking user)

**Services:**
- Hair Cut (₹500, 30 min)
- Hair Styling (₹800, 45 min)
- Facial Treatment (₹1200, 60 min)
- Manicure (₹400, 30 min)
- Pedicure (₹600, 45 min)

**Salons:**
- Luxury Hair Salon (Connaught Place)
- Elite Beauty Parlour (Saket)
- Style Studio (Karol Bagh)

---

## 🚀 Next Steps

After initial testing:

1. **Explore Admin Panel** - Manage salons, services, bookings
2. **Test Customer Features** - Cart, favorites, reviews
3. **Try RM Portal** - Dashboard, vendor management
4. **Payment Flow** - Create orders, verify payments
5. **Location Services** - Search nearby salons

---

## 💡 Pro Tips

- **Auto-save Variables:** Postman collection automatically saves IDs and tokens
- **Collection Runner:** Run entire test suites automatically
- **Environments:** Create different environments for dev/staging/prod
- **Pre-request Scripts:** Already included to chain requests
- **Test Scripts:** Add assertions to validate responses

---

## 📚 Documentation

For detailed information:

- **Full Testing Guide:** `API_TESTING_GUIDE.md`
- **Architecture:** `ARCHITECTURE_MAP.md`
- **API Documentation:** Visit `http://localhost:8000/docs` (when server is running)

---

## ✅ Testing Checklist

Quick checklist to verify everything works:

- [ ] Backend server starts successfully
- [ ] Seed script runs without errors
- [ ] Can login as Admin
- [ ] Can login as Customer
- [ ] Can view salons list
- [ ] Can create a booking
- [ ] Can create payment order
- [ ] Can view booking history

---

**Happy Testing! 🎉**

**Questions?** Check `API_TESTING_GUIDE.md` for detailed scenarios and troubleshooting.
