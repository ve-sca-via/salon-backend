# 🔐 User Role & Signup Reference Guide

**Last Updated:** December 11, 2025  
**Roles:** customer | vendor | relationship_manager | admin

## Understanding User Roles

Your backend has **4 user roles** with different signup methods:

```
┌─────────────────────┬──────────────────────┬─────────────────────┐
│ Role                │ Value in DB/API      │ Signup Method       │
├─────────────────────┼──────────────────────┼─────────────────────┤
│ Customer            │ "customer"           │ Public API ✅       │
│ Relationship Mgr    │ "relationship_manager│ Admin API only      │
│ Vendor              │ "vendor"             │ Special flow        │
│ Admin               │ "admin"              │ Manual/Database     │
└─────────────────────┴──────────────────────┴─────────────────────┘
```

---

## ✅ Correct Role Values

**IMPORTANT:** Use these exact values:

```json
❌ WRONG: "relational_manager"
✅ RIGHT: "relationship_manager"

❌ WRONG: "rm"
✅ RIGHT: "relationship_manager"

❌ WRONG: "admin" (via public signup)
✅ RIGHT: "customer" (or create admin manually)
```

---

## 🚀 How to Create Each Role

### 1. Customer (Public Signup)

**Endpoint:** `POST /api/v1/auth/signup`

**Request Body:**
```json
{
  "email": "customer@example.com",
  "password": "Password123!",
  "full_name": "Customer Name",
  "phone": "+919876543210",
  "user_role": "customer"
}
```

**Response:** ✅ 200 OK with tokens

---

### 2. Relationship Manager (Admin API)

**Step 1:** First, you need an **admin account** (see method 4 below)

**Step 2:** Create RM using admin endpoint

**Endpoint:** `POST /api/v1/admin/users/`

**Headers:**
```
Authorization: Bearer {admin_access_token}
```

**Request Body:**
```json
{
  "email": "rm@example.com",
  "password": "RM123456!",
  "full_name": "RM Name",
  "phone": "+919876543212",
  "role": "relationship_manager"
}
```

**Response:** ✅ 200 OK

---

### 3. Vendor (Special Registration Flow)

Vendors go through a multi-step process:

1. **Salon registration** (creates vendor request)
2. **RM/Admin approval**
3. **Vendor completes registration** via token link

See `VENDOR_REGISTRATION_FLOW.md` for details.

---

### 4. Admin (Manual Creation)

**Method A: Supabase Dashboard (Recommended)**

1. Go to your Supabase project
2. Navigate to: **Authentication → Users**
3. Click **Add User**
4. Fill in:
   - Email: `admin@salon.com`
   - Password: `Admin123!`
   - Confirm email: ✅ (check this)
5. Click **Create User**
6. Copy the generated User ID
7. Navigate to: **Table Editor → profiles**
8. Click **Insert → Insert row**
9. Fill in:
   ```
   id: {paste User ID}
   email: admin@salon.com
   full_name: System Administrator
   phone: +919876543211
   user_role: admin
   is_active: true
   ```
10. Click **Save**

**Method B: SQL Query**

Run this in Supabase SQL Editor:

```sql
-- First, create auth user (get ID from Supabase Auth dashboard)
-- Then insert profile:

INSERT INTO profiles (id, email, full_name, phone, user_role, is_active)
VALUES (
  '{user_id_from_auth}',
  'admin@salon.com',
  'System Administrator',
  '+919876543211',
  'admin',
  true
);
```

---

## 🐛 Troubleshooting RLS Errors

### Error: "new row violates row-level security policy"

**What it means:** You're trying to create a restricted role via public API.

**Solution:** Use the correct method for that role (see above).

**Common Causes:**
```
❌ Trying to create admin via /auth/signup
❌ Trying to create RM via /auth/signup
❌ Using wrong role value ("rm" instead of "relationship_manager")
```

---

## 📝 Quick Reference for Your Error

**Your request:**
```json
{
  "email": "agent@salonhub.com",
  "password": "12345678",
  "full_name": "Relationship Manager",
  "phone": "+919876543212",
  "role": "relational_manager"  // ❌ WRONG on two counts
}
```

