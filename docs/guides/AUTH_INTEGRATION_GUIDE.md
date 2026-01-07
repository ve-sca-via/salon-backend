# Authentication Integration Guide

**Status:** ✅ Backend Auth Fully Working  
**Date:** November 18, 2025  
**Environment:** Local Development

## 🎯 Overview

All authentication endpoints are now working with the production schema. This guide shows you how to integrate them into your frontend applications.

---

## 🔑 Working Endpoints

### 1. User Signup (Registration)

**Endpoint:** `POST /api/v1/auth/signup`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "Test@123456",
  "full_name": "John Doe",
  "phone": "9876543210",
  "user_role": "customer"
}
```

**Success Response (201):**
```json
{
  "success": true,
  "message": "Account created successfully!",
  "user_id": "af92db01-2910-4b46-b501-9b9802f17904",
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "user": {
    "id": "af92db01-2910-4b46-b501-9b9802f17904",
    "email": "user@example.com",
    "full_name": "John Doe",
    "user_role": "customer",
    "role": "customer",
    "phone": "9876543210",
    "is_active": true
  }
}
```

**Notes:**
- Only `customer` role is allowed for public signup
- Password must be at least 6 characters
- Phone is optional but recommended
- User is auto-logged in (tokens provided)

---

### 2. User Login

**Endpoint:** `POST /api/v1/auth/login`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "Test@123456"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "af92db01-2910-4b46-b501-9b9802f17904",
    "email": "user@example.com",
    "full_name": "John Doe",
    "user_role": "customer",
    "role": "customer",
    "phone": "9876543210",
    "is_active": true
  }
}
```

**Error Response (401):**
```json
{
  "success": false,
  "message": "Invalid credentials",
  "error_code": "HTTP_401"
}
```

---

### 3. Get Current User Profile

**Endpoint:** `GET /api/v1/auth/me`

**Headers:**
```
Authorization: Bearer {access_token}
```

**Success Response (200):**
```json
{
  "success": true,
  "user": {
    "id": "af92db01-2910-4b46-b501-9b9802f17904",
    "full_name": "John Doe",
    "email": "user@example.com",
    "phone": "9876543210",
    "avatar_url": null,
    "address_line1": null,
    "address_line2": null,
    "city": null,
    "state": null,
    "pincode": null,
    "phone_verified": false,
    "phone_verified_at": null,
    "phone_verification_method": null,
    "user_role": "customer",
    "is_active": true,
    "created_at": "2025-11-17T20:35:08.025437+00:00",
    "updated_at": "2025-11-17T20:35:08.025437+00:00",
    "deleted_at": null,
    "deleted_by": null,
    "role": "customer"
  }
}
```

**Notes:**
- Use this to check if user is still authenticated
- Call on app startup if access_token exists in storage
- If 401 error, token expired → use refresh token

---

## 🔄 Frontend Integration Steps

### Step 1: Update API Base URL

**For Local Development:**
```javascript
const API_BASE_URL = "http://localhost:8000/api/v1";
```

### Step 2: Update Auth Service/API

**Example for signup:**
```javascript
// services/api/auth.js or similar

export const signup = async (userData) => {
  const response = await fetch(`${API_BASE_URL}/auth/signup`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      email: userData.email,
      password: userData.password,
      full_name: userData.fullName,
      phone: userData.phone,
      user_role: 'customer'
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Signup failed');
  }

  const data = await response.json();
  
  // Store tokens
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  localStorage.setItem('user', JSON.stringify(data.user));
  
  return data;
};
```

**Example for login:**
```javascript
export const login = async (email, password) => {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Login failed');
  }

  const data = await response.json();
  
  // Store tokens
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  localStorage.setItem('user', JSON.stringify(data.user));
  
  return data;
};
```

