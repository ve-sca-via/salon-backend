 # 🔥 CRITICAL FIXES CHECKLIST
**Fix These IMMEDIATELY Before Production**

---

## ✅ CHECKLIST

### 🔴 CRITICAL (Production Blockers)

- [x] **Fix API Version Prefixes in salon-management-app** (2-3 hours) ✅ COMPLETED
  - [x] Fix `cartApi.js` - 2 endpoints (updateCartItem, removeFromCart)
  - [x] Fix `favoriteApi.js` - 1 endpoint (removeFavorite)
  - [x] Fix `reviewApi.js` - 1 endpoint (updateReview)
  - [x] Fix `vendorApi.js` - 5 endpoints (updateService, deleteService, updateStaff, deleteStaff, updateBookingStatus)
  - [x] Fix `paymentApi.js` - 1 endpoint (getVendorEarnings)
  - [ ] Test all affected pages

- [x] **Fix Hardcoded Localhost URL** (15 min) ✅ COMPLETED
  - [x] Update `salon-management-app/src/pages/public/Careers.jsx:150`
  - [x] Change `http://localhost:8000` to use `VITE_API_URL` env variable
  - [ ] Test career form submission

- [x] **Fix System Config API Path** (15 min) ✅ COMPLETED
  - [x] Update `salon-management-app/src/services/api/configApi.js`
  - [x] Change `/salons/config/public` to `/api/v1/salons/config/public`
  - [ ] Test config loading on app startup

### 🟠 HIGH PRIORITY (This Week)

- [x] **Build RM Leaderboard Page** (4-6 hours) ✅ COMPLETED
  - [x] Create `salon-management-app/src/pages/hmr/RMLeaderboard.jsx`
  - [x] Add route in App.jsx router
  - [x] Add `useGetRMLeaderboardQuery()` and `useGetRMSalonsQuery()` to rmApi.js
  - [x] Add navigation link in HMR dashboard header
  - [x] Add navigation link in sidebar menu

- [ ] **Build RM My Salons Page** (4-6 hours)
  - [ ] Create `salon-management-app/src/pages/hmr/RMMySalons.jsx`
  - [ ] Add RTK Query endpoint `getRMSalons` to rmApi.js
  - [ ] Display salon cards with status indicators
  - [ ] Add route and navigation

- [ ] **Complete Career Applications UI** (6-8 hours)
  - [ ] Add document viewer modal to `CareerApplications.jsx`
  - [ ] Implement search/filter functionality
  - [ ] Add bulk approval actions
  - [ ] Fix list refresh on status change
  - [ ] Add loading states

### 🟡 MEDIUM PRIORITY (This Month)

- [ ] **Unify Admin Panel Architecture** (8-10 hours)
  - [ ] Audit all `fetch()` calls in admin panel
  - [ ] Create RTK Query equivalents
  - [ ] Replace fetch with RTK Query hooks
  - [ ] Remove `backendApi.js`
  - [ ] Test all admin pages

- [ ] **Build Vendor Analytics Page** (8-10 hours)
  - [ ] Create `salon-management-app/src/pages/vendor/VendorAnalytics.jsx`
  - [ ] Add charts library (recharts recommended)
  - [ ] Implement revenue/booking charts
  - [ ] Add date range filters
  - [ ] Add route and navigation

- [ ] **Build RM Score History Details** (4-6 hours)
  - [ ] Create `salon-management-app/src/pages/hmr/RMScoreHistory.jsx`
  - [ ] Timeline view of score changes
  - [ ] Filter by action type
  - [ ] Add route and navigation

---

## 🛠️ DETAILED FIX INSTRUCTIONS

### 1. Fix API Version Prefixes

**Files to Update**:

#### `salon-management-app/src/services/api/cartApi.js`
```javascript
// BEFORE (line 11)
url: '/api/cart',

// AFTER
url: '/api/v1/customers/cart',
```

Repeat for all cart endpoints (add, update, remove, clear).

#### `salon-management-app/src/services/api/favoriteApi.js`
```javascript
// BEFORE
url: '/api/favorites',

// AFTER  
url: '/api/v1/customers/favorites',
```

