# Frontend API Usage Analysis

## Executive Summary

This document provides a comprehensive analysis of all API endpoints being called by both frontend applications:
- **salon-admin-panel** (Admin Dashboard)
- **salon-management-app** (Customer/Vendor/RM Portal)

## Table of Contents
1. [Admin Panel APIs](#admin-panel-apis)
2. [Management App APIs](#management-app-apis)
3. [Duplicate/Shared Endpoints](#duplicateshared-endpoints)
4. [Hardcoded URLs](#hardcoded-urls)
5. [API Architecture](#api-architecture)
6. [Recommendations](#recommendations)

---

## Admin Panel APIs

### API Service Layer Architecture
**Location**: `salon-admin-panel/src/services/`

The admin panel uses **TWO different API integration approaches**:
1. **backendApi.js** - Direct fetch API calls (legacy)
2. **api/*.js** - RTK Query with axios (modern)

### 1. Authentication Endpoints
**Source**: `backendApi.js`

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/auth/login` | POST | Admin login | Login.jsx |
| `/api/v1/auth/logout` | POST | Admin logout | Various |
| `/api/v1/auth/me` | GET | Get current admin profile | Auth flow |
| `/api/v1/auth/refresh` | POST | Refresh access token | baseQuery.js interceptor |

### 2. Admin Dashboard Statistics
**Source**: `api/adminApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/stats` | GET | Dashboard statistics | Dashboard.jsx |

### 3. Vendor Request Management
**Source**: `backendApi.js` AND `api/salonApi.js`

| Endpoint | Method | Purpose | Used In | Source |
|----------|--------|---------|---------|--------|
| `/api/v1/admin/vendor-requests?status_filter=pending` | GET | Get pending vendor requests | backendApi.js | Legacy |
| `/api/v1/admin/vendor-requests` | GET | Get vendor requests (with filters) | PendingSalons.jsx | RTK Query |
| `/api/v1/admin/vendor-requests/{id}/approve` | POST | Approve vendor request | PendingSalons.jsx | Both |
| `/api/v1/admin/vendor-requests/{id}/reject` | POST | Reject vendor request | PendingSalons.jsx | Both |

### 4. Salon Management
**Source**: `api/salonApi.js` (RTK Query) AND `backendApi.js`

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/salons` | GET | Get all salons (with filters) | Salons.jsx |
| `/api/v1/admin/salons/{id}` | GET | Get single salon details | Salon detail view |
| `/api/v1/admin/salons/{id}` | PUT | Update salon | Salons.jsx |
| `/api/v1/admin/salons/{id}` | DELETE | Delete salon | Salons.jsx |
| `/api/v1/admin/salons/{id}/status` | PUT | Toggle salon active status | Salons.jsx |

### 5. User Management
**Source**: `api/userApi.js` (RTK Query) AND `backendApi.js`

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/users/` | GET | Get all users (with filters) | Users.jsx |
| `/api/v1/admin/users/{id}` | GET | Get single user | User detail view |
| `/api/v1/admin/users/` | POST | Create new user | Users.jsx |
| `/api/v1/admin/users/{id}` | PUT | Update user | Users.jsx |
| `/api/v1/admin/users/{id}` | DELETE | Delete user | Users.jsx |

### 6. RM Management
**Source**: `api/userApi.js` (RTK Query) AND `backendApi.js`

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/rms` | GET | Get all RMs | RMManagement.jsx |
| `/api/v1/admin/rms/{id}` | GET | Get RM profile | backendApi.js |
| `/api/v1/admin/rms/{id}/status` | PUT | Update RM status | RMManagement.jsx |
| `/api/v1/admin/rms/{id}/score-history` | GET | Get RM score history | backendApi.js |

### 7. Booking/Appointment Management
**Source**: `api/appointmentApi.js` (RTK Query) AND `backendApi.js`

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/bookings` | GET | Get all bookings (with filters) | Appointments.jsx |
| `/api/v1/admin/bookings/{id}` | GET | Get single booking | Appointment detail |
| `/api/v1/admin/bookings/{id}/status` | PUT | Update booking status | Appointments.jsx |
| `/api/v1/admin/bookings/{id}` | DELETE | Delete booking | Appointments.jsx |

### 8. Service Management
**Source**: `backendApi.js` (fetch API)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/services` | GET | Get all services | Services.jsx |
| `/api/v1/admin/services` | POST | Create service | Services.jsx |
| `/api/v1/admin/services/{id}` | PUT | Update service | Services.jsx |
| `/api/v1/admin/services/{id}` | DELETE | Delete service | Services.jsx |

### 9. Staff Management
**Source**: `backendApi.js` (fetch API)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/staff` | GET | Get all staff | Staff.jsx |
| `/api/v1/admin/staff/{id}` | PUT | Update staff | Staff.jsx |
| `/api/v1/admin/staff/{id}` | DELETE | Delete staff | Staff.jsx |

### 10. System Configuration
**Source**: `backendApi.js` (fetch API)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/admin/config` | GET | Get all system configs | SystemConfig.jsx |
| `/api/v1/admin/config` | POST | Create new config | SystemConfig.jsx |
| `/api/v1/admin/config/{key}` | GET | Get specific config | backendApi.js |
| `/api/v1/admin/config/{key}` | PUT | Update config | SystemConfig.jsx |
| `/api/v1/admin/config/{key}` | DELETE | Delete config | SystemConfig.jsx |
| `/api/v1/admin/dashboard/stats` | GET | Dashboard stats (deprecated?) | backendApi.js |

### 11. Career Applications
**Source**: `api/careerApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/careers/applications` | GET | Get all applications (with filters) | CareerApplications.jsx |
| `/api/v1/careers/applications/{id}` | GET | Get single application | CareerApplications.jsx |
| `/api/v1/careers/applications/{id}` | PATCH | Update application status | CareerApplications.jsx |
| `/api/v1/careers/applications/{id}/download/{type}` | GET | Get document download URL | CareerApplications.jsx |

### 12. Location Services
**Source**: `backendApi.js` (fetch API)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/location/geocode` | POST | Geocode address to coordinates | backendApi.js |
| `/api/v1/location/reverse-geocode` | POST | Reverse geocode coordinates | backendApi.js |
| `/api/v1/location/salons/nearby` | POST | Find salons near location | backendApi.js |

---

## Management App APIs

### API Service Layer Architecture
**Location**: `salon-management-app/src/services/`

The management app uses **RTK Query exclusively** with axios interceptors for token management.

### 1. Authentication Endpoints
**Source**: `api/authApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/auth/login` | POST | User login (customer/vendor/rm) | Login page |
| `/api/v1/auth/signup` | POST | User signup | Signup page |
| `/api/v1/auth/me` | GET | Get current user profile | Auth flow |
| `/api/v1/auth/logout` | POST | Logout current session | Various |
| `/api/v1/auth/logout-all` | POST | Logout from all devices | Settings |
| `/api/v1/auth/refresh` | POST | Refresh access token | apiClient.js interceptor |

### 2. Public Salon Browsing
**Source**: `api/salonApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/salons/public` | GET | Get all public salons | PublicSalonListing.jsx |
| `/api/v1/salons/{id}` | GET | Get single salon details | SalonDetail.jsx |
| `/api/v1/salons/search/query` | GET | Search salons by query | Search functionality |
| `/api/v1/salons/search/nearby` | GET | Search nearby salons | Location search |
| `/api/v1/salons/{id}/services` | GET | Get salon services | SalonDetail.jsx |
| `/api/v1/salons/{id}/staff` | GET | Get salon staff | ServiceBooking.jsx |
| `/api/v1/salons/{id}/available-slots` | GET | Get available booking slots | ServiceBooking.jsx |
| `/api/v1/salons/config/booking-fee-percentage` | GET | Get booking fee config | Checkout.jsx |

### 3. Customer Cart Management
**Source**: `api/cartApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/customers/cart` | GET | Get customer cart | Cart.jsx |
| `/api/v1/customers/cart` | POST | Add item to cart | Service selection |
| `/api/customers/cart/{id}` | PUT | Update cart item quantity | Cart.jsx |
| `/api/customers/cart/{id}` | DELETE | Remove cart item | Cart.jsx |
| `/api/v1/customers/cart/clear/all` | DELETE | Clear entire cart | Cart.jsx |

### 4. Customer Booking Management
**Source**: `api/bookingApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/customers/bookings/my-bookings` | GET | Get customer bookings | Customer dashboard |
| `/api/v1/bookings` | POST | Create new booking | Checkout.jsx |
| `/api/v1/customers/bookings/{id}/cancel` | PUT | Cancel booking | Booking management |

### 5. Customer Favorites
**Source**: `api/favoriteApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/customers/favorites` | GET | Get user favorites | Favorites page |
| `/api/v1/customers/favorites` | POST | Add salon to favorites | Salon detail |
| `/api/customers/favorites/{id}` | DELETE | Remove from favorites | Favorites page |

### 6. Customer Reviews
**Source**: `api/reviewApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/customers/reviews/my-reviews` | GET | Get customer reviews | Reviews page |
| `/api/v1/customers/reviews` | POST | Create review | Review submission |
| `/api/customers/reviews/{id}` | PUT | Update review | Review edit |

### 7. Payment Integration (Razorpay)
**Source**: `api/paymentApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/payments/booking/create-order` | POST | Create Razorpay booking order | Checkout.jsx |
| `/api/v1/payments/booking/verify` | POST | Verify payment signature | Payment.jsx |
| `/api/v1/payments/registration/create-order` | POST | Create vendor registration order | VendorPayment.jsx |
| `/api/v1/payments/registration/verify` | POST | Verify registration payment | VendorPayment.jsx |
| `/api/v1/payments/history` | GET | Get payment history | Payment history |
| `/api/payments/vendor/{id}/earnings` | GET | Get vendor earnings | Vendor dashboard |

### 8. Vendor Salon Management
**Source**: `api/vendorApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/vendors/salon` | GET | Get vendor's salon | VendorDashboard.jsx |
| `/api/v1/vendors/salon` | PUT | Update salon profile | SalonProfile.jsx |
| `/api/v1/vendors/complete-registration` | POST | Complete vendor registration | CompleteRegistration.jsx |
| `/api/v1/vendors/process-payment` | POST | Process vendor payment (demo) | VendorPayment.jsx |

### 9. Vendor Service Management
**Source**: `api/vendorApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/vendors/service-categories` | GET | Get service categories | ServicesManagement.jsx |
| `/api/v1/vendors/services` | GET | Get vendor services | ServicesManagement.jsx |
| `/api/v1/vendors/services` | POST | Create service | ServicesManagement.jsx |
| `/api/vendors/services/{id}` | PUT | Update service | ServicesManagement.jsx |
| `/api/vendors/services/{id}` | DELETE | Delete service | ServicesManagement.jsx |

### 10. Vendor Staff Management
**Source**: `api/vendorApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/vendors/staff` | GET | Get vendor staff | StaffManagement.jsx |
| `/api/v1/vendors/staff` | POST | Create staff member | StaffManagement.jsx |
| `/api/vendors/staff/{id}` | PUT | Update staff member | StaffManagement.jsx |
| `/api/vendors/staff/{id}` | DELETE | Delete staff member | StaffManagement.jsx |

### 11. Vendor Booking Management
**Source**: `api/vendorApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/vendors/bookings` | GET | Get vendor bookings | BookingsManagement.jsx |
| `/api/vendors/bookings/{id}/status` | PUT | Update booking status | BookingsManagement.jsx |
| `/api/v1/vendors/analytics` | GET | Get vendor analytics | VendorDashboard.jsx |

### 12. RM (Relationship Manager) Operations
**Source**: `api/rmApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/rm/vendor-requests` | POST | Submit vendor join request | SubmitSalon.jsx |
| `/api/v1/rm/vendor-requests` | GET | Get RM's vendor requests | SubmissionHistory.jsx |
| `/api/v1/rm/vendor-requests/{id}` | GET | Get specific vendor request | RequestDetail.jsx |
| `/api/v1/rm/vendor-requests/{id}` | PUT | Update vendor request | EditRequest.jsx |
| `/api/v1/rm/vendor-requests/{id}` | DELETE | Delete vendor request | Drafts.jsx |
| `/api/v1/rm/dashboard` | GET | Get RM profile & stats | HMRDashboard.jsx |
| `/api/v1/rm/profile` | PUT | Update RM profile | RMProfile.jsx |
| `/api/v1/rm/score-history` | GET | Get RM score history | RMProfile.jsx |
| `/api/v1/rm/service-categories` | GET | Get service categories | Form dropdowns |

### 13. File Upload
**Source**: `api/uploadApi.js` (axios direct)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/upload/salon-image?folder={folder}` | POST | Upload salon image | Image upload components |

### 14. System Configuration
**Source**: `api/configApi.js` (RTK Query)

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/salons/config/public` | GET | Get public system configs | Config context |

### 15. Career Applications (Public)
**Source**: Direct fetch in `Careers.jsx`

| Endpoint | Method | Purpose | Used In |
|----------|--------|---------|---------|
| `/api/v1/careers/apply` | POST | Submit career application | Careers.jsx |

---

## Duplicate/Shared Endpoints

### 1. Authentication Endpoints
**IDENTICAL** across both frontends:
- `/api/v1/auth/login` - POST
- `/api/v1/auth/logout` - POST  
- `/api/v1/auth/me` - GET
- `/api/v1/auth/refresh` - POST

### 2. Vendor Request Management
**SHARED** between admin and RM:
- `/api/v1/admin/vendor-requests` (Admin)
- `/api/v1/rm/vendor-requests` (RM)

Both access the same data with different permissions.

### 3. Salon Data
**DIFFERENT** endpoints for different roles:
- Admin: `/api/v1/admin/salons` (full access)
- Public: `/api/v1/salons/public` (public view)
- Vendor: `/api/v1/vendors/salon` (own salon only)

### 4. Service Management
**ROLE-BASED**:
- Admin: `/api/v1/admin/services` (all services)
- Vendor: `/api/v1/vendors/services` (own services)
- RM: `/api/v1/rm/service-categories` (categories for forms)

### 5. Booking Management
**ROLE-BASED**:
- Admin: `/api/v1/admin/bookings` (all bookings)
- Customer: `/api/v1/customers/bookings/my-bookings` (own bookings)
- Vendor: `/api/v1/vendors/bookings` (salon bookings)

---

## Hardcoded URLs

### ⚠️ CRITICAL ISSUES

#### 1. Career Application Submission
**File**: `salon-management-app/src/pages/public/Careers.jsx`
**Line 150**:
```javascript
const response = await fetch('http://localhost:8000/api/v1/careers/apply', {
  method: 'POST',
  body: formDataToSend
});
```

**Problem**: Hardcoded localhost URL - will break in production!
**Fix Required**: Should use `BACKEND_URL` from env or `apiClient`.

#### 2. Public Config Endpoint
**File**: `salon-management-app/src/services/api/configApi.js`
```javascript
url: '/salons/config/public',
```

**Problem**: Missing `/api/v1` prefix - inconsistent with other endpoints
**Expected**: `/api/v1/salons/config/public`

#### 3. Cart/Favorites Endpoint Inconsistencies
**Files**: 
- `cartApi.js` - Uses `/api/customers/cart/{id}` (missing v1)
- `favoriteApi.js` - Uses `/api/customers/favorites/{id}` (missing v1)
- `reviewApi.js` - Uses `/api/customers/reviews/{id}` (missing v1)
- `vendorApi.js` - Uses `/api/vendors/services/{id}` and `/api/vendors/staff/{id}` (missing v1)
- `vendorApi.js` - Uses `/api/vendors/bookings/{id}` (missing v1)
- `paymentApi.js` - Uses `/api/payments/vendor/{id}` (missing v1)

**Problem**: Inconsistent versioning across PUT/DELETE operations
**Pattern**: GET uses `/api/v1/...` but PUT/DELETE use `/api/...`

---

## API Architecture

### Admin Panel Architecture

```
┌─────────────────────────────────────────────┐
│         Admin Panel Frontend                │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐      ┌─────────────────┐│
│  │ backendApi.js│◄────►│ Fetch API       ││ (Legacy)
│  │ (fetch)      │      │ localStorage    ││
│  └──────────────┘      └─────────────────┘│
│                                             │
│  ┌──────────────┐      ┌─────────────────┐│
│  │ RTK Query    │◄────►│ Axios Instance  ││ (Modern)
│  │ API Slices   │      │ Interceptors    ││
│  └──────────────┘      └─────────────────┘│
│         ▲                       ▲           │
└─────────┼───────────────────────┼──────────┘
          │                       │
          └───────────────────────┘
                   HTTP
          ┌───────────────────────┐
          │   Backend API Server  │
          │   localhost:8000      │
          └───────────────────────┘
```

**Problems**:
- 🔴 **Dual Architecture**: Mix of fetch and RTK Query
- 🔴 **Duplicate Code**: Same endpoints defined twice
- 🔴 **Inconsistent Error Handling**: Different patterns

### Management App Architecture

```
┌─────────────────────────────────────────────┐
│      Management App Frontend                │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐      ┌─────────────────┐│
│  │ RTK Query    │◄────►│ apiClient.js    ││
│  │ API Slices   │      │ (Axios)         ││
│  └──────────────┘      │ Interceptors    ││
│         ▲              │ Token Refresh   ││
│         │              └─────────────────┘│
│         │                       ▲          │
└─────────┼───────────────────────┼──────────┘
          │                       │
          └───────────────────────┘
                   HTTP
          ┌───────────────────────┐
          │   Backend API Server  │
          │   localhost:8000      │
          └───────────────────────┘
```

**Advantages**:
- ✅ Single API architecture (RTK Query)
- ✅ Consistent patterns
- ✅ Automatic caching and invalidation
- ✅ Token refresh handled centrally

---

## Recommendations

### 🔴 CRITICAL (Must Fix)

1. **Remove Hardcoded URL in Careers.jsx**
   ```javascript
   // Current (WRONG):
   fetch('http://localhost:8000/api/v1/careers/apply', ...)
   
   // Should be:
   import apiClient from '../../services/apiClient';
   apiClient.post('/api/v1/careers/apply', formDataToSend, {
     headers: { 'Content-Type': 'multipart/form-data' }
   });
   ```

2. **Fix Inconsistent Endpoint Versioning**
   - Add `/v1/` to all customer/vendor endpoints
   - Update all PUT/DELETE operations in:
     - `cartApi.js`
     - `favoriteApi.js`
     - `reviewApi.js`
     - `vendorApi.js`
     - `paymentApi.js`

3. **Standardize Admin Panel Architecture**
   - Migrate all `backendApi.js` calls to RTK Query
   - Remove duplicate endpoint definitions
   - Consolidate error handling

### 🟡 MEDIUM PRIORITY

4. **Fix Config Endpoint**
   ```javascript
   // Current:
   url: '/salons/config/public'
   
   // Should be:
   url: '/api/v1/salons/config/public'
   ```

5. **Standardize Response Formats**
   - Backend should consistently return either:
     - `{ data: {...} }` (wrapped)
     - Direct object `{...}` (unwrapped)
   - Frontend should not need to handle both patterns

6. **Add Missing API Documentation**
   - Document expected request/response formats
   - Add API versioning guidelines
   - Create endpoint naming conventions

### 🟢 NICE TO HAVE

7. **Create Shared API Package**
   - Extract common endpoints (auth, etc.)
   - Share TypeScript types
   - Reduce duplication

8. **Add API Monitoring**
   - Log all API calls in development
   - Track response times
   - Monitor error rates

9. **Implement API Testing**
   - Add integration tests for critical flows
   - Mock API responses for frontend tests
   - Add contract testing

---

## Summary Statistics

### Admin Panel
- **Total Unique Endpoints**: ~45
- **API Definition Files**: 6 (RTK Query) + 1 (fetch)
- **Pages Using APIs**: 11
- **Architecture**: Mixed (fetch + RTK Query)

### Management App
- **Total Unique Endpoints**: ~60
- **API Definition Files**: 9 (RTK Query) + 1 (client)
- **Pages Using APIs**: 20+
- **Architecture**: Unified (RTK Query)

### Shared Endpoints
- **Auth**: 4 endpoints
- **Vendor Requests**: 2 endpoint patterns
- **Total Overlap**: ~10%

### Critical Issues Found
- 🔴 **1** Hardcoded localhost URL
- 🔴 **15+** Missing `/v1/` version prefixes
- 🟡 **1** Inconsistent config endpoint
- 🟡 **Dual architecture** in admin panel

---

## Next Steps

1. **Immediate**: Fix hardcoded URL in Careers.jsx
2. **This Sprint**: Add missing `/v1/` prefixes to all endpoints
3. **Next Sprint**: Migrate admin panel to full RTK Query
4. **Future**: Create shared API package for both frontends

---

*Document Generated*: 2025-11-18
*Last Updated*: 2025-11-18
*Author*: API Analysis Tool
