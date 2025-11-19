# 🛒 CART TO BOOKING FLOW - COMPLETE IMPLEMENTATION

## ✅ All Requirements Implemented

### 1. **Cart Management** ✅
- ✅ Add multiple services from same salon
- ✅ Prevent adding services from different salons
- ✅ Update cart item quantities
- ✅ Remove items from cart
- ✅ Clear entire cart
- ✅ Check salon `accepting_bookings` before adding to cart

### 2. **Checkout Flow** ✅
- ✅ Create booking from cart items
- ✅ Select date and time slots (up to 3)
- ✅ Validate salon accepting bookings
- ✅ Calculate convenience fee + GST
- ✅ Razorpay payment integration
- ✅ Clear cart after successful booking

### 3. **Payment Integration** ✅
- ✅ Razorpay order creation for cart
- ✅ Payment verification
- ✅ Convenience fee (platform fee) payment
- ✅ Service price paid at salon

### 4. **Booking Display** ✅
- ✅ Customer "My Bookings" endpoint
- ✅ Vendor dashboard bookings
- ✅ Booking details with services
- ✅ Multiple time slots support

---

## 🔧 Setup Instructions

### 1. **Run Database Migrations**

```powershell
# Navigate to backend
cd g:\vescavia\Projects\backend

# Apply migrations
supabase migration up
```

Two new migrations:
- `20251118200000_add_accepting_bookings_to_salons.sql` - Adds accepting_bookings toggle
- `20251118200001_add_time_slots_to_bookings.sql` - Adds time_slots array support

### 2. **Configure Razorpay Keys**

Add your Razorpay demo keys to environment variables or system_config table:

**Option A: Environment Variables** (Recommended for development)
```powershell
# In .env file
RAZORPAY_KEY_ID=your_demo_key_id
RAZORPAY_KEY_SECRET=your_demo_key_secret
```

**Option B: Database Config**
```sql
-- Insert Razorpay config
INSERT INTO system_config (key, value, description, is_public)
VALUES 
  ('razorpay_key_id', 'your_demo_key_id', 'Razorpay Key ID', true),
  ('booking_fee_percentage', '10', 'Booking convenience fee percentage', true);
```

### 3. **Restart Backend Server**

```powershell
cd g:\vescavia\Projects\backend
python main.py
```

---

## 📡 API Endpoints

### Cart Operations

```
GET    /api/v1/customers/cart                  # Get cart items
POST   /api/v1/customers/cart                  # Add item to cart
PUT    /api/v1/customers/cart/{item_id}        # Update quantity
DELETE /api/v1/customers/cart/{item_id}        # Remove item
DELETE /api/v1/customers/cart/clear/all        # Clear cart
```

### Checkout & Payment

```
POST   /api/v1/payments/cart/create-order      # Create Razorpay order
POST   /api/v1/customers/cart/checkout         # Complete checkout with payment
```

### Bookings

```
GET    /api/v1/customers/bookings/my-bookings  # Get customer bookings
GET    /api/v1/bookings/salon/{salon_id}       # Get salon bookings (vendor)
```

---

## 🔄 Complete User Flow

### Step 1: Browse & Add to Cart
```javascript
// Add service to cart
POST /api/v1/customers/cart
{
  "service_id": "uuid",
  "quantity": 1
}

// Response: Item added (or quantity updated if exists)
```

### Step 2: Create Payment Order
```javascript
// Get Razorpay order details
POST /api/v1/payments/cart/create-order

// Response:
{
  "order_id": "order_xxx",
  "amount": 118.00,  // Convenience fee + GST
  "key_id": "rzp_test_xxx",
  "breakdown": {
    "service_price": 1000.00,      // Pay at salon
    "booking_fee": 100.00,          // Platform fee (10%)
    "gst_amount": 18.00,            // GST on booking fee
    "total_to_pay_now": 118.00      // Pay online
  }
}
```

