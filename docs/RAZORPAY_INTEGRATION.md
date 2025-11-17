# Razorpay Payment Integration

## Overview
Complete production-ready Razorpay payment gateway integration for the Salon Management Platform.

## Architecture

### Backend Structure
```
app/
├── api/
│   └── payments.py          # API endpoints (thin routing layer)
├── services/
│   ├── payment_service.py   # Business logic for payments
│   └── config_service.py    # Dynamic config management
└── core/
    └── razorpay_service.py  # Razorpay SDK wrapper
```

### Frontend Structure
```
src/
├── services/
│   └── api/
│       └── paymentApi.js    # RTK Query payment endpoints
└── pages/
    └── public/
        └── Payment.jsx      # Razorpay Checkout integration
```

## Payment Flow

### 1. Booking Payment Flow
```
User clicks "Pay Now" in Payment.jsx
    ↓
Frontend: createBooking() → Create booking with status='pending'
    ↓
Frontend: createBookingOrder(booking_id) → POST /payments/booking/create-order
    ↓
Backend: PaymentService.create_booking_payment_order()
    ├── Validate booking exists & user owns it
    ├── Calculate amount (booking_fee + gst)
    ├── Create Razorpay order via RazorpayService
    ├── Store order in booking_payments table
    └── Return {order_id, amount, currency, key_id}
    ↓
Frontend: Open Razorpay Checkout modal
    ├── User completes payment
    └── Razorpay returns {order_id, payment_id, signature}
    ↓
Frontend: verifyBookingPayment() → POST /payments/booking/verify
    ↓
Backend: PaymentService.verify_booking_payment()
    ├── Verify signature using RazorpayService
    ├── Update booking_payments.status = 'completed'
    ├── Update booking_payments.razorpay_payment_id
    ├── Update bookings.payment_status = 'paid'
    └── Return updated booking details
    ↓
Frontend: Clear cart, navigate to confirmation page
```

### 2. Vendor Registration Payment Flow
```
Vendor clicks "Pay Registration Fee"
    ↓
Frontend: createVendorRegistrationOrder() → POST /payments/registration/create-order
    ↓
Backend: PaymentService.create_vendor_registration_order()
    ├── Get registration_fee from system_config
    ├── Create Razorpay order
    ├── Store order in vendor_payments table
    └── Return {order_id, amount, currency, key_id}
    ↓
Frontend: Open Razorpay Checkout modal
    ↓
Frontend: verifyVendorRegistrationPayment() → POST /payments/registration/verify
    ↓
Backend: PaymentService.verify_vendor_registration_payment()
    ├── Verify signature
    ├── Update vendor_payments.status = 'completed'
    ├── Update vendors.payment_status = 'paid'
    ├── Update vendors.is_approved = true (if configured)
    └── Return vendor details
```

## Backend Setup

### 1. Environment Variables
Add to `.env`:
```env
# Razorpay Configuration
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=whsec_xxxxxxxxxx  # Optional: for webhooks
```

### 2. Database Schema

#### booking_payments
```sql
CREATE TABLE booking_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID REFERENCES bookings(id),
    user_id UUID REFERENCES users(id),
    razorpay_order_id TEXT UNIQUE,
    razorpay_payment_id TEXT,
    amount INTEGER,  -- Amount in paisa (₹100 = 10000 paisa)
    currency TEXT DEFAULT 'INR',
    status TEXT DEFAULT 'pending',  -- pending, completed, failed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### vendor_payments
```sql
CREATE TABLE vendor_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID REFERENCES vendors(id),
    razorpay_order_id TEXT UNIQUE,
    razorpay_payment_id TEXT,
    amount INTEGER,
    currency TEXT DEFAULT 'INR',
    payment_type TEXT DEFAULT 'registration_fee',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### system_config
```sql
-- Required config entries:
INSERT INTO system_config (config_key, config_value, description) VALUES
('registration_fee', '500', 'Vendor registration fee in INR'),
('booking_fee_percentage', '10', 'Booking fee percentage'),
('gst_percentage', '18', 'GST percentage on booking fee');
```

### 3. API Endpoints

#### Booking Payments
- `POST /payments/booking/create-order` - Create Razorpay order
  - Body: `{"booking_id": "uuid"}`
  - Returns: `{"order_id": "order_xxx", "amount": 10000, "currency": "INR", "key_id": "rzp_test_xxx"}`

- `POST /payments/booking/verify` - Verify payment signature
  - Body: `{"razorpay_order_id": "order_xxx", "razorpay_payment_id": "pay_xxx", "razorpay_signature": "xxx"}`
  - Returns: `{"booking": {...}, "payment": {...}}`

#### Vendor Registration Payments
- `POST /payments/registration/create-order` - Create registration order
  - Returns: `{"order_id": "order_xxx", "amount": 50000, ...}`

- `POST /payments/registration/verify` - Verify registration payment
  - Body: `{"razorpay_order_id": "order_xxx", "razorpay_payment_id": "pay_xxx", "razorpay_signature": "xxx"}`
  - Returns: `{"vendor": {...}, "payment": {...}}`

