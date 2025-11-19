# 🧪 Complete API Testing Guide

## Overview
This guide will help you test your entire salon management backend API flow without needing to seed data manually. We'll use Postman to create test data as we go and verify the complete user journey.

---

## 📦 Setup Instructions

### 1. Import Postman Collection

1. Open Postman
2. Click **Import** button
3. Select the file: `Salon_API_Postman_Collection.json`
4. The collection will be imported with all endpoints organized by modules

### 2. Configure Environment Variables

The collection uses variables that are automatically set during testing:

**Base Variables** (Set manually):
- `base_url`: `http://localhost:8000/api/v1` (or your server URL)

**Auto-Set Variables** (automatically populated by test scripts):
- `access_token` - Current user's access token
- `admin_token` - Admin user's token
- `vendor_token` - Vendor user's token  
- `rm_token` - Relationship Manager's token
- `customer_token` - Customer user's token
- `user_id` - Current user ID
- `salon_id` - Test salon ID
- `booking_id` - Test booking ID
- `service_id` - Test service ID
- `staff_id` - Test staff ID
- `order_id` - Payment order ID

---

## 🎯 Testing Flow Scenarios

### Scenario 1: Complete Customer Journey (No Seeding Required)

This flow tests the entire customer experience from signup to booking completion.

#### Step 1: Start Your Backend Server

