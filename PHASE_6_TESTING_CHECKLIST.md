# Phase 6 Testing Checklist

## Prerequisites
- [ ] Backend running on http://localhost:8000
- [ ] Admin panel running on http://localhost:5174
- [ ] Environment variables configured in both projects
- [ ] At least one admin user exists in database

## 1. Login & Authentication

### Test Login
- [ ] Navigate to http://localhost:5174/login
- [ ] Enter admin credentials
- [ ] Click "Sign In"
- [ ] **Expected**: Redirected to /dashboard
- [ ] **Expected**: See "Welcome back, [Name]" in header
- [ ] **Expected**: localStorage has 'access_token' and 'refresh_token'

### Test Invalid Login
- [ ] Enter wrong password
- [ ] Click "Sign In"
- [ ] **Expected**: Error toast "Invalid credentials"
- [ ] **Expected**: No redirect

### Test Non-Admin Login
- [ ] Login with customer/vendor/rm account
- [ ] **Expected**: Error "Only admins can access this panel"
- [ ] **Expected**: No redirect

## 2. Dashboard

### Load Dashboard
- [ ] After login, should see dashboard automatically
- [ ] **Expected**: All 7 stat cards visible:
  - Pending Requests (yellow)
  - Total Salons (blue)
  - Active Salons (green)
  - Total Revenue (purple)
  - Total RMs (indigo)
  - Today's Bookings (pink)
  - Total Bookings (cyan)

### Verify Stats
- [ ] Check if numbers match database reality
- [ ] **Expected**: Pending Requests shows actual pending count
- [ ] **Expected**: Total Salons shows all salons count
- [ ] **Expected**: Revenue shows correct amount with ₹ symbol

### Quick Actions
- [ ] Click "Pending Approvals" button
- [ ] **Expected**: Navigate to /pending-salons
- [ ] Go back, click "Manage RMs" button
- [ ] **Expected**: Navigate to /rm-management
- [ ] Go back, click "System Settings" button
- [ ] **Expected**: Navigate to /system-config

## 3. System Configuration

### Load Configurations
- [ ] Navigate to System Config page
- [ ] **Expected**: See 3 categories:
  - Payments (fees)
  - RM Scoring (score settings)
  - Limits (free services, staff)
- [ ] **Expected**: Each config has current value and description

### Update Configuration
- [ ] Click "Edit" on any configuration
- [ ] Change value (e.g., registration_fee_amount to 5000)
- [ ] Click "Save"
- [ ] **Expected**: Success toast "Configuration updated successfully"
- [ ] **Expected**: Page refreshes with new value

### Validation
- [ ] Try entering negative number for fee
- [ ] Try entering text instead of number
- [ ] **Expected**: Proper validation error messages

## 4. Pending Salons (Critical!)

### View Pending Requests
- [ ] Navigate to Pending Salons page
- [ ] **Expected**: See list of pending salon submissions
- [ ] **Expected**: Each row shows:
  - Salon name
  - Owner email
  - RM name
  - Submitted date
  - Action buttons (Review, Reject)

### Review Salon Details
- [ ] Click "Review" on any pending salon
- [ ] **Expected**: Modal opens with full details:
  - Salon information (name, address, location)
  - Owner details (name, email, phone)
  - RM information
  - Submission timestamp

### Approve Salon
- [ ] In review modal, click "Approve"
- [ ] **Expected**: Confirmation modal appears
- [ ] Click "Yes, Approve"
- [ ] **Expected**: Success toast "Salon approved! Registration email sent"
- [ ] **Expected**: Salon removed from pending list
- [ ] **Expected**: Check email inbox - registration email received by owner
- [ ] **Expected**: Email contains registration link with JWT token

### Reject Salon
- [ ] Click "Reject" on another pending salon
- [ ] **Expected**: Rejection reason modal opens
- [ ] Leave reason empty, click "Reject"
- [ ] **Expected**: Error toast "Please provide a rejection reason"
- [ ] Enter reason (e.g., "Incomplete documentation")
- [ ] Click "Reject"
- [ ] **Expected**: Success toast "Salon rejected"
- [ ] **Expected**: Salon removed from pending list
- [ ] **Expected**: RM receives rejection email with reason

### Email Verification
- [ ] Check owner email for approval email
- [ ] **Expected**: Subject: "Salon Approved - Complete Your Registration"
- [ ] **Expected**: Email contains salon name
- [ ] **Expected**: Registration link with token parameter
- [ ] Check RM email for rejection email
- [ ] **Expected**: Subject: "Salon Submission Update"
- [ ] **Expected**: Email contains rejection reason

## 5. RM Management

### View RM List
- [ ] Navigate to RM Management page
- [ ] **Expected**: See table of all RMs
- [ ] **Expected**: Each row shows:
  - RM name, email, phone
  - Current score (points)
  - Performance metrics (Total/Approved/Pending salons)
  - "View Details" button

### Sort & Search
- [ ] Click on "Current Score" header to sort
- [ ] **Expected**: RMs sorted by score (highest first)
- [ ] Use search box to find specific RM
- [ ] **Expected**: Filtered results

### View RM Details
- [ ] Click "View Details" on any RM
- [ ] **Expected**: Modal opens with:
  - RM profile information
  - Current score and total salons
  - Score history table showing:
    - Date earned
    - Points earned
    - Description (e.g., "Salon approval")
    - Salon name (if applicable)

