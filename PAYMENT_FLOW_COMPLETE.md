# Complete Payment Flow Documentation

## Overview
This document describes the end-to-end payment flow for cart checkout in the salon booking system. The flow involves Frontend (React), Backend (FastAPI), Database (PostgreSQL via Supabase), and Razorpay (Payment Gateway).

---

## Architecture Overview

### Payment Split Model
- **Online Payment**: Convenience Fee (10% of service total + 18% GST) → Platform Revenue
- **At Salon Payment**: Full Service Amount → Vendor Revenue

### Components
1. **Frontend**: React + RTK Query + Razorpay Checkout Modal
2. **Backend**: FastAPI + Service Layer Pattern
3. **Database**: PostgreSQL with tables: `cart_items`, `bookings`, `booking_payments`
4. **Payment Gateway**: Razorpay (for secure online payments)

---

## Complete Flow (14 Steps)

### Phase 1: Cart Management (Steps 1-3)

#### Step 1: Add Services to Cart
- **User Action**: Clicks "Add to Cart" on service
- **Frontend**: `POST /api/v1/customers/cart`
- **Backend**: `CustomerService.add_to_cart()`
- **Database**: Inserts into `cart_items` table
- **Schema**:
  ```sql
  cart_items (
    id UUID,
    user_id UUID,
    salon_id UUID,
    service_id UUID,
    quantity INTEGER,
    metadata JSONB,
    created_at TIMESTAMP
  )
  ```

#### Step 2: Navigate to Checkout
- **User Action**: Clicks cart icon → "Proceed to Checkout"
- **Frontend**: Navigates to `/checkout`

#### Step 3: Fetch Cart Data
- **Frontend**: `useGetCartQuery()` → `GET /api/v1/customers/cart`
- **Backend**: `CustomerService.get_cart()`
- **Database**: Joins `cart_items`, `services`, `salons`
- **Response**:
  ```json
  {
    "items": [...],
    "salon_id": "uuid",
    "salon_name": "Beauty Salon",
    "total_amount": 1000.00,
    "item_count": 3
  }
  ```

---

### Phase 2: Appointment Selection (Steps 4-6)

#### Step 4: Select Date
- **User Action**: Selects date from calendar
- **Config**: `max_booking_advance_days` (default: 30)
- **Frontend State**: `selectedDate = "2025-11-25"`

#### Step 5: Select Time Slots
- **User Action**: Selects up to 3 time slots (15-min intervals)
- **Time Range**: 2:30 PM - 8:15 PM
- **Frontend State**: `selectedTimes = ["2:30 PM", "2:45 PM"]`

#### Step 6: Review Pricing
- **Display**:
  - Service Total: ₹1000.00
  - Booking Fee (10%): ₹100.00
  - GST (18%): ₹18.00
  - **Pay Now**: ₹118.00 (online)
  - **Pay at Salon**: ₹1000.00 (cash/card)

---

### Phase 3: Payment Initiation (Steps 7-9)

#### Step 7: User Clicks "Proceed to Payment"
- **Frontend**: Validates `selectedDate` and `selectedTimes`
- **Frontend**: Calls `handleProceedToPayment()`

#### Step 8: Create Razorpay Order
- **Frontend**: `createPaymentOrder().unwrap()`
- **API**: `POST /api/v1/payments/cart/create-order`
- **Backend**: `PaymentService.create_cart_payment_order()`
- **Process**:
  1. Fetches cart items
  2. Calculates service total
  3. Fetches `booking_fee_percentage` from `system_config` (default: 10%)
  4. Calculates booking_fee = total × 10%
  5. Calculates gst = booking_fee × 18%
  6. Creates Razorpay order with `razorpay.client.order.create()`
- **Response**:
  ```json
  {
    "order_id": "order_NzX...",
    "amount": 118.00,
    "amount_paise": 11800,
    "currency": "INR",
    "key_id": "rzp_test_...",
    "breakdown": {
      "service_price": 1000.00,
      "booking_fee": 100.00,
      "gst_amount": 18.00,
      "total_to_pay_now": 118.00,
      "pay_at_salon": 1000.00
    }
  }
  ```