**Example for getting current user:**
```javascript
export const getCurrentUser = async () => {
  const token = localStorage.getItem('access_token');
  
  if (!token) {
    throw new Error('No access token found');
  }

  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
    }
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Token expired, try refresh
      throw new Error('TOKEN_EXPIRED');
    }
    throw new Error('Failed to fetch user');
  }

  const data = await response.json();
  return data.user;
};
```

### Step 3: Update Redux/Store (if using)

**Check what field names your store expects:**

⚠️ **IMPORTANT:** Backend now returns:
- `user_role` (primary field)
- `role` (backward compatibility, same value)

**If your frontend expects `role`:** ✅ It's already provided!

**Example store update:**
```javascript
// store/slices/authSlice.js

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
  },
  reducers: {
    setCredentials: (state, action) => {
      state.user = action.payload.user;
      state.accessToken = action.payload.access_token;
      state.refreshToken = action.payload.refresh_token;
      state.isAuthenticated = true;
    },
    logout: (state) => {
      state.user = null;
      state.accessToken = null;
      state.refreshToken = null;
      state.isAuthenticated = false;
      localStorage.clear();
    }
  }
});
```

---

## 🚨 Breaking Changes to Check

### Field Names

| Old Field (if any) | New Field | Notes |
|-------------------|-----------|-------|
| `role` | `user_role` (primary) | Backend still returns `role` for compatibility |
| `name` | `full_name` | Consistently `full_name` everywhere |
| - | `phone_verified` | New field, defaults to `false` |
| - | `deleted_at` | Soft delete support (null = active) |

### Response Structure

All responses now follow this pattern:
```json
{
  "success": true,  // or false
  "message": "...",  // optional
  "data": {...}      // or specific keys like "user", "access_token"
}
```

---

## ✅ Testing Checklist

Use this to verify frontend integration:

- [ ] Signup form submits to `/api/v1/auth/signup`
- [ ] Tokens are stored after signup
- [ ] Login form submits to `/api/v1/auth/login`
- [ ] Tokens are stored after login
- [ ] Protected routes check for `access_token`
- [ ] App fetches current user on startup (if token exists)
- [ ] User data displays correctly (name, email, role)
- [ ] Logout clears tokens and redirects

---

## 🐛 Common Issues & Fixes

### Issue 1: CORS Error
**Symptom:** `Access-Control-Allow-Origin` error in browser console

**Fix:** Backend already allows your frontend URL. Check:
```
ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000,http://localhost:5174"
```

Make sure your frontend runs on one of these ports.

---

### Issue 2: 401 Unauthorized on /me endpoint
**Symptom:** `/auth/me` returns 401 even after login

**Fix:** Check Authorization header format:
```javascript
headers: {
  'Authorization': `Bearer ${token}`  // Note: "Bearer " with space
}
```

---

### Issue 3: User role not displaying
**Symptom:** `user.role` is undefined

**Fix:** Backend returns both `user_role` and `role`. Use either:
```javascript
const role = user.user_role || user.role;  // Fallback
```

---

## 🎯 Next Steps

Once authentication is working in frontend:

1. **Test the full flow:**
   - Signup → Auto-login → Dashboard
   - Login → Dashboard
   - Logout → Redirect to login
   - Refresh page → Still logged in (token from localStorage)

2. **Protect routes:**
   - Use `access_token` to guard protected pages
   - Redirect to login if token missing/expired

3. **Handle token refresh:**
   - Implement refresh token logic (not tested yet in backend)
   - Auto-refresh before token expires

4. **Test role-based access:**
   - Customer can access customer portal
   - Vendor can access vendor portal (need to test vendor creation)
   - Admin can access admin panel

---

## 📞 Questions?

If frontend integration fails:

1. Check browser console for errors
2. Check Network tab for actual request/response
3. Verify API base URL matches backend (`http://localhost:8000/api/v1`)
4. Ensure backend is running (`.\run-local.ps1`)
5. Test endpoint with curl/Postman first to isolate issue

---

**Status:** Ready for frontend integration! 🚀
