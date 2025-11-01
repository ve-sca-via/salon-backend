# Phase 8 Testing Guide - Vendor Portal

**Date:** October 31, 2025  
**Status:** Ready for Testing

---

## 🧪 Testing Environment Setup

### Prerequisites
1. Backend server running on `http://localhost:8000`
2. Frontend server running on `http://localhost:5173` (or Vite port)
3. PostgreSQL database with all Phase 1-7 migrations applied
4. Razorpay test API keys configured in `.env`
5. Email service configured for registration emails

### Environment Variables
```bash
# Backend (.env)
DATABASE_URL=postgresql://user:password@localhost:5432/salon_db
SECRET_KEY=your_jwt_secret_key
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
RAZORPAY_KEY_ID=rzp_test_xxxxx
RAZORPAY_KEY_SECRET=xxxxx

# Frontend (.env)
VITE_API_URL=http://localhost:8000
VITE_RAZORPAY_KEY_ID=rzp_test_xxxxx
```

---

## 📋 Test Scenarios

### 1. Vendor Registration Flow (End-to-End)

#### Scenario: New Vendor Registration
**Steps:**
1. **Admin Approval (Admin Panel):**
   - Go to Admin Panel > Pending Salons
   - Find a vendor request
   - Click "Approve"
   - System sends email with registration link

2. **Email Verification:**
   - Check vendor's email inbox
   - Email should contain:
     * Subject: "Salon Registration Approved"
     * Registration link: `http://localhost:5173/vendor/complete-registration?token=...`
     * Salon details (name, owner name, email)
   - Click registration link

3. **Complete Registration (4 Steps):**
   
   **Step 1: Personal Information**
   - Enter Full Name: "John Doe"
   - Enter Phone: "+91 9876543210"
   - Click "Next"
   - ✅ Verify: Form advances to Step 2
   
   **Step 2: Set Password**
   - Enter Password: "Test@1234" (min 8 chars, uppercase, lowercase, number, special)
   - Enter Confirm Password: "Test@1234"
   - ✅ Verify: Password strength indicator shows "Strong"
   - Click "Next"
   - ✅ Verify: Form advances to Step 3
   
   **Step 3: Salon Details**
   - Enter Description: "Premium salon with expert stylists"
   - Business Hours (edit as needed):
     * Monday: "09:00 AM - 08:00 PM"
     * Tuesday: "09:00 AM - 08:00 PM"
     * ... (edit other days)
   - Click "Next"
   - ✅ Verify: Form advances to Step 4
   
   **Step 4: Review & Confirm**
   - ✅ Verify: All entered data displayed correctly
   - Click "Complete Registration"
   - ✅ Verify: Success toast appears
   - ✅ Verify: Redirected to `/vendor/payment` page

4. **Payment Process:**
   - ✅ Verify: Payment page shows registration fee (from config)
   - ✅ Verify: Salon info displayed correctly
   - Click "Proceed to Payment"
   - ✅ Verify: Razorpay modal opens
   - Enter test card details:
     * Card Number: 4111 1111 1111 1111
     * CVV: 123
     * Expiry: Any future date
   - Click Pay
   - ✅ Verify: Payment success message
   - ✅ Verify: Redirected to `/vendor/dashboard`
   - ✅ Verify: Salon status is "Active"

**Expected Results:**
- ✅ Registration completed successfully
- ✅ Payment verified and recorded
- ✅ Salon activated (is_active = true)
- ✅ Welcome email sent to vendor
- ✅ Vendor can access dashboard

---

### 2. Vendor Login & Authentication

#### Scenario: Successful Login
**Steps:**
1. Go to `/vendor-login`
2. Enter email: "john@salon.com"
3. Enter password: "Test@1234"
4. Click "Sign In"
5. ✅ Verify: Success toast appears
6. ✅ Verify: Redirected to `/vendor/dashboard`
7. ✅ Verify: Sidebar shows "Vendor Portal" with menu items

#### Scenario: Invalid Login
**Steps:**
1. Go to `/vendor-login`
2. Enter wrong email or password
3. Click "Sign In"
4. ✅ Verify: Error toast appears with message
5. ✅ Verify: User stays on login page