#### `salon-management-app/src/services/api/reviewApi.js`
```javascript
// BEFORE
url: '/api/reviews',

// AFTER
url: '/api/v1/customers/reviews',
```

#### `salon-management-app/src/services/api/vendorApi.js`
```javascript
// BEFORE (multiple endpoints)
url: '/api/vendor/salon',
url: '/api/vendor/services',
url: '/api/vendor/staff',
url: '/api/vendor/bookings',

// AFTER
url: '/api/v1/vendors/salon',
url: '/api/v1/vendors/services', 
url: '/api/v1/vendors/staff',
url: '/api/v1/vendors/bookings',
```

#### `salon-management-app/src/services/api/paymentApi.js`
```javascript
// BEFORE
url: '/api/payments/booking/create-order',
url: '/api/payments/booking/verify',

// AFTER
url: '/api/v1/payments/booking/create-order',
url: '/api/v1/payments/booking/verify',
```

**Testing Checklist**:
- [ ] Cart add/remove/update works
- [ ] Favorites add/remove works
- [ ] Reviews submit/edit works
- [ ] Vendor salon update works
- [ ] Vendor services CRUD works
- [ ] Vendor staff CRUD works
- [ ] Vendor bookings load
- [ ] Payment order creation works
- [ ] Payment verification works

---

### 2. Fix Hardcoded Localhost URL

**File**: `salon-management-app/src/pages/public/Careers.jsx`

**Line 150** (approximately):
```javascript
// BEFORE ❌
const response = await fetch('http://localhost:8000/api/v1/careers/apply', {
  method: 'POST',
  body: formData,
});

// AFTER ✅
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const response = await fetch(`${API_URL}/api/v1/careers/apply`, {
  method: 'POST',
  body: formData,
});
```

**Environment Variable** (`.env`):
```env
VITE_API_URL=http://localhost:8000
```

**Testing**:
- [ ] Career form submits in development
- [ ] Update `.env.production` with production API URL
- [ ] Test in staging environment

---

### 3. Fix System Config API Path

**File**: `salon-management-app/src/services/api/configApi.js`

```javascript
// BEFORE ❌
getPublicConfig: builder.query({
  query: () => ({
    url: '/api/v1/config/public',
    method: 'get',
  }),
}),

// AFTER ✅
getPublicConfig: builder.query({
  query: () => ({
    url: '/api/v1/salons/config/public',
    method: 'get',
  }),
}),
```

**Testing**:
- [ ] App loads without config errors
- [ ] Config values display correctly in UI
- [ ] Check browser console for errors

---

### 4. Build RM Leaderboard Page

**File**: `salon-management-app/src/pages/hmr/RMLeaderboard.jsx`

```jsx
import React from 'react';
import DashboardLayout from '../../components/layout/DashboardLayout';
import Card from '../../components/shared/Card';
import { useGetRMLeaderboardQuery } from '../../services/api/rmApi';

const RMLeaderboard = () => {
  const { data, isLoading } = useGetRMLeaderboardQuery({ limit: 20 });
  const leaderboard = data?.data || [];

  if (isLoading) return <div>Loading...</div>;

  return (
    <DashboardLayout role="hmr">
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">RM Leaderboard</h1>
        
        <Card>
          <table className="w-full">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Name</th>
                <th>Score</th>
                <th>Salons Added</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((rm, index) => (
                <tr key={rm.id}>
                  <td>{index + 1}</td>
                  <td>{rm.full_name}</td>
                  <td>{rm.performance_score}</td>
                  <td>{rm.total_salons || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default RMLeaderboard;
```

**Add RTK Query Hook** (if missing):
```javascript
// In rmApi.js
getRMLeaderboard: builder.query({
  query: ({ limit = 20 } = {}) => ({
    url: '/api/v1/rm/leaderboard',
    method: 'get',
    params: { limit },
  }),
}),
```

**Add Route**:
```javascript
// In router
{
  path: '/hmr/leaderboard',
  element: <RMProtectedRoute><RMLeaderboard /></RMProtectedRoute>,
}
```

---

### 5. Build RM My Salons Page

