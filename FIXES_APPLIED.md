# Fixes Applied for Pending Salon Workflow

## Issues Fixed:

### 1. ✅ Auto-Submit Issue on "Save as Draft" Button
**Problem:** The form was auto-submitting when clicking anywhere on step 4

**Root Cause:** The "Save as Draft" button's onClick handler was triggering form submission

**Fix Applied:**
- File: `salon-management-app/src/pages/hmr/AddSalonForm.jsx`
- Added `e.preventDefault()` and `e.stopPropagation()` to prevent event bubbling
- Changed button handler to explicitly call handleSubmit function

```jsx
// BEFORE:
onClick={handleSubmit((data) => onSubmit(data, true))}

// AFTER:
onClick={(e) => {
  e.preventDefault();
  e.stopPropagation();
  handleSubmit((data) => onSubmit(data, true))();
}}
```

---

### 2. ✅ RLS Policy Error (42501)
**Problem:** 500 Internal Server Error when submitting salon
```
'new row violates row-level security policy for table "vendor_join_requests"'
```

**Root Cause:** Missing INSERT policy for `vendor_join_requests` table. Only had SELECT policy for realtime.

**Fix Applied:**
- File: `backend/fix_vendor_join_requests_rls.sql`
- Created comprehensive RLS policies:
  1. Service role full access
  2. RMs can INSERT own requests
  3. RMs can SELECT own requests
  4. Admins can SELECT all requests
  5. Admins can UPDATE requests
  6. Anon can SELECT (for realtime)

**Run this SQL in Supabase SQL Editor:**
```sql
-- See: backend/fix_vendor_join_requests_rls.sql
```

---

### 3. ✅ Admin Panel Not Showing Pending Salons
**Problem:** Admin panel showing 0 pending salons even though table has records

**Root Cause:** Wrong query parameter - using `status=pending` instead of `status_filter=pending`

**Fix Applied:**
- File: `salon-admin-panel/src/services/backendApi.js`
- Changed API call from:
  ```javascript
  /api/admin/vendor-requests?status=pending
  ```
  To:
  ```javascript
  /api/admin/vendor-requests?status_filter=pending
  ```

---

## How to Apply Fixes:

### Step 1: Apply Database Fix (CRITICAL)
```bash
# In Supabase Dashboard:
# 1. Go to SQL Editor
# 2. Open: backend/fix_vendor_join_requests_rls.sql
# 3. Run the entire script
# 4. Verify policies created successfully
```

### Step 2: Restart Frontend Applications
```bash
# Terminal 1 - Salon Management App
cd salon-management-app
npm run dev

# Terminal 2 - Admin Panel  
cd salon-admin-panel
npm run dev
```

### Step 3: Test the Workflow

#### Test 1: Submit Salon (RM Portal)
1. Go to: http://localhost:3000/hmr/add-salon
2. Fill all 4 steps
3. On step 4:
   - Click "Save as Draft" - should NOT auto-submit ✅
   - Click "Submit for Approval" - should submit successfully ✅
4. Should see success message and redirect to dashboard

#### Test 2: View in Admin Panel
1. Go to: http://localhost:5173/pending-salons
2. Login as admin
3. Should see the submitted salon in the list ✅
4. Bell icon should show badge with count ✅

#### Test 3: Real-time Notification
1. Keep admin panel open
2. In another browser/incognito, submit a new salon as RM
3. Admin panel should:
   - Bell bounces ✅
   - Badge updates ✅
   - Toast notification appears ✅
   - List refreshes automatically ✅

---

## Verification Commands:

### Check RLS Policies:
```sql
-- In Supabase SQL Editor
SELECT schemaname, tablename, policyname, permissive, roles, cmd
FROM pg_policies
WHERE tablename = 'vendor_join_requests'
ORDER BY policyname;
```

Expected output:
```
vendor_join_requests | Admins can update requests      | authenticated | UPDATE
vendor_join_requests | Admins can view all requests    | authenticated | SELECT
vendor_join_requests | Enable realtime for anon        | anon          | SELECT
vendor_join_requests | RMs can insert own requests     | authenticated | INSERT
vendor_join_requests | RMs can view own requests       | authenticated | SELECT
vendor_join_requests | Service role has full access    | service_role  | ALL
```

### Check Pending Requests:
```sql
-- In Supabase SQL Editor
SELECT id, business_name, owner_name, status, created_at
FROM vendor_join_requests
WHERE status = 'pending'
ORDER BY created_at DESC
LIMIT 10;
```

### Test Backend API:
```bash
# In PowerShell (with admin token)
$headers = @{
    "Authorization" = "Bearer YOUR_ADMIN_TOKEN"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/admin/vendor-requests?status_filter=pending" -Headers $headers | ConvertTo-Json
```

---

## Summary of Changes:

| Issue | File | Change Type | Status |
|-------|------|-------------|--------|
| Auto-submit on draft button | AddSalonForm.jsx | Code Fix | ✅ Fixed |
| RLS policy error 42501 | Supabase RLS | Database Fix | ✅ SQL Ready |
| Admin panel empty list | backendApi.js | API Fix | ✅ Fixed |

---

## Expected Behavior After Fixes:

### RM Portal (http://localhost:3000/hmr/add-salon)
- ✅ "Save as Draft" button doesn't auto-submit
- ✅ Form submits successfully without RLS errors
- ✅ Success message appears
- ✅ Redirects to dashboard

### Admin Panel (http://localhost:5173/pending-salons)
- ✅ Shows all pending salons in table
- ✅ Real-time notifications work
- ✅ Bell icon shows correct count
- ✅ Can approve/reject salons
- ✅ Toast notifications appear

### Backend (http://localhost:8000)
- ✅ POST /api/rm/vendor-requests - Returns 201 Created
- ✅ GET /api/admin/vendor-requests?status_filter=pending - Returns array
- ✅ No RLS errors in logs

---

## Troubleshooting:

### If form still auto-submits:
1. Clear browser cache
2. Hard reload (Ctrl+Shift+R)
3. Check console for errors

### If RLS error persists:
1. Verify SQL ran successfully
2. Check policies exist: `SELECT * FROM pg_policies WHERE tablename = 'vendor_join_requests'`
3. Verify user has RM profile: `SELECT * FROM rm_profiles WHERE id = auth.uid()`

### If admin panel still empty:
1. Check network tab - verify API call uses `status_filter=pending`
2. Check backend logs for errors
3. Verify admin token is valid
4. Test API directly with curl/Postman

---

**Last Updated:** November 2, 2025  
**Status:** All fixes applied and ready to test