#### Scenario: Non-Vendor User Login
**Steps:**
1. Go to `/vendor-login`
2. Enter customer/RM credentials
3. Click "Sign In"
4. ✅ Verify: Error toast: "Access denied. Vendor credentials required."
5. ✅ Verify: User stays on login page

---

### 3. Dashboard & Analytics

#### Scenario: View Dashboard
**Steps:**
1. Login as vendor
2. ✅ Verify: Dashboard displays 6 stat cards:
   - Total Revenue (with ₹ symbol)
   - Bookings Today
   - Active Services
   - Staff Members
   - Pending Bookings
   - Completed Bookings
3. ✅ Verify: Quick actions section with 3 buttons
4. ✅ Verify: Recent bookings table (if bookings exist)
5. ✅ Verify: All data loads without errors

---

### 4. Salon Profile Management

#### Scenario: View Profile
**Steps:**
1. Go to `/vendor/profile`
2. ✅ Verify: Profile data loaded and displayed
3. ✅ Verify: Status banner shows correct salon status
4. ✅ Verify: Quick stats sidebar shows payment/account status

#### Scenario: Edit Profile
**Steps:**
1. On profile page, click "Edit Profile"
2. ✅ Verify: Form fields become editable
3. ✅ Verify: "Cancel" and "Save Changes" buttons appear
4. Update fields:
   - Name: "Premium Hair Salon"
   - Phone: "+91 9876543211"
   - Address: "123 Main Street"
   - City: "Mumbai"
   - State: "Maharashtra"
   - Pincode: "400001"
   - Description: "Updated description"
5. Update business hours:
   - Monday: "10:00 AM - 09:00 PM"
6. Click "Save Changes"
7. ✅ Verify: Success toast appears
8. ✅ Verify: Edit mode disabled
9. ✅ Verify: Updated data displayed

#### Scenario: Cancel Edit
**Steps:**
1. Click "Edit Profile"
2. Make some changes
3. Click "Cancel"
4. ✅ Verify: Original data restored
5. ✅ Verify: Edit mode disabled

---

### 5. Services Management

#### Scenario: Add Service
**Steps:**
1. Go to `/vendor/services`
2. Click "Add Service"
3. ✅ Verify: Modal opens with form
4. Fill form:
   - Name: "Haircut & Styling"
   - Category: "Hair"
   - Description: "Professional haircut with styling"
   - Price: "500"
   - Duration: "45"
   - Active: Checked
5. Click "Add Service"
6. ✅ Verify: Success toast appears
7. ✅ Verify: Modal closes
8. ✅ Verify: New service card appears in grid
9. ✅ Verify: Service details correct

#### Scenario: Add FREE Service
**Steps:**
1. Click "Add Service"
2. Fill form with Price: "0"
3. Submit form
4. ✅ Verify: Service created with "FREE" label
5. ✅ Verify: Price shows "FREE" instead of "₹0"

#### Scenario: Edit Service
**Steps:**
1. On services page, find a service card
2. Click "Edit" button
3. ✅ Verify: Modal opens with existing data
4. Update fields:
   - Price: "600"
   - Duration: "60"
5. Click "Update Service"
6. ✅ Verify: Success toast appears
7. ✅ Verify: Service card shows updated data

#### Scenario: Toggle Service Active/Inactive
**Steps:**
1. Find a service card
2. Click toggle icon (top right)
3. ✅ Verify: Status changes (green/gray)
4. ✅ Verify: Success toast appears
5. ✅ Verify: Badge shows new status
6. Click toggle again
7. ✅ Verify: Status reverts

#### Scenario: Delete Service
**Steps:**
1. Find a service card
2. Click trash icon
3. ✅ Verify: Confirmation dialog appears
4. Click "OK"
5. ✅ Verify: Success toast appears
6. ✅ Verify: Service card removed from grid

#### Scenario: Search Services
**Steps:**
1. Create multiple services with different names
2. Type search term in search box
3. ✅ Verify: Only matching services displayed
4. Clear search
5. ✅ Verify: All services displayed again

#### Scenario: Filter Services
**Steps:**
1. Create active and inactive services
2. Click "Active" filter button
3. ✅ Verify: Only active services shown
4. Click "Inactive" filter
5. ✅ Verify: Only inactive services shown
6. Click "All" filter
7. ✅ Verify: All services shown

---

### 6. Staff Management

