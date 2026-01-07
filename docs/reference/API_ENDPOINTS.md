# API Endpoints Reference

**Last Updated:** December 11, 2025  
**Total Endpoints:** 138  
**Base URL:** `http://localhost:8000/api/v1` (local) | `https://your-domain.com/api/v1` (production)

---

## 📊 Endpoint Count by Module

| Module | Count | Description |
|--------|-------|-------------|
| Auth | 8 | Login, Signup, Logout, Password Reset |
| Admin | 40+ | Dashboard, Users, Salons, RMs, Config, Vendor Requests |
| Customers | 19 | Cart, Bookings, Favorites, Reviews, Salons |
| Vendors | 17 | Dashboard, Salon, Services, Staff, Bookings, Analytics |
| RM (Relationship Manager) | 13 | Dashboard, Vendor Requests, Salons, Profile, Scoring |
| Salons (Public) | 11 | Browse, Search, Details, Services, Staff, Slots |
| Bookings | 8 | CRUD operations, Status management |
| Payments | 8 | Razorpay Orders, Verification, History, Earnings |
| Careers | 5 | Applications, Review, Download Documents |
| Upload | 3 | Single/Multiple Image Upload, Delete |
| Location | 3 | Geocoding, Reverse Geocoding, Nearby Salons |
| Realtime | 4 | WebSocket subscriptions for live updates |
| Test Email | 2 | Dev/Staging only - Send test emails |

---

## 🔐 Authentication Endpoints (8)

All return JWT tokens + user profile.

```
POST   /auth/login                  # Email/password login
POST   /auth/signup                 # User registration
POST   /auth/refresh                # Refresh access token
GET    /auth/me                     # Get current user profile
POST   /auth/logout                 # Logout (blacklist token)
POST   /auth/logout-all             # Logout from all devices
POST   /auth/password-reset         # Request password reset
POST   /auth/password-reset/confirm # Confirm password reset
```

**Rate Limits:**
- Login: 5 requests/minute
- Signup: 3 requests/minute
- Password Reset: 3 requests/minute

---

## 👨‍💼 Admin Endpoints (40+)

Requires `admin` role.

### Dashboard (2)
```
GET    /admin/stats              # Platform statistics
GET    /admin/recent-activity    # Recent system activity
```

### User Management (4)
```
GET    /admin/users              # List all users
POST   /admin/users              # Create user
PUT    /admin/users/{user_id}    # Update user
DELETE /admin/users/{user_id}    # Delete user
```

### Salon Management (4)
```
GET    /admin/salons             # List all salons
PUT    /admin/salons/{salon_id}  # Update salon
DELETE /admin/salons/{salon_id}  # Delete salon
PUT    /admin/salons/{salon_id}/status  # Toggle active status
```

### Service Management (5)
```
GET    /admin/services              # List all services
GET    /admin/services/{service_id} # Get service details
POST   /admin/services              # Create service
PUT    /admin/services/{service_id} # Update service
DELETE /admin/services/{service_id} # Delete service
```

### Staff Management (5)
```
GET    /admin/staff                # List all staff
GET    /admin/staff/{staff_id}     # Get staff details
POST   /admin/staff                # Create staff
PUT    /admin/staff/{staff_id}     # Update staff
DELETE /admin/staff/{staff_id}     # Delete staff
```

### Booking Management (2)
```
GET    /admin/bookings                # List all bookings
PUT    /admin/bookings/{booking_id}/status  # Update booking status
```

### RM Management (4)
```
GET    /admin/rms                     # List all RMs
GET    /admin/rms/{rm_id}             # Get RM details
GET    /admin/rms/{rm_id}/score-history  # RM score history
PUT    /admin/rms/{rm_id}             # Update RM
```

### Vendor Request Approvals (4)
```
GET    /admin/vendor-requests             # List all vendor requests
GET    /admin/vendor-requests/{request_id} # Get request details
POST   /admin/vendor-requests/{request_id}/approve  # Approve request
POST   /admin/vendor-requests/{request_id}/reject   # Reject request
```

### System Configuration (6)
```
GET    /admin/config              # List all configs
GET    /admin/config/{config_key} # Get specific config
POST   /admin/config              # Create config
PUT    /admin/config/{config_key} # Update config
DELETE /admin/config/{config_key} # Delete config
POST   /admin/config/cleanup/expired-tokens  # Manual token cleanup
```

---

## 👤 Customer Endpoints (19)

Requires `customer` role.

