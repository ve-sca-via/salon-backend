-- ============================================================================
-- FIX VENDOR REGISTRATION PAYMENTS TABLE
-- ============================================================================
-- Issue: Code tries to insert 'metadata' column which doesn't exist
-- Issue: Code expects 'salon_id' column to link payment to salon
-- Issue: Code uses 'paid_at' but schema has 'payment_completed_at'
-- Issue: Code uses status 'completed' but enum expects 'success'
--
-- Solution: Add missing columns and align with code expectations
-- ============================================================================

-- Add missing columns to vendor_registration_payments
ALTER TABLE vendor_registration_payments
  ADD COLUMN IF NOT EXISTS salon_id UUID REFERENCES salons(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS vendor_request_id UUID REFERENCES vendor_join_requests(id) ON DELETE SET NULL;

-- Add comment for documentation
COMMENT ON COLUMN vendor_registration_payments.salon_id IS 'Salon ID (linked after payment verification and salon activation)';
COMMENT ON COLUMN vendor_registration_payments.vendor_request_id IS 'Original vendor join request that led to this payment';

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_vendor_registration_payments_salon_id 
  ON vendor_registration_payments(salon_id) 
  WHERE salon_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vendor_registration_payments_vendor_request_id 
  ON vendor_registration_payments(vendor_request_id) 
  WHERE vendor_request_id IS NOT NULL;

-- Add index for vendor_id queries
CREATE INDEX IF NOT EXISTS idx_vendor_registration_payments_vendor_id 
  ON vendor_registration_payments(vendor_id);

-- Add index for razorpay queries (if not exists)
CREATE INDEX IF NOT EXISTS idx_vendor_registration_payments_razorpay_order 
  ON vendor_registration_payments(razorpay_order_id) 
  WHERE razorpay_order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vendor_registration_payments_razorpay_payment 
  ON vendor_registration_payments(razorpay_payment_id) 
  WHERE razorpay_payment_id IS NOT NULL;

-- Update table comment
COMMENT ON TABLE vendor_registration_payments IS 'One-time registration fee payments for vendor salon accounts. Separate from bookings-based payments table for cleaner architecture and audit trail.';