### Verify Score Calculation
- [ ] Check RM with approved salons
- [ ] **Expected**: Score = (approved_count × score_per_approval)
- [ ] Example: 5 approved salons × 10 points = 50 points

## 6. Protected Routes & Session

### Token Refresh
- [ ] Login and wait 30+ minutes (or manually expire token)
- [ ] Navigate to any page
- [ ] **Expected**: Token auto-refreshes in background
- [ ] **Expected**: No redirect to login
- [ ] **Expected**: Request succeeds

### Manual Logout
- [ ] Click user avatar in header
- [ ] Click "Logout"
- [ ] **Expected**: Redirected to /login
- [ ] **Expected**: localStorage cleared (no tokens)
- [ ] Try to access /dashboard directly
- [ ] **Expected**: Redirected back to /login

### Session Expiration
- [ ] Login and remove access_token from localStorage
- [ ] Navigate to any page
- [ ] **Expected**: Redirected to /login
- [ ] **Expected**: "Please login again" message

## 7. Error Handling

### Backend Down
- [ ] Stop backend server
- [ ] Try to login or load dashboard
- [ ] **Expected**: Error toast "Network error" or "Failed to connect"

### Invalid Token
- [ ] Login successfully
- [ ] Manually edit access_token in localStorage to invalid value
- [ ] Refresh page
- [ ] **Expected**: Redirected to login with error message

### Network Issues
- [ ] Disable network temporarily
- [ ] Try to perform any action
- [ ] **Expected**: Error toast with clear message
- [ ] Re-enable network
- [ ] **Expected**: Retry succeeds

## 8. Performance & UX

### Load Times
- [ ] Dashboard loads within 1 second
- [ ] Pending salons loads within 1 second
- [ ] RM management loads within 1 second
- [ ] System config loads within 1 second

### Smooth Interactions
- [ ] Modals open/close smoothly
- [ ] Buttons show loading state when processing
- [ ] Toast notifications appear and disappear automatically
- [ ] No console errors in browser DevTools

### Mobile Responsiveness
- [ ] Open admin panel on mobile device or resize browser
- [ ] **Expected**: Layout adapts to mobile screen
- [ ] **Expected**: Stats cards stack vertically
- [ ] **Expected**: Tables become scrollable
- [ ] **Expected**: All buttons accessible

## 9. Security Checks

### Role Validation
- [ ] Login as admin
- [ ] Check localStorage - should have access_token
- [ ] Decode JWT token at https://jwt.io
- [ ] **Expected**: Payload contains `"role": "admin"`

### API Authorization
- [ ] Open browser DevTools → Network tab
- [ ] Perform any action (e.g., load dashboard)
- [ ] Check API request headers
- [ ] **Expected**: Authorization header: `Bearer eyJhbG...`
- [ ] **Expected**: No Supabase API key in requests

### Protected Endpoints
- [ ] Try to access admin endpoints without token
- [ ] Use curl or Postman:
  ```bash
  curl http://localhost:8000/admin/dashboard/stats
  ```
- [ ] **Expected**: 401 Unauthorized response
- [ ] **Expected**: Error: "Not authenticated"

## 10. Complete Workflow Test

### End-to-End Vendor Approval
1. **RM Submits Salon**:
   - [ ] Use RM account to submit new salon
   - [ ] **Expected**: Appears in pending list

2. **Admin Reviews**:
   - [ ] Login as admin
   - [ ] Navigate to Pending Salons
   - [ ] Click "Review" on new submission
   - [ ] **Expected**: All details visible

3. **Admin Approves**:
   - [ ] Click "Approve"
   - [ ] **Expected**: Success toast
   - [ ] **Expected**: Email sent to owner

4. **Owner Registers**:
   - [ ] Check owner email
   - [ ] Click registration link
   - [ ] Complete registration form
   - [ ] **Expected**: Vendor account created
   - [ ] **Expected**: Can login as vendor

5. **RM Score Updated**:
   - [ ] Go back to RM Management
   - [ ] Find the RM who submitted salon
   - [ ] **Expected**: Score increased by 10 points
   - [ ] **Expected**: Approved salons count increased

## 11. Browser Compatibility

### Test in Chrome
- [ ] All features work correctly

### Test in Firefox
- [ ] All features work correctly

### Test in Safari
- [ ] All features work correctly

### Test in Edge
- [ ] All features work correctly

## 12. Final Verification

### Code Quality
- [ ] No console errors in browser DevTools
- [ ] No linting errors in VS Code
- [ ] No TypeScript/JSX errors
- [ ] All imports resolved correctly

### Data Integrity
- [ ] Check database after approval
- [ ] **Expected**: Salon record created
- [ ] **Expected**: Vendor request status = 'approved'
- [ ] **Expected**: RM score updated
- [ ] **Expected**: Admin notes saved

### Logs Review
- [ ] Check backend logs for any errors
- [ ] **Expected**: Clean logs with successful operations
- [ ] **Expected**: JWT verification logs present
- [ ] **Expected**: Email sending logs present

---

## Issue Tracking

### Found Issues
| # | Page | Issue | Severity | Status |
|---|------|-------|----------|--------|
| 1 | | | | |
| 2 | | | | |

### Notes
- Document any unexpected behavior
- Note any performance issues
- Record any UI/UX improvements needed

---

## Sign-Off

**Tester**: ___________________  
**Date**: ___________________  
**Result**: ☐ Pass  ☐ Fail  ☐ Pass with Issues  

**Comments**:
_________________________________________________________________
_________________________________________________________________
