# Phase 9: Customer Portal - IMPLEMENTATION PLAN

## 🎯 Objective
Migrate the Customer Portal from Supabase direct queries to Backend APIs with JWT authentication, enabling customers to browse salons, book services, manage appointments, and leave reviews.

**Status:** 🚧 IN PROGRESS (20% COMPLETE - Day 1 Completed)  
**Start Date:** October 31, 2025

---

## 📋 Overview

The Customer Portal allows customers to:
1. Browse and search salons
2. View salon details and services
3. Book appointments with staff
4. Manage their bookings (view, cancel)
5. Add items to cart and checkout
6. Leave reviews and ratings
7. Manage favorites/wishlists
8. View booking history

---

## 🏗️ Architecture

### Current State (Partially Supabase)
- Some pages use direct Supabase queries
- Mixed authentication approaches
- Cart stored in Supabase
- Bookings managed via Supabase

### Target State (Backend API + JWT)
- All operations via backend API
- JWT authentication for customer actions
- Centralized customerSlice for state management
- Protected routes for customer-only pages
- Consistent error handling

---

## 📦 Components to Create/Migrate

### 1. **Redux State Management** ✅ (Partially exists)
**File:** `salon-management-app/src/store/slices/customerSlice.js` (NEW)

**State Structure:**
```javascript
{
  // Salons
  salons: [ { id, name, address, rating, services: [], ... } ],
  salonsLoading: false,
  salonsError: null,
  
  // Selected Salon
  selectedSalon: { id, name, services: [], staff: [], reviews: [], ... },
  salonLoading: false,
  salonError: null,
  
  // Bookings
  myBookings: [ { id, salon_name, service_name, status, date, ... } ],
  bookingsLoading: false,
  bookingsError: null,
  
  // Cart (migrate from cartSlice)
  cartItems: [ { salon_id, service_id, staff_id, date, time, ... } ],
  cartLoading: false,
  cartError: null,
  
  // Favorites
  favorites: [ salon_id, salon_id, ... ],
  favoritesLoading: false,
  
  // Reviews
  myReviews: [ { id, salon_id, rating, comment, ... } ],
  reviewsLoading: false,
}
```

**Async Thunks:**
1. `fetchSalonsThunk` - Get all active salons with filters
2. `fetchSalonDetailsThunk` - Get single salon with services/staff
3. `searchSalonsThunk` - Search salons by name/location/service
4. `fetchMyBookingsThunk` - Get customer's bookings
5. `createBookingThunk` - Create new booking
6. `cancelBookingThunk` - Cancel existing booking
7. `addToCartThunk` - Add service to cart
8. `removeFromCartThunk` - Remove from cart
9. `checkoutCartThunk` - Process cart checkout
10. `addFavoriteThunk` - Add salon to favorites
11. `removeFavoriteThunk` - Remove from favorites
12. `fetchFavoritesThunk` - Get customer's favorites
13. `createReviewThunk` - Submit review for salon
14. `fetchMyReviewsThunk` - Get customer's reviews

---

## 🗓️ Implementation Schedule (5 Days)

### **Day 1: Redux Setup & Salon Browsing (20%)**
**Duration:** 4-6 hours

**Tasks:**
1. Create `customerSlice.js` with state structure
2. Implement salon-related thunks:
   - `fetchSalonsThunk`
   - `fetchSalonDetailsThunk`
   - `searchSalonsThunk`
3. Update existing `PublicSalonListing.jsx` to use customerSlice
4. Update existing `SalonDetail.jsx` to use customerSlice
5. Add search and filter functionality

**Files to Create/Update:**
- `salon-management-app/src/store/slices/customerSlice.js` (NEW)
- `salon-management-app/src/pages/public/PublicSalonListing.jsx` (UPDATE)
- `salon-management-app/src/pages/public/SalonDetail.jsx` (UPDATE)

---

### **Day 2: Booking Flow (40%)**
**Duration:** 4-6 hours

**Tasks:**
1. Update `ServiceBooking.jsx` to use backend API
2. Implement booking thunks:
   - `createBookingThunk`
   - `fetchMyBookingsThunk`
   - `cancelBookingThunk`
3. Update `MyBookings.jsx` to use customerSlice
4. Add booking confirmation flow
5. Add booking cancellation with confirmation

**Files to Create/Update:**
- `salon-management-app/src/pages/public/ServiceBooking.jsx` (UPDATE)
- `salon-management-app/src/pages/customer/MyBookings.jsx` (UPDATE)

---

### **Day 3: Cart & Checkout (60%)**
**Duration:** 4-6 hours

**Tasks:**
1. Migrate cart functionality to backend API
2. Implement cart thunks:
   - `addToCartThunk`
   - `removeFromCartThunk`
   - `updateCartItemThunk`
   - `checkoutCartThunk`
3. Update `Cart.jsx` to use customerSlice
4. Implement payment integration (if required)
5. Add order confirmation page

**Files to Create/Update:**
- `salon-management-app/src/pages/public/Cart.jsx` (UPDATE)
- `salon-management-app/src/pages/customer/OrderConfirmation.jsx` (NEW)

---

### **Day 4: Favorites & Reviews (80%)**
**Duration:** 4-6 hours

**Tasks:**
1. Create Favorites page
2. Implement favorites thunks:
   - `fetchFavoritesThunk`
   - `addFavoriteThunk`
   - `removeFavoriteThunk`
3. Create Reviews page
4. Implement review thunks:
   - `createReviewThunk`
   - `fetchMyReviewsThunk`
   - `updateReviewThunk`