#### Scenario: Add Staff Member
**Steps:**
1. Go to `/vendor/staff`
2. Click "Add Staff Member"
3. ✅ Verify: Large modal opens with form
4. Fill basic info:
   - Name: "Sarah Johnson"
   - Email: "sarah@salon.com"
   - Phone: "+91 9876543220"
   - Specialization: "Hair Stylist"
5. Select services:
   - Check "Haircut & Styling"
   - Check "Hair Coloring"
6. Set availability:
   - Monday: Check available, 09:00 - 18:00
   - Tuesday: Check available, 09:00 - 18:00
   - ... (set other days)
   - Sunday: Uncheck available
7. Active: Checked
8. Click "Add Staff Member"
9. ✅ Verify: Success toast appears
10. ✅ Verify: Modal closes
11. ✅ Verify: New staff card appears
12. ✅ Verify: Assigned services shown as badges

#### Scenario: Edit Staff
**Steps:**
1. Find staff card
2. Click "Edit" button
3. ✅ Verify: Modal opens with existing data
4. Update specialization: "Senior Hair Stylist"
5. Add more services
6. Update availability times
7. Click "Update Staff Member"
8. ✅ Verify: Success toast appears
9. ✅ Verify: Card shows updated data

#### Scenario: Delete Staff
**Steps:**
1. Find staff card
2. Click trash icon
3. ✅ Verify: Confirmation dialog appears
4. Click "OK"
5. ✅ Verify: Success toast appears
6. ✅ Verify: Staff card removed

#### Scenario: Search & Filter Staff
**Steps:**
1. Create multiple staff members
2. Test search by name
3. ✅ Verify: Matching staff displayed
4. Test active/inactive filters
5. ✅ Verify: Filters work correctly

---

### 7. Bookings Management

#### Scenario: View Bookings
**Steps:**
1. Go to `/vendor/bookings`
2. ✅ Verify: 6 stat cards display correctly
3. ✅ Verify: Bookings table loads
4. ✅ Verify: Each booking row shows:
   - Booking ID
   - Customer name & phone
   - Service name
   - Staff name
   - Date & time
   - Amount
   - Status badge

#### Scenario: View Booking Details
**Steps:**
1. On bookings page, find a booking
2. Click "View Details"
3. ✅ Verify: Modal opens with full booking details
4. ✅ Verify: All information displayed correctly
5. ✅ Verify: Action buttons available (based on status)

#### Scenario: Confirm Pending Booking
**Steps:**
1. Find a pending booking
2. Click "View Details"
3. Click "Confirm Booking"
4. ✅ Verify: Success toast appears
5. ✅ Verify: Modal closes
6. ✅ Verify: Booking status updated to "Confirmed"
7. ✅ Verify: Status badge color changed to blue
8. ✅ Verify: Stats cards updated

#### Scenario: Complete Confirmed Booking
**Steps:**
1. Find a confirmed booking
2. Click "View Details"
3. Click "Mark as Completed"
4. ✅ Verify: Success toast appears
5. ✅ Verify: Status updated to "Completed"
6. ✅ Verify: Revenue stats updated

#### Scenario: Cancel Booking
**Steps:**
1. Find pending/confirmed booking
2. Click "View Details"
3. Click "Cancel Booking"
4. ✅ Verify: Success toast appears
5. ✅ Verify: Status updated to "Cancelled"
6. ✅ Verify: Status badge red

#### Scenario: Filter by Status
**Steps:**
1. Create bookings with different statuses
2. Click "Pending" filter
3. ✅ Verify: Only pending bookings shown
4. Test other status filters
5. ✅ Verify: Each filter works correctly

#### Scenario: Filter by Date
**Steps:**
1. Create bookings with different dates
2. Click "Today" filter
3. ✅ Verify: Only today's bookings shown
4. Click "Upcoming"
5. ✅ Verify: Future bookings shown
6. Click "Past"
7. ✅ Verify: Past bookings shown

#### Scenario: Search Bookings
**Steps:**
1. Enter customer name in search
2. ✅ Verify: Matching bookings shown
3. Search by service name
4. ✅ Verify: Results filtered correctly
5. Search by staff name
6. ✅ Verify: Results filtered correctly

---

### 8. Navigation & Routes