### Cart Management (5)
```
GET    /customers/cart              # Get cart items
POST   /customers/cart              # Add to cart
PUT    /customers/cart/{item_id}    # Update cart item
DELETE /customers/cart/{item_id}    # Remove from cart
DELETE /customers/cart/clear/all    # Clear entire cart
POST   /customers/cart/checkout     # Checkout cart
```

### Booking Management (3)
```
GET    /customers/bookings/my-bookings  # My bookings
POST   /customers/bookings              # Create booking
PUT    /customers/bookings/{booking_id}/cancel  # Cancel booking
```

### Favorites (3)
```
GET    /customers/favorites             # Get favorites
POST   /customers/favorites             # Add to favorites
DELETE /customers/favorites/{salon_id} # Remove from favorites
```

### Reviews (3)
```
GET    /customers/reviews/my-reviews  # My reviews
POST   /customers/reviews             # Submit review
PUT    /customers/reviews/{review_id} # Update review
```

### Salon Browsing (3)
```
GET    /customers/salons              # Browse salons
GET    /customers/salons/search       # Search salons
GET    /customers/salons/{salon_id}   # Salon details
```

---

## 🏪 Vendor Endpoints (17)

Requires `vendor` role.

### Dashboard & Analytics (2)
```
GET    /vendors/dashboard    # Vendor dashboard stats
GET    /vendors/analytics    # Detailed analytics
```

### Salon Profile (2)
```
GET    /vendors/salon        # Get my salon
PUT    /vendors/salon        # Update my salon
```

### Service Management (5)
```
GET    /vendors/service-categories  # Get service categories
GET    /vendors/services            # List my services
POST   /vendors/services            # Create service
PUT    /vendors/services/{service_id}     # Update service
DELETE /vendors/services/{service_id}     # Delete service
```

### Staff Management (4)
```
GET    /vendors/staff             # List my staff
POST   /vendors/staff             # Create staff
PUT    /vendors/staff/{staff_id}  # Update staff
DELETE /vendors/staff/{staff_id}  # Delete staff
```

### Booking Management (2)
```
GET    /vendors/bookings                      # My salon bookings
PUT    /vendors/bookings/{booking_id}/status  # Update booking status
```

### Registration & Payment (2)
```
POST   /vendors/complete-registration  # Complete vendor registration
POST   /vendors/process-payment        # Process registration payment
```

---

## 🤝 Relationship Manager Endpoints (13)

Requires `relationship_manager` role.

### Dashboard (1)
```
GET    /rm/dashboard         # RM dashboard with stats
```

### Vendor Request Management (5)
```
POST   /rm/vendor-requests            # Submit vendor request
GET    /rm/vendor-requests            # List my requests
GET    /rm/vendor-requests/{request_id}  # Get request details
PUT    /rm/vendor-requests/{request_id}  # Update request
DELETE /rm/vendor-requests/{request_id}  # Delete request
```

### Salon Management (1)
```
GET    /rm/salons            # My approved salons
```

### Profile Management (2)
```
GET    /rm/profile           # Get my profile
PUT    /rm/profile           # Update my profile
```

### Scoring & Leaderboard (3)
```
GET    /rm/score-history     # My score history
GET    /rm/leaderboard       # RM leaderboard
GET    /rm/service-categories # Service categories (for forms)
```

---

## 🏠 Public Salon Endpoints (11)

No authentication required (public access).

### Browsing & Search (4)
```
GET    /salons                # List all salons (paginated)
GET    /salons/public         # Legacy alias for /salons
GET    /salons/search/nearby  # Nearby salons (lat/lng)
GET    /salons/search/query   # Search salons (name, location, services)
```

### Salon Details (4)
```
GET    /salons/{salon_id}                 # Salon details + reviews
GET    /salons/{salon_id}/services        # Salon services
GET    /salons/{salon_id}/staff           # Salon staff
GET    /salons/{salon_id}/available-slots # Available booking slots
```

### Salon Management (3)
```
POST   /salons                  # Create salon (admin/vendor)
PATCH  /salons/{salon_id}       # Update salon (admin/vendor)
POST   /salons/{salon_id}/approve  # Approve salon (admin only)
POST   /salons/{salon_id}/images   # Upload salon images
```

### Configuration (2)
```
GET    /salons/config/public                  # Public system config
GET    /salons/config/booking-fee-percentage  # Booking commission rate
```

---

## 📅 Booking Endpoints (8)