#### Step 9: Open Razorpay Modal
- **Frontend**: Creates Razorpay options object
- **Frontend**: `const rzp = new window.Razorpay(options)`
- **Frontend**: `rzp.open()`
- **Razorpay Modal**: Opens in browser (secure payment form)

---

### Phase 4: Payment Completion (Steps 10-11)

#### Step 10: User Completes Payment
- **User Action**: Enters card details / UPI / netbanking
- **Razorpay**: Processes payment securely
- **Razorpay**: Returns payment response to frontend

#### Step 11: Razorpay Returns Payment Details
- **Razorpay Response**:
  ```javascript
  {
    razorpay_order_id: "order_NzX...",
    razorpay_payment_id: "pay_NzY...",
    razorpay_signature: "abc123..."
  }
  ```
- **Frontend**: Calls `handleCheckoutSuccess(paymentResponse)`

---

### Phase 5: Booking Creation (Steps 12-14)

#### Step 12: Complete Checkout
- **Frontend**: `checkoutCart({ booking_date, time_slots, razorpay_* }).unwrap()`
- **API**: `POST /api/v1/customers/cart/checkout`
- **Backend**: `CustomerService.checkout_cart()`

#### Step 13: Backend Processing
1. **Fetch Cart**: Gets cart items with services
2. **Validate Salon**: Checks `is_active` and `accepting_bookings`
3. **Verify Payment Signature**:
   ```python
   razorpay_service.verify_payment_signature(
       razorpay_order_id,
       razorpay_payment_id,
       razorpay_signature
   )
   ```
   - If invalid: Raises 400 error (prevents fraud)
   - If valid: Continues
4. **Calculate Totals**:
   - Fetches `booking_fee_percentage` from config
   - booking_fee = service_total × percentage / 100
   - gst_amount = booking_fee × 0.18
5. **Create Booking**:
   - Calls `BookingService.create_booking()`
   - Creates booking in `bookings` table:
     ```sql
     bookings (
       id UUID,
       booking_number VARCHAR,
       customer_id UUID,
       salon_id UUID,
       services JSONB,
       booking_date DATE,
       booking_time TIME,
       time_slots TEXT[],
       status booking_status DEFAULT 'confirmed',
       service_price DECIMAL,
       convenience_fee DECIMAL,
       total_amount DECIMAL,
       convenience_fee_paid BOOLEAN DEFAULT true,
       service_paid BOOLEAN DEFAULT false,
       payment_completed_at TIMESTAMP,
       razorpay_order_id VARCHAR,
       razorpay_payment_id VARCHAR,
       razorpay_signature VARCHAR,
       created_at TIMESTAMP
     )
     ```
6. **Create Payment Record**:
   - Inserts into `booking_payments` table:
     ```sql
     booking_payments (
       id UUID,
       booking_id UUID REFERENCES bookings(id),
       customer_id UUID,
       razorpay_order_id VARCHAR,
       razorpay_payment_id VARCHAR,
       razorpay_signature VARCHAR,
       amount DECIMAL,
       convenience_fee DECIMAL,
       service_amount DECIMAL,
       currency VARCHAR DEFAULT 'INR',
       status payment_status DEFAULT 'success',
       payment_method VARCHAR,
       paid_at TIMESTAMP,
       created_at TIMESTAMP
     )
     ```
7. **Clear Cart**:
   - Deletes all items from `cart_items` for user
8. **Send Email**:
   - Booking confirmation email to customer
   - Notification email to salon vendor

#### Step 14: Redirect to Bookings
- **Backend Response**:
  ```json
  {
    "success": true,
    "message": "Booking created successfully",
    "booking": { ... },
    "booking_id": "uuid",
    "booking_number": "BK123456"
  }
  ```
- **Frontend**: `toast.success("Booking confirmed!")`
- **Frontend**: `navigate('/customer/bookings')`

---

## Key Files and Their Roles

### Frontend
| File | Role |
|------|------|
| `src/pages/public/Checkout.jsx` | Main checkout UI component |
| `src/services/api/cartApi.js` | RTK Query for cart operations |
| `src/services/api/paymentApi.js` | RTK Query for payment operations |
| `index.html` | Loads Razorpay script |