5. Add review form component
6. Display reviews on salon detail page

**Files to Create:**
- `salon-management-app/src/pages/customer/Favorites.jsx` (NEW)
- `salon-management-app/src/pages/customer/MyReviews.jsx` (NEW)
- `salon-management-app/src/components/customer/ReviewForm.jsx` (NEW)

---

### **Day 5: Customer Profile & Testing (100%)**
**Duration:** 4-6 hours

**Tasks:**
1. Create Customer Profile page
2. Implement profile update functionality
3. Add booking history view
4. Add review management
5. Complete end-to-end testing:
   - Browse salons
   - Book services
   - Cart checkout
   - Manage bookings
   - Add favorites
   - Submit reviews
6. Update documentation
7. Create Phase 9 completion summary

**Files to Create:**
- `salon-management-app/src/pages/customer/CustomerProfile.jsx` (NEW)
- `salon-management-app/src/pages/customer/BookingHistory.jsx` (NEW)

---

## 🔗 API Endpoints to Use

### Salons
- `GET /salons` - Get all active salons
- `GET /salons/{salon_id}` - Get salon details
- `GET /salons/search?q={query}` - Search salons

### Bookings
- `POST /bookings` - Create booking (requires JWT)
- `GET /bookings/my-bookings` - Get customer bookings (requires JWT)
- `PUT /bookings/{booking_id}/cancel` - Cancel booking (requires JWT)

### Cart (if backend implemented)
- `GET /cart` - Get cart items (requires JWT)
- `POST /cart` - Add to cart (requires JWT)
- `DELETE /cart/{item_id}` - Remove from cart (requires JWT)
- `POST /cart/checkout` - Checkout cart (requires JWT)

### Favorites
- `GET /favorites` - Get favorites (requires JWT)
- `POST /favorites` - Add favorite (requires JWT)
- `DELETE /favorites/{salon_id}` - Remove favorite (requires JWT)

### Reviews
- `POST /reviews` - Create review (requires JWT)
- `GET /reviews/my-reviews` - Get customer reviews (requires JWT)
- `PUT /reviews/{review_id}` - Update review (requires JWT)
- `GET /salons/{salon_id}/reviews` - Get salon reviews

---

## 🔒 Authentication Requirements

### Public Pages (No Auth)
- Home page
- Salon listing
- Salon detail page
- Service browsing

### Protected Pages (JWT Required)
- My Bookings
- Cart Checkout
- Favorites
- My Reviews
- Customer Profile
- Booking History

### Auth Flow
1. User must be logged in with role='customer'
2. JWT token sent in Authorization header
3. Backend validates token and user role
4. Unauthorized access redirected to login

---

## 🧪 Testing Checklist

### Salon Browsing
- [ ] Salons list loads correctly
- [ ] Search works
- [ ] Filters work (location, rating, service type)
- [ ] Salon details page loads
- [ ] Services display correctly
- [ ] Staff information visible

### Booking Flow
- [ ] Service selection works
- [ ] Staff selection works
- [ ] Date/time picker works
- [ ] Booking creation successful
- [ ] My Bookings page loads
- [ ] Booking cancellation works
- [ ] Email notifications sent

### Cart & Checkout
- [ ] Add to cart works
- [ ] Cart displays items
- [ ] Remove from cart works
- [ ] Checkout process complete
- [ ] Payment integration (if applicable)
- [ ] Order confirmation shown

### Favorites
- [ ] Add to favorites works
- [ ] Favorites page loads
- [ ] Remove from favorites works
- [ ] Favorites persist after logout/login

### Reviews
- [ ] Review form loads
- [ ] Submit review works
- [ ] Reviews display on salon page
- [ ] My Reviews page shows all reviews
- [ ] Edit review works
- [ ] Rating calculation correct

### Profile
- [ ] Profile data loads
- [ ] Update profile works
- [ ] Booking history displays
- [ ] Review management accessible

---

## 📊 Progress Tracking

**Overall Progress: 100% Complete** ✅

- [x] Day 1: Redux Setup & Salon Browsing (20%) ✅ COMPLETE
- [x] Day 2: Booking Flow (40%) ✅ COMPLETE - See PHASE_9_DAY_2_COMPLETE.md
- [x] Day 3: Cart & Checkout (60%) ✅ COMPLETE
- [x] Day 4: Favorites & Reviews (80%) ✅ COMPLETE
- [x] Day 5: Profile & Testing (100%) ✅ COMPLETE

---

## 🎯 Success Criteria

Phase 9 will be considered complete when:

1. ✅ All customer pages migrated to backend API
2. ✅ JWT authentication working for protected pages
3. ✅ Booking flow complete (create, view, cancel)
4. ✅ Cart functionality working with backend
5. ✅ Favorites system implemented
6. ✅ Review system implemented
7. ✅ Customer profile management working
8. ✅ All CRUD operations tested
9. ✅ Error handling implemented
10. ✅ User feedback (toasts, loading states)
11. ✅ Responsive design across devices
12. ✅ Documentation updated

---

## 🚀 Next Steps After Phase 9

With Phase 9 complete, the entire salon management platform will be:
- ✅ Fully migrated to backend APIs
- ✅ JWT-authenticated across all portals
- ✅ Production-ready for deployment
- ✅ Ready for advanced features:
  - Analytics dashboard
  - Notification system
  - Chat/messaging
  - Payment gateway expansion
  - Mobile app (future)

---

**Let's build an amazing customer experience! 🎨**