**Issues:**
1. ❌ `"relational_manager"` should be `"relationship_manager"`
2. ❌ Cannot create RM via public `/auth/signup` endpoint

**Fixed approach - Option 1 (Create as customer):**
```json
{
  "email": "agent@salonhub.com",
  "password": "12345678",
  "full_name": "Test Customer",
  "phone": "+919876543212",
  "user_role": "customer"  // ✅ Only allowed role for public signup
}
```

**Fixed approach - Option 2 (Create admin first, then use admin API):**

Step 1: Create admin manually in Supabase (see Method 4 above)

Step 2: Login as admin
```json
POST /api/v1/auth/login
{
  "email": "admin@salon.com",
  "password": "Admin123!"
}
```

Step 3: Use admin token to create RM
```json
POST /api/v1/admin/users/
Authorization: Bearer {admin_token}

{
  "email": "agent@salonhub.com",
  "password": "12345678",
  "full_name": "Relationship Manager",
  "phone": "+919876543212",
  "role": "relationship_manager"  // ✅ Correct value
}
```

---

## 🎯 Testing Recommendations

### For Local Development:

1. **Create admin manually** in Supabase (one-time)
2. **Use Postman** to create other roles as needed
3. **Keep admin credentials** handy for testing

### For Automated Testing:

1. **Seed script** creates only customers
2. **Test fixtures** mock other roles
3. **Use admin API** when role creation is needed

---

## 📊 Role Permissions Summary

```
Feature                    Customer  RM    Vendor  Admin
──────────────────────────────────────────────────────
Browse salons                 ✅      ✅     ✅      ✅
Create booking                ✅      ❌     ❌      ✅
Manage own bookings           ✅      ❌     ✅      ✅
Cart & checkout               ✅      ❌     ❌      ❌
Favorites & reviews           ✅      ❌     ❌      ❌
View RM dashboard             ❌      ✅     ❌      ✅
Manage vendor requests        ❌      ✅     ❌      ✅
Manage salon (own)            ❌      ❌     ✅      ✅
View vendor earnings          ❌      ❌     ✅      ✅
Manage all salons             ❌      ❌     ❌      ✅
Manage services               ❌      ❌     ❌      ✅
System configuration          ❌      ❌     ❌      ✅
View all users                ❌      ❌     ❌      ✅
Create users (RM/Customer)    ❌      ❌     ❌      ✅
```

---

## 🔧 Postman Collection Updates

The Postman collection has been configured with the correct role values:

**Customer Signup:**
```json
{
  "user_role": "customer"  // ✅
}
```

**Admin Create RM** (via admin endpoint):
```json
{
  "role": "relationship_manager"  // ✅
}
```

---

## 💡 Pro Tips

1. **Always use "customer" for public signup** - It's the only allowed role
2. **Create ONE admin manually** - Then use admin API for everything else
3. **Check role spelling** - Common mistake: "rm" vs "relationship_manager"
4. **Use correct endpoint** - Public signup vs Admin API
5. **Check RLS policies** - If you get 403, you're using wrong endpoint

---

## 🆘 Still Having Issues?

### Error: "Invalid role. Use customer signup only."
- ✅ You're using correct endpoint but wrong role
- ✅ Change `user_role` to `"customer"`

### Error: "new row violates row-level security"
- ✅ You're trying restricted operation
- ✅ Create admin first, then use admin API

### Error: "Email already registered"
- ✅ User exists already
- ✅ Try logging in instead

### Error: "Unauthorized"
- ✅ Your admin token expired
- ✅ Login again to get new token

---

## 📚 Related Documentation

- `API_TESTING_GUIDE.md` - Complete API testing scenarios
- `AUTH_INTEGRATION_GUIDE.md` - Authentication implementation
- `SECURITY_AUDIT_REPORT.md` - Security policies explained

---

**Remember:** The restriction on role creation is a **security feature**, not a bug! It prevents unauthorized users from elevating their privileges.