#### Query Endpoints
- `GET /payments/history` - Customer payment history
- `GET /payments/vendor/{vendor_id}/earnings?start_date=&end_date=` - Vendor earnings

## Frontend Setup

### 1. Razorpay Checkout.js
Automatically loaded via script tag in `Payment.jsx`:
```javascript
useEffect(() => {
  const script = document.createElement("script");
  script.src = "https://checkout.razorpay.com/v1/checkout.js";
  script.async = true;
  script.onload = () => setRazorpayLoaded(true);
  document.body.appendChild(script);
}, []);
```

### 2. Payment Processing
```javascript
const handlePayNow = async () => {
  // 1. Create booking (status='pending')
  const booking = await createBooking(bookingData).unwrap();
  
  // 2. Create Razorpay order
  const { order_id, amount, key_id } = await createBookingOrder(booking.id).unwrap();
  
  // 3. Open Razorpay modal
  const razorpay = new window.Razorpay({
    key: key_id,
    order_id: order_id,
    handler: async (response) => {
      // 4. Verify payment
      await verifyBookingPayment(response).unwrap();
    }
  });
  razorpay.open();
};
```

## Testing

### Test Mode Credentials
```
Key ID: rzp_test_xxxxxxxxxx
Key Secret: xxxxxxxxxxxxxxxxxx
```

### Test Cards
```
Success: 4111 1111 1111 1111
CVV: Any 3 digits
Expiry: Any future date
```

### Test Flow
1. Go to `/checkout`
2. Select date/time, proceed to payment
3. Click "Pay Now"
4. Razorpay modal opens
5. Enter test card: `4111 1111 1111 1111`
6. Payment succeeds
7. Booking status updated to 'paid'
8. Redirect to confirmation page

## Security

### Signature Verification
**CRITICAL**: Always verify payment signature on backend:
```python
client.utility.verify_payment_signature({
    'razorpay_order_id': order_id,
    'razorpay_payment_id': payment_id,
    'razorpay_signature': signature
})
```

**NEVER** trust frontend payment status without backend verification.

### Amount Validation
- Amounts stored in **paisa** (₹1 = 100 paisa)
- Always validate amount matches expected booking total
- Calculate dynamically from `system_config`, never hardcode

### User Authorization
- Verify user owns the booking before creating order
- Check vendor identity before registration payment
- Use JWT authentication on all endpoints

## Error Handling

### Backend Errors
- `400 Bad Request` - Invalid booking_id, booking not found
- `401 Unauthorized` - User doesn't own booking
- `402 Payment Required` - Order creation failed
- `409 Conflict` - Payment already completed
- `500 Internal Server Error` - Razorpay API error

### Frontend Errors
- `Payment cancelled` - User closed Razorpay modal
- `Payment gateway not loaded` - Checkout.js script failed
- `Payment verification failed` - Signature mismatch (fraud attempt)

## Monitoring

### Logs to Monitor
```python
logger.info(f"Created Razorpay order {order_id} for booking {booking_id}")
logger.info(f"Payment {payment_id} verified for order {order_id}")
logger.error(f"Signature verification failed for order {order_id}")
```

### Database Queries
```sql
-- Failed payments
SELECT * FROM booking_payments WHERE status = 'failed';

-- Pending payments (older than 15 minutes)
SELECT * FROM booking_payments 
WHERE status = 'pending' 
AND created_at < NOW() - INTERVAL '15 minutes';

-- Today's revenue
SELECT SUM(amount)/100.0 as total_inr 
FROM booking_payments 
WHERE status = 'completed' 
AND DATE(created_at) = CURRENT_DATE;
```

## Migration from Fake Payment

### What Changed
- **Old**: `setTimeout` fake payment → immediate booking creation
- **New**: Real Razorpay flow → booking created with `status='pending'` → updated to `'paid'` after verification

### Data Migration
No migration needed - new payment tables separate from existing bookings.

### Rollback Plan
1. Restore old `Payment.jsx` with fake setTimeout
2. Keep new backend endpoints (won't be called)
3. Update booking creation to skip payment verification

## Production Checklist

- [ ] Replace test keys with production keys in `.env`
- [ ] Update Razorpay webhook URL in dashboard
- [ ] Test with real card (₹1 minimum)
- [ ] Verify signature validation works
- [ ] Check logs for errors
- [ ] Monitor failed payments table
- [ ] Set up refund process
- [ ] Configure payment success email notifications
- [ ] Test edge cases (network failure, timeout)
- [ ] Set up Razorpay dashboard alerts

## Support

### Razorpay Documentation
- Python SDK: https://razorpay.com/docs/payments/server-integration/python/
- Checkout.js: https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/
- Signature Verification: https://razorpay.com/docs/payments/server-integration/python/payment-verification/

### Common Issues

**Issue**: "Payment gateway not loaded"
- **Fix**: Check network, ensure Checkout.js script loads

**Issue**: "Signature verification failed"
- **Fix**: Check `RAZORPAY_KEY_SECRET` matches dashboard

**Issue**: "Booking already has payment"
- **Fix**: Check `booking_payments` table, prevent duplicate orders

**Issue**: Amount mismatch
- **Fix**: Amounts in paisa (multiply by 100), check calculation logic