Mixed access (role-dependent).

```
GET    /bookings                    # List bookings (admin)
GET    /bookings/user/{user_id}     # User bookings (admin/owner)
GET    /bookings/salon/{salon_id}   # Salon bookings (vendor/admin)
GET    /bookings/{booking_id}       # Booking details (admin/owner)
POST   /bookings                    # Create booking (customer)
PATCH  /bookings/{booking_id}       # Update booking (admin)
POST   /bookings/{booking_id}/cancel   # Cancel booking (customer/admin)
POST   /bookings/{booking_id}/complete # Complete booking (vendor/admin)
```

---

## 💰 Payment Endpoints (8)

Razorpay integration.

### Booking Payments (2)
```
POST   /payments/booking/create-order  # Create Razorpay order for booking
POST   /payments/booking/verify        # Verify booking payment
```

### Cart Payments (1)
```
POST   /payments/cart/create-order     # Create Razorpay order for cart checkout
```

### Vendor Registration Payments (2)
```
POST   /payments/registration/create-order  # Create order for vendor registration
POST   /payments/registration/verify        # Verify registration payment
```

### Payment History & Earnings (2)
```
GET    /payments/history          # Payment history (user)
GET    /payments/vendor/earnings  # Vendor earnings breakdown
```

### Webhooks (1)
```
POST   /payments/webhook/razorpay  # Razorpay webhook handler
```

---

## 💼 Career Endpoints (5)

Job applications management.

```
POST   /careers/apply                           # Submit application
GET    /careers/applications                    # List applications (admin)
GET    /careers/applications/{application_id}   # Application details (admin)
PATCH  /careers/applications/{application_id}   # Update application status (admin)
GET    /careers/applications/{application_id}/download/{document_type}  # Download resume/cover letter
```

---

## 📤 Upload Endpoints (3)

File upload to Supabase Storage.

```
POST   /upload/salon-image            # Upload single salon image
POST   /upload/salon-images/multiple  # Upload multiple salon images
DELETE /upload/salon-image             # Delete salon image
```

**Supported Formats:** JPG, JPEG, PNG, WebP  
**Max Size:** 5MB per image  
**Storage:** Supabase Storage bucket

---

## 🗺️ Location Endpoints (3)

Geocoding and location services.

```
POST   /location/geocode           # Convert address to lat/lng
GET    /location/reverse-geocode   # Convert lat/lng to address
GET    /location/salons/nearby     # Find nearby salons (uses PostGIS)
```

---

## 🔄 Realtime Endpoints (4)

WebSocket-based real-time updates (experimental).

```
POST   /realtime/subscribe/salon/{salon_id}      # Subscribe to salon updates
POST   /realtime/subscribe/bookings/{salon_id}   # Subscribe to booking updates
POST   /realtime/unsubscribe                     # Unsubscribe from updates
GET    /realtime/status                          # Check connection status
```

---

## 🧪 Test Email Endpoints (2)

**Dev/Staging Only** - Disabled in production.

```
POST   /test-email/send     # Send test email
GET    /test-email/status   # Email service status
```

---

## 🔒 Rate Limiting

Global rate limits (per IP):
- **Default:** 60 requests/minute
- **Auth endpoints:**
  - Login: 5/minute
  - Signup: 3/minute
  - Password Reset: 3/minute

Rate limiting implemented via **SlowAPI** middleware.

---

## 🎯 Authentication

**Header:** `Authorization: Bearer <access_token>`

**Token Expiry:**
- Access Token: 30 minutes
- Refresh Token: 7 days

**Token Management:**
- Logout blacklists tokens in `blacklisted_tokens` table
- Background task cleans expired tokens every 6 hours
- Refresh tokens via `/auth/refresh`

---

## 📝 Response Format

### Success Response
```json
{
  "success": true,
  "message": "Operation successful",
  "data": { ... }
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "details": { ... }
}
```

### Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 🛠️ Testing Endpoints

1. **Start Backend:**
   ```powershell
   .\run-local.ps1
   ```

2. **Access Docs:**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

3. **Get Token:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"user@example.com","password":"password123"}'
   ```

4. **Use Token:**
   ```bash
   curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/auth/me
   ```

---

## 📌 Notes

- All timestamps are in UTC
- Pagination uses `limit` and `offset` query params
- Soft deletes used where applicable (is_active flag)
- Service role bypasses RLS for all database operations
- CORS configured for `localhost:3000`, `localhost:5173`, `localhost:5174`