```powershell
cd g:\vescavia\Projects\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Or use your existing script:
```powershell
.\run-local.ps1
```

#### Step 2: Create Test Accounts

Run these endpoints in order:

1. **POST** `1. Authentication > Signup - Customer`
   - Creates a customer account
   - Auto-saves `customer_token`
   
2. **POST** `1. Authentication > Signup - Admin`
   - Creates an admin account
   - Auto-saves `admin_token`

3. **POST** `1. Authentication > Signup - RM`
   - Creates an RM account
   - Auto-saves `rm_token`

#### Step 3: Admin Creates Services

Using the `admin_token`:

4. **POST** `6. Admin Panel > Services Management > Create Service`
   - Create a service (e.g., "Hair Cut")
   - Repeat to create multiple services:
     - Hair Styling
     - Facial
     - Manicure
   - `service_id` is auto-saved from first service

#### Step 4: Create a Salon (As Vendor/Admin)

5. **POST** `2. Salons - Public > POST /salons/` (requires vendor/admin token)
   
**Sample Body:**
```json
{
  "name": "Luxury Hair Salon",
  "email": "luxury@salon.com",
  "phone": "+919876543220",
  "address": "Connaught Place, New Delhi",
  "city": "Delhi",
  "state": "Delhi",
  "pincode": "110001",
  "latitude": 28.6139,
  "longitude": 77.2090,
  "description": "Premium salon services",
  "opening_time": "09:00",
  "closing_time": "21:00",
  "services_offered": ["Hair Cut", "Hair Styling", "Facial"],
  "amenities": ["WiFi", "AC", "Parking"]
}
```
- `salon_id` is auto-saved

#### Step 5: Get Salon Data

6. **GET** `2. Salons - Public > Get All Salons (Public)`
   - Verify salon appears in listing
   - Confirms `salon_id`

7. **GET** `2. Salons - Public > Get Salon Services`
   - Fetches services for the salon
   - Auto-saves `service_id`

8. **GET** `2. Salons - Public > Get Salon Staff`
   - Fetches staff (if any)
   - Auto-saves `staff_id`

#### Step 6: Check Available Slots

9. **GET** `2. Salons - Public > Get Available Slots`
   - Check what times are available
   - Update the `date` parameter to a future date

#### Step 7: Create a Booking (As Customer)

Using the `customer_token`:

10. **POST** `3. Bookings - Customer > Create Booking`

**Sample Body:**
```json
{
  "salon_id": "{{salon_id}}",
  "service_id": "{{service_id}}",
  "booking_date": "2025-11-25",
  "booking_time": "14:00",
  "staff_id": "{{staff_id}}",
  "notes": "First time customer"
}
```
- `booking_id` is auto-saved

#### Step 8: Payment Flow

11. **POST** `5. Payments > Create Booking Payment Order`
    - Creates Razorpay order
    - Auto-saves `order_id`

12. **POST** `5. Payments > Verify Booking Payment`
    - Verifies payment (use test payment IDs)

#### Step 9: View Booking Details

13. **GET** `3. Bookings - Customer > Get My Bookings`
    - See all customer bookings

14. **GET** `3. Bookings - Customer > Get Booking Details`
    - View specific booking details

#### Step 10: Customer Portal Features

15. **POST** `4. Customer Portal > Favorites > Add to Favorites`
    - Add salon to favorites

16. **GET** `4. Customer Portal > Favorites > Get Favorites`
    - View favorite salons

17. **POST** `4. Customer Portal > Reviews > Submit Review`
    - Submit a review for the salon

---

### Scenario 2: Admin Operations Flow

Test admin panel functionality:

#### Step 1: Admin Login

1. **POST** `1. Authentication > Login - Admin`
   - Use admin credentials
   - Token auto-saved

#### Step 2: Dashboard & Analytics

2. **GET** `6. Admin Panel > Dashboard > Get Dashboard Stats`
   - View overall platform statistics

#### Step 3: Manage Salons

3. **GET** `6. Admin Panel > Salons Management > Get All Salons`
   - View all registered salons

4. **PUT** `6. Admin Panel > Salons Management > Toggle Salon Status`
   - Activate/deactivate salon

#### Step 4: Manage Bookings

5. **GET** `6. Admin Panel > Bookings Management > Get All Bookings`
   - View all platform bookings

6. **PUT** `6. Admin Panel > Bookings Management > Update Booking Status`
   - Change booking status (confirmed, completed, etc.)

#### Step 5: System Configuration

7. **GET** `6. Admin Panel > System Config > Get All Config`
   - View system settings

8. **PUT** `6. Admin Panel > System Config > Update Config`
   - Update booking fee percentage, etc.

---

### Scenario 3: RM (Relationship Manager) Flow

Test RM dashboard and vendor management:

#### Step 1: RM Login

1. **POST** `1. Authentication > Login - RM` (if not already logged in)

#### Step 2: RM Dashboard

2. **GET** `7. RM Portal > Get RM Dashboard`
   - View personal metrics

3. **GET** `7. RM Portal > Get Leaderboard`
   - See RM rankings

#### Step 3: Manage Vendors

4. **GET** `7. RM Portal > Get Vendor Requests`
   - View pending vendor join requests

5. **GET** `7. RM Portal > Get My Salons`
   - View salons assigned to this RM

---

### Scenario 4: Vendor Operations

Test vendor salon management:

#### Step 1: Vendor Login/Registration

1. Complete vendor registration flow
2. Login as vendor

#### Step 2: Vendor Dashboard

3. **GET** `8. Vendors > Get Vendor Dashboard`
   - View sales, bookings, analytics

#### Step 3: Manage Salon

4. **GET** `8. Vendors > Get My Salons`
   - View owned salons

5. **GET** `8. Vendors > Get Salon Bookings`
   - View bookings for specific salon

---

## 🔄 Common Testing Workflows

### Testing the Cart System

1. Login as customer
2. **POST** `4. Customer Portal > Cart > Add to Cart` (multiple times)
3. **GET** `4. Customer Portal > Cart > Get Cart`
4. **POST** `4. Customer Portal > Cart > Checkout Cart`
5. Complete payment flow

### Testing Location Services

1. **POST** `9. Location Services > Geocode Address`
   - Convert address to coordinates
   
2. **GET** `9. Location Services > Reverse Geocode`
   - Convert coordinates to address

3. **GET** `9. Location Services > Get Nearby Salons`
   - Find salons near coordinates

### Testing Search

1. **GET** `2. Salons - Public > Search Nearby Salons`
   - Search by location

2. **GET** `2. Salons - Public > Search Salons by Query`
   - Search by keywords, city, etc.

---

## 🐛 Troubleshooting

### Common Issues

**❌ "Unauthorized" Error**
- Check that token is set correctly
- Re-login to refresh token
- Ensure you're using the right token for the role (admin_token, customer_token, etc.)

**❌ "Salon not found"**
- Ensure you've created a salon first
- Check that `salon_id` variable is set
- Verify salon is active

**❌ "Service not found"**
- Create services via admin panel first
- Check `service_id` variable is set

**❌ "Invalid booking time"**
- Use future dates
- Check salon opening hours
- Ensure time slot is available

**❌ Database errors**
- Check Supabase connection
- Verify database tables exist
- Check environment variables

### Checking Logs

Monitor your terminal running the backend to see detailed logs:
```
INFO:     → POST /api/v1/auth/login - 127.0.0.1
INFO:     200 OK - Processed in 0.15s
```

---

## 📊 Test Data Quick Reference

### Sample User Accounts

| Role | Email | Password |
|------|-------|----------|
| Customer | customer@test.com | Password123! |
| Admin | admin@salon.com | Admin123! |
| RM | rm@salon.com | RM123456! |

### Sample Salon Data

```json
{
  "name": "Elite Beauty Parlour",
  "email": "elite@beauty.com",
  "phone": "+919876543230",
  "address": "Saket, New Delhi",
  "city": "Delhi",
  "latitude": 28.5244,
  "longitude": 77.2066,
  "opening_time": "10:00",
  "closing_time": "20:00"
}
```

### Sample Service Data

```json
{
  "name": "Premium Haircut",
  "description": "Professional styling by expert stylists",
  "category": "Hair",
  "duration_minutes": 45,
  "price": 800
}
```

---

## ✅ Complete Test Checklist

Use this checklist to ensure you've tested all major functionality:

### Authentication
- [ ] Customer signup
- [ ] Admin signup
- [ ] RM signup
- [ ] Login (all roles)
- [ ] Get current user
- [ ] Refresh token
- [ ] Logout

### Salon Management
- [ ] Create salon
- [ ] List all salons
- [ ] Get salon details
- [ ] Search salons (nearby & query)
- [ ] Get salon services
- [ ] Get salon staff
- [ ] Get available slots

### Bookings
- [ ] Create booking
- [ ] Get booking details
- [ ] List user bookings
- [ ] Cancel booking
- [ ] Complete booking

### Payments
- [ ] Create order
- [ ] Verify payment
- [ ] Get payment history

### Customer Features
- [ ] Cart (add, view, clear, checkout)
- [ ] Favorites (add, view, remove)
- [ ] Reviews (submit, view)

### Admin Panel
- [ ] Dashboard stats
- [ ] Manage salons
- [ ] Manage services
- [ ] Manage bookings
- [ ] System config

### RM Portal
- [ ] Dashboard
- [ ] Vendor requests
- [ ] My salons
- [ ] Leaderboard

### Vendor Portal
- [ ] Dashboard
- [ ] My salons
- [ ] Salon bookings

---

## 🎓 Advanced Testing Tips

### 1. Using Postman Collection Runner

Run entire test suites automatically:
1. Click on collection name
2. Click "Run collection"
3. Select scenarios to run
4. View automated test results

### 2. Environment Switching

Create multiple environments for different backends:
- Local Development: `http://localhost:8000/api/v1`
- Staging: `https://staging-api.yourdomain.com/api/v1`
- Production: `https://api.yourdomain.com/api/v1`

### 3. Pre-request Scripts

The collection includes scripts that:
- Auto-save tokens
- Auto-save IDs
- Chain requests together

### 4. Test Assertions

Add test scripts to validate responses:
```javascript
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

pm.test("Response has booking_id", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.booking_id).to.exist;
});
```

---

## 📝 Notes

- All timestamps should be in future dates when creating bookings
- Use proper phone format: `+91XXXXXXXXXX`
- Coordinates should be valid (latitude: -90 to 90, longitude: -180 to 180)
- Some endpoints require specific roles (admin, vendor, rm, customer)
- Rate limiting is enabled (check limits in config)

---

## 🚀 Next Steps

After testing with Postman:

1. **Frontend Integration**: Use these same endpoints in your React apps
2. **Automated Tests**: Convert Postman tests to pytest tests
3. **Load Testing**: Use tools like k6 or Apache Bench
4. **Documentation**: Generate OpenAPI docs from your FastAPI app

---

## 🆘 Getting Help

If you encounter issues:

1. Check backend logs in terminal
2. Verify Supabase connection
3. Check environment variables in `.env`
4. Review API response error messages
5. Ensure database tables are properly set up

---

**Happy Testing! 🎉**