#### Scenario: Sidebar Navigation
**Steps:**
1. Login as vendor
2. Click each sidebar menu item:
   - Dashboard → `/vendor/dashboard`
   - My Profile → `/vendor/profile`
   - Services → `/vendor/services`
   - Staff → `/vendor/staff`
   - Bookings → `/vendor/bookings`
3. ✅ Verify: Each route loads correctly
4. ✅ Verify: Active menu item highlighted

#### Scenario: Protected Routes
**Steps:**
1. Logout
2. Try accessing `/vendor/dashboard` directly
3. ✅ Verify: Redirected to `/vendor-login`
4. Login as customer
5. Try accessing `/vendor/dashboard`
6. ✅ Verify: Access denied

---

### 9. Error Handling

#### Scenario: Network Errors
**Steps:**
1. Stop backend server
2. Try any operation (add service, update profile, etc.)
3. ✅ Verify: Error toast appears with message
4. ✅ Verify: Loading spinner stops
5. ✅ Verify: UI remains functional

#### Scenario: Invalid Token
**Steps:**
1. Access registration link with invalid token
2. ✅ Verify: Error message displayed
3. ✅ Verify: Form disabled

#### Scenario: Payment Failure
**Steps:**
1. During payment, use test card that fails
2. ✅ Verify: Error message shown
3. ✅ Verify: Option to retry available

---

### 10. Responsive Design

#### Scenario: Mobile View
**Steps:**
1. Resize browser to mobile width (375px)
2. Test all pages:
   - Dashboard
   - Profile
   - Services
   - Staff
   - Bookings
3. ✅ Verify: Layout adapts correctly
4. ✅ Verify: All buttons accessible
5. ✅ Verify: Forms usable
6. ✅ Verify: Tables scroll horizontally if needed

#### Scenario: Tablet View
**Steps:**
1. Resize to tablet width (768px)
2. Test all pages
3. ✅ Verify: Grid layouts adjust appropriately
4. ✅ Verify: Navigation works smoothly

---

## 🐛 Common Issues & Solutions

### Issue: "Invalid credentials" on login
**Solution:** 
- Verify user exists in database
- Check role is 'vendor'
- Verify password is correct
- Check JWT_SECRET_KEY matches

### Issue: Payment modal not opening
**Solution:**
- Check Razorpay script loaded (dev console)
- Verify VITE_RAZORPAY_KEY_ID in .env
- Check browser console for errors

### Issue: Services/Staff not loading
**Solution:**
- Check backend logs for errors
- Verify JWT token in localStorage
- Check API endpoints returning data
- Verify salon_id associated with vendor

### Issue: Profile update fails
**Solution:**
- Check required fields filled
- Verify API endpoint accessible
- Check backend validation rules

---

## ✅ Final Checklist

Before marking Phase 8 as complete:

### Functionality
- [ ] Vendor can register via email link
- [ ] Payment integration works
- [ ] Vendor can login
- [ ] Dashboard displays stats
- [ ] Profile can be viewed/edited
- [ ] Services CRUD works
- [ ] Staff CRUD works
- [ ] Bookings management works
- [ ] All filters functional
- [ ] Search works across pages

### Security
- [ ] JWT authentication working
- [ ] Role validation enforced
- [ ] Protected routes secured
- [ ] Payment verification secure
- [ ] Tokens stored safely

### UX/UI
- [ ] All pages load without errors
- [ ] Loading states visible
- [ ] Success/error toasts appear
- [ ] Responsive on mobile/tablet
- [ ] Navigation intuitive
- [ ] Forms validate properly

### Performance
- [ ] Pages load quickly
- [ ] No memory leaks
- [ ] API calls optimized
- [ ] Images load efficiently

---

## 📊 Test Results Template

```markdown
# Phase 8 Test Results - [Date]

## Tester: [Name]
## Environment: [Dev/Staging/Prod]

### Test Summary
- Total Tests: XX
- Passed: XX
- Failed: XX
- Blocked: XX

### Critical Issues
1. [Issue description]
2. [Issue description]

### Minor Issues
1. [Issue description]
2. [Issue description]

### Recommendations
1. [Recommendation]
2. [Recommendation]

### Sign-off
Phase 8 is ready for production: [ ] Yes [ ] No

Reason if No: _______________
```

---

**Happy Testing! 🧪**