**File**: `salon-management-app/src/pages/hmr/RMMySalons.jsx`

```jsx
import React from 'react';
import { Link } from 'react-router-dom';
import DashboardLayout from '../../components/layout/DashboardLayout';
import Card from '../../components/shared/Card';
import { useGetRMSalonsQuery } from '../../services/api/rmApi';

const RMMySalons = () => {
  const { data, isLoading } = useGetRMSalonsQuery();
  const salons = data?.data || [];

  if (isLoading) return <div>Loading...</div>;

  return (
    <DashboardLayout role="hmr">
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">My Salons</h1>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {salons.map((salon) => (
            <Card key={salon.id}>
              <h3 className="text-xl font-semibold">{salon.business_name}</h3>
              <p className="text-gray-600">{salon.city}, {salon.state}</p>
              <div className="mt-4 space-y-2">
                <div>
                  Status: <span className={
                    salon.is_active ? 'text-green-600' : 'text-red-600'
                  }>
                    {salon.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <div>
                  Verified: {salon.is_verified ? '✅' : '❌'}
                </div>
                <div>
                  Rating: ⭐ {salon.average_rating || 'N/A'}
                </div>
              </div>
              <Link 
                to={`/salon/${salon.id}`}
                className="mt-4 inline-block text-blue-600 hover:underline"
              >
                View Details →
              </Link>
            </Card>
          ))}
        </div>

        {salons.length === 0 && (
          <Card>
            <p className="text-center py-12 text-gray-600">
              No salons added yet. Add your first salon!
            </p>
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
};

export default RMMySalons;
```

**Add RTK Query Hook**:
```javascript
// In rmApi.js
getRMSalons: builder.query({
  query: ({ includeInactive = false } = {}) => ({
    url: '/api/v1/rm/salons',
    method: 'get',
    params: { include_inactive: includeInactive },
  }),
  providesTags: ['RMSalons'],
}),
```

---

## 📊 TESTING CHECKLIST

### Critical Path Testing

**Customer Flow**:
- [ ] Browse salons
- [ ] Add to cart ✅ (after fix #1)
- [ ] Add to favorites ✅ (after fix #1)
- [ ] Checkout and book
- [ ] Payment processing ✅ (after fix #1)
- [ ] Submit review ✅ (after fix #1)

**Vendor Flow**:
- [ ] Complete registration
- [ ] Update salon profile ✅ (after fix #1)
- [ ] Add/edit services ✅ (after fix #1)
- [ ] Manage staff ✅ (after fix #1)
- [ ] View bookings ✅ (after fix #1)

**RM Flow**:
- [ ] Submit vendor request
- [ ] View dashboard
- [ ] Check leaderboard ✅ (after fix #4)
- [ ] View my salons ✅ (after fix #5)
- [ ] Track score history

**Admin Flow**:
- [ ] Approve/reject vendor requests
- [ ] Manage users
- [ ] View dashboard stats
- [ ] Manage system config ✅ (after fix #3)
- [ ] Review career applications

---

## 🚀 DEPLOYMENT CHECKLIST

Before deploying to production:

- [ ] All critical fixes applied
- [ ] All tests passing
- [ ] Environment variables configured
- [ ] API URLs updated for production
- [ ] CORS settings verified
- [ ] Rate limiting tested
- [ ] Payment webhook verified
- [ ] Email notifications tested
- [ ] SSL certificates configured
- [ ] Database migrations run
- [ ] Backup strategy in place
- [ ] Error monitoring enabled (Sentry, etc.)
- [ ] Performance monitoring enabled
- [ ] Security headers configured
- [ ] Static assets CDN configured

---

## 📧 SUPPORT

If you need help with any of these fixes:

1. Check the detailed documentation in `FRONTEND_BACKEND_AUDIT_REPORT.md`
2. Review backend API docs in `/api/v1/docs` (when running locally)
3. Check logs in browser DevTools console
4. Test API endpoints directly with Postman/Thunder Client

---

**Last Updated**: November 18, 2025  
**Version**: 1.0  
**Priority**: CRITICAL - Fix immediately before production deployment