### Backend
| File | Role |
|------|------|
| `app/api/customers.py` | Cart & checkout endpoints |
| `app/api/payments.py` | Payment endpoints |
| `app/services/customer_service.py` | Cart & checkout business logic |
| `app/services/payment_service.py` | Payment order creation |
| `app/services/booking_service.py` | Booking creation logic |
| `app/services/payment.py` | Razorpay integration |
| `app/schemas/request/booking.py` | Request schemas |

### Database
| Table | Purpose |
|-------|---------|
| `cart_items` | Stores cart items before checkout |
| `bookings` | Stores completed bookings |
| `booking_payments` | Stores payment records |
| `system_config` | Stores config (booking_fee_percentage) |

---

## Error Handling

### Common Errors
| Error | Cause | Solution |
|-------|-------|----------|
| Cart is empty | User navigates to checkout without items | Frontend redirects to cart |
| Salon inactive | Salon deactivated between cart add and checkout | Show error, clear cart |
| Payment verification failed | Invalid signature (fraud attempt) | Reject checkout, log incident |
| Booking creation failed | Database error during transaction | Rollback, show error |

### Error Responses
```json
{
  "detail": "Payment verification failed. Please contact support."
}
```

---

## Security Measures

### Payment Signature Verification
- **Purpose**: Prevents payment tampering and fraud
- **Method**: HMAC SHA256 signature verification
- **Process**:
  1. Razorpay generates signature using secret key
  2. Frontend receives signature with payment response
  3. Backend verifies signature using same secret key
  4. If signatures match: Payment is authentic
  5. If signatures don't match: Payment is rejected

### Database Transactions
- All booking + payment creation happens in a transaction
- If any step fails: Entire operation rolls back
- Ensures data consistency

---

## Testing Checklist

### Manual Testing
- [ ] Add services to cart
- [ ] Navigate to checkout
- [ ] Select date and time
- [ ] Verify pricing calculation
- [ ] Click "Proceed to Payment"
- [ ] Razorpay modal opens
- [ ] Complete test payment
- [ ] Booking created successfully
- [ ] Cart cleared
- [ ] Booking appears in "My Bookings"
- [ ] Payment record exists in database

### Edge Cases
- [ ] Empty cart → redirects to cart
- [ ] Inactive salon → shows error
- [ ] Payment cancelled → shows toast
- [ ] Payment fails → shows error
- [ ] Invalid signature → rejects checkout
- [ ] Network error during checkout → handles gracefully

---

## Configuration

### System Config (Backend)
```sql
system_config (
  config_key = 'booking_fee_percentage',
  config_value = '10.0',
  is_encrypted = false
)

system_config (
  config_key = 'max_booking_advance_days',
  config_value = '30',
  is_encrypted = false
)
```

### Environment Variables
```env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
```

---

## Monitoring and Logging

### Key Log Points
1. Cart item added: `customer_service.py:add_to_cart()`
2. Payment order created: `payment_service.py:create_cart_payment_order()`
3. Payment signature verified: `customer_service.py:checkout_cart()`
4. Booking created: `booking_service.py:create_booking()`
5. Payment record created: `booking_service.py:create_booking()`
6. Cart cleared: `customer_service.py:clear_cart()`

### Metrics to Track
- Cart abandonment rate
- Payment success rate
- Payment failure reasons
- Average checkout time
- Booking creation errors

---

## Future Enhancements
1. **Retry Logic**: Auto-retry failed bookings
2. **Webhooks**: Handle Razorpay webhooks for payment status
3. **Partial Refunds**: Support cancellation with refunds
4. **Multiple Payment Methods**: Add UPI, wallets, etc.
5. **Payment Reminders**: Remind users of abandoned carts
6. **Analytics**: Track conversion funnel

---

## Support

For issues or questions:
1. Check logs in backend terminal
2. Check browser console for frontend errors
3. Verify Razorpay credentials
4. Check database for payment records
5. Review this document for flow understanding

---

**Last Updated**: November 19, 2025
**Status**: ✅ PRODUCTION READY
