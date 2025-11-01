# Phase 7 - Quick Start Testing Guide

## 🚀 Quick Start (5 minutes)

### **Step 1: Start Backend**
```powershell
cd G:\vescavia\Projects\backend
python -m uvicorn main:app --reload
```
Backend will run on `http://localhost:8000`

### **Step 2: Start Frontend**
```powershell
cd G:\vescavia\Projects\salon-management-app
npm run dev
```
Frontend will run on `http://localhost:5173`

### **Step 3: Test RM Login**
1. Open browser: `http://localhost:5173/rm-login`
2. Enter RM credentials:
   - Email: (your RM user email)
   - Password: (your RM password)
3. Click "Sign In"
4. Should redirect to `/hmr/dashboard`

### **Step 4: Test Dashboard**
- Verify 4 stat cards show numbers
- Check recent submissions table
- Sidebar should show:
  - Dashboard
  - Add Salon
  - My Submissions
  - My Profile ← NEW

### **Step 5: Test Profile**
1. Click "My Profile" in sidebar
2. Verify personal info displays
3. Check score card and performance stats
4. Click "Edit Profile"
5. Update name/phone
6. Click "Save Changes"
7. Should see success toast

---

## 🔍 What Changed in Phase 7?

### **Before (Supabase):**
```javascript
// Direct Supabase query
const { data } = await supabase
  .from('agent_submissions')
  .select('*')
  .eq('agent_id', userId);
```

### **After (Backend API with JWT):**
```javascript
// Redux thunk with backend API
dispatch(fetchRMSubmissions());
// → GET /rm/vendor-requests
// → Authorization: Bearer <access_token>
```

---

## 🛠️ Troubleshooting

### **Issue: Can't login at /rm-login**
**Solution:**
1. Check backend is running on port 8000
2. Verify `VITE_BACKEND_URL=http://localhost:8000` in `.env`
3. Ensure RM user exists in database with role='rm'

### **Issue: "Invalid credentials" error**
**Solution:**
1. Verify user email and password are correct
2. Check user has `role='rm'` in backend database
3. Ensure user `is_active=true`

### **Issue: Redirects to /rm-login after successful login**
**Solution:**
1. Check browser localStorage has `access_token`
2. Verify token is valid: GET `/me` endpoint
3. Check Redux state has user with role='rm'

### **Issue: Stats cards show 0s on dashboard**
**Solution:**
1. Check backend endpoint `/rm/profile` returns data
2. Verify RM has submitted salons (check `vendor_join_requests` table)
3. Open browser console for API errors

### **Issue: "Failed to fetch profile" error**
**Solution:**
1. Verify backend is running
2. Check JWT token is valid (not expired)
3. Look at backend logs for error details
4. Ensure RM user exists in `profiles` table

---

## 📋 Quick Test Checklist

Use this for fast regression testing:

- [ ] **Login:** RM can login at `/rm-login`
- [ ] **Dashboard:** Stats and submissions display
- [ ] **Add Salon:** Form submission works
- [ ] **History:** Submissions list shows data
- [ ] **Profile:** Profile displays and can be edited
- [ ] **Navigation:** Sidebar links work
- [ ] **Protected:** Can't access without login
- [ ] **Logout:** Tokens cleared (when implemented)

---

## 🎯 Key URLs

| URL | Description |
|-----|-------------|
| `/rm-login` | RM login page |
| `/hmr/dashboard` | RM dashboard with stats |
| `/hmr/add-salon` | Submit new salon form |
| `/hmr/submissions` | View all submissions |
| `/hmr/profile` | RM profile page |

---

## 🔐 Test Users

Create these users in your database for testing:

```sql
-- RM User
INSERT INTO profiles (id, email, full_name, role, is_active)
VALUES (
  'uuid-here',
  'rm@test.com',
  'Test RM Agent',
  'rm',
  true
);

-- Admin User (for approving salons)
INSERT INTO profiles (id, email, full_name, role, is_active)
VALUES (
  'uuid-here',
  'admin@test.com',
  'Test Admin',
  'admin',
  true
);
```

---

## 💡 Pro Tips

1. **Use Browser DevTools:**
   - Check Network tab for API calls
   - Inspect localStorage for tokens
   - Look at Console for errors

2. **Backend Logs:**
   - Watch terminal for API requests
   - Check for 401/403 errors
   - Verify JWT decode logs

3. **Redux DevTools:**
   - Install Redux DevTools extension
   - Monitor state changes
   - See dispatched actions

4. **Test with Multiple Windows:**
   - Open one window as RM
   - Open another as Admin
   - Test approval workflow

---

## ✅ Success Indicators

You'll know Phase 7 is working when:

1. ✅ Can login at `/rm-login` with RM credentials
2. ✅ Dashboard shows correct stats (not all 0s)
3. ✅ Can submit new salon via form
4. ✅ Submissions appear in history
5. ✅ Can edit profile and see changes
6. ✅ Protected routes redirect to login when not authenticated
7. ✅ No console errors on any page
8. ✅ Loading spinners show during API calls
9. ✅ Toast notifications show for success/errors
10. ✅ Sidebar navigation works smoothly

---

## 🚨 Emergency Rollback

If Phase 7 breaks something, you can temporarily revert:

1. **Restore Old Routes:**
   ```javascript
   // In App.jsx, replace RMProtectedRoute with ProtectedRoute
   <Route path="/hmr/dashboard" 
     element={<ProtectedRoute allowedRoles={['hmr']}><HMRDashboard /></ProtectedRoute>} 
   />
   ```

2. **Use Supabase Directly:**
   ```javascript
   // In components, temporarily use old Supabase queries
   const { data } = await supabase.from('agent_submissions').select('*');
   ```

3. **Disable JWT:**
   - Comment out token checks in RMProtectedRoute
   - Allows testing without authentication

---

## 📞 Support

If you encounter issues:

1. Check this guide first
2. Review `PHASE_7_RM_PORTAL_MIGRATION.md` for details
3. Look at `PHASE_7_COMPLETION_SUMMARY.md` for full context
4. Check backend logs for API errors
5. Inspect browser console for frontend errors

---

**Happy Testing! 🎉**

Phase 7 is complete and ready for production testing. All RM portal features now use secure JWT authentication with backend APIs.