### Step 3: Complete Payment (Frontend)
```javascript
// Razorpay Checkout (frontend handles this)
const options = {
  key: response.key_id,
  amount: response.amount_paise,
  order_id: response.order_id,
  handler: function(response) {
    // Payment successful - proceed to checkout
    checkoutCart(response);
  }
};

const rzp = new Razorpay(options);
rzp.open();
```

### Step 4: Checkout with Payment Details
```javascript
// Create booking from cart
POST /api/v1/customers/cart/checkout
{
  "booking_date": "2025-11-20",
  "time_slots": ["10:00 AM", "11:00 AM"],  // Max 3 slots
  "razorpay_order_id": "order_xxx",
  "razorpay_payment_id": "pay_xxx",
  "razorpay_signature": "signature_xxx",
  "payment_method": "razorpay",
  "notes": "Optional booking notes"
}

// Response:
{
  "success": true,
  "message": "Booking created successfully",
  "booking_id": "uuid",
  "booking_number": "BK-20251120-00001"
}

// Cart is automatically cleared after successful booking
```

---

## 🎯 Key Features

### Multiple Time Slots (Max 3)
- Customer can select 1-3 time slots for flexibility
- Stored in `bookings.time_slots` JSONB column
- Primary slot also stored in `booking_time` for backward compatibility

### Accepting Bookings Toggle
- Vendors can toggle `accepting_bookings` in their salon settings
- When disabled:
  - Cart add fails with clear message
  - Checkout blocked
  - "Add to Cart" button disabled on frontend

### Split Payment Model
- **Online (Convenience Fee)**: Platform fee + GST paid via Razorpay
- **At Salon (Service Price)**: Full service amount paid at salon
- Example:
  - Service: ₹1000
  - Platform fee (10%): ₹100
  - GST (18%): ₹18
  - **Pay online**: ₹118
  - **Pay at salon**: ₹1000

### Cart Validation
- ✅ Only one salon at a time
- ✅ Service must be active
- ✅ Salon must be active
- ✅ Salon must be accepting bookings
- ✅ Auto-increment quantity if same service added twice

---

## 📊 Database Changes

### New Columns

**salons table:**
```sql
accepting_bookings BOOLEAN DEFAULT true
```

**bookings table:**
```sql
time_slots JSONB DEFAULT '[]'  -- Array of time strings, max 3
```

### New Constraints
- `time_slots_is_array` - Ensures JSONB is array type
- `time_slots_max_3` - Limits to 3 time slots maximum

---

## 🧪 Testing Flow

### Test 1: Add to Cart
```bash
curl -X POST http://localhost:8000/api/v1/customers/cart \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "service_uuid",
    "quantity": 1
  }'
```

### Test 2: Create Payment Order
```bash
curl -X POST http://localhost:8000/api/v1/payments/cart/create-order \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test 3: Checkout (after payment)
```bash
curl -X POST http://localhost:8000/api/v1/customers/cart/checkout \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "booking_date": "2025-11-20",
    "time_slots": ["10:00 AM", "11:00 AM"],
    "razorpay_order_id": "order_xxx",
    "razorpay_payment_id": "pay_xxx",
    "razorpay_signature": "signature_xxx"
  }'
```

---

## 🔐 Razorpay Test Cards

Use these for testing:

- **Card Number**: 4111 1111 1111 1111
- **CVV**: Any 3 digits
- **Expiry**: Any future date

---

## ✨ What's Next?

1. **Frontend Integration**:
   - Implement Razorpay Checkout UI
   - Add payment verification flow
   - Show booking confirmation

2. **Vendor Dashboard**:
   - Add `accepting_bookings` toggle
   - Display bookings with time slots
   - Show booking details with customer info

3. **Notifications**:
   - Email confirmation after booking
   - SMS notifications (optional)
   - Vendor booking alerts

---

All critical requirements are now implemented! 🎉
