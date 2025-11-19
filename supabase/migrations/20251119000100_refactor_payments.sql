-- ============================================================================
-- PAYMENT SCHEMA REFACTOR - Production Ready
-- ============================================================================
-- Refactors payment tracking to eliminate duplication and support proper
-- transaction separation between convenience fees and service payments
-- 
-- BEFORE: 
-- - bookings had: service_price, convenience_fee, total_amount (confusing)
-- - booking_payments tracked only convenience fee (limited)
-- 
-- AFTER:
-- - bookings only has: service_price (clean)
-- - payments table tracks ALL transactions with type (scalable)

-- ============================================================================
-- STEP 1: Create new unified payments table
-- ============================================================================

CREATE TABLE IF NOT EXISTS payments (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Relationships
  booking_id UUID NOT NULL REFERENCES bookings(id) ON DELETE RESTRICT,
  customer_id UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
  
  -- Payment Type (convenience_fee or service_payment)
  payment_type VARCHAR(50) NOT NULL CHECK (payment_type IN ('convenience_fee', 'service_payment', 'refund')),
  
  -- Amount Details
  amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
  currency VARCHAR(3) DEFAULT 'INR' NOT NULL,
  
  -- Razorpay Integration (for online payments)
  razorpay_order_id VARCHAR(100),
  razorpay_payment_id VARCHAR(100),
  razorpay_signature VARCHAR(255),
  
  -- Payment Status
  status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'success', 'failed', 'refunded')),
  payment_method VARCHAR(50), -- 'razorpay', 'cash', 'card', 'upi'
  
  -- Timestamps
  paid_at TIMESTAMPTZ,
  failed_at TIMESTAMPTZ,
  refunded_at TIMESTAMPTZ,
  
  -- Metadata
  payment_metadata JSONB DEFAULT '{}'::jsonb,
  error_code VARCHAR(100),
  error_description TEXT,
  notes TEXT,
  
  -- Audit Trail
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  created_by UUID REFERENCES auth.users(id),
  updated_by UUID REFERENCES auth.users(id),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES auth.users(id),
  
  -- Constraints
  CONSTRAINT payment_online_requires_razorpay 
    CHECK (
      (payment_type != 'convenience_fee') OR 
      (razorpay_payment_id IS NOT NULL AND razorpay_signature IS NOT NULL) OR
      (status != 'success')
    ),
  
  CONSTRAINT payment_success_requires_paid_at
    CHECK (
      (status != 'success') OR (paid_at IS NOT NULL)
    )
);

-- Indexes for performance
CREATE INDEX idx_payments_booking_id ON payments(booking_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_payments_customer_id ON payments(customer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_payments_type ON payments(payment_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_payments_status ON payments(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_payments_razorpay_order ON payments(razorpay_order_id) WHERE razorpay_order_id IS NOT NULL;
CREATE INDEX idx_payments_razorpay_payment ON payments(razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL;
CREATE INDEX idx_payments_paid_at ON payments(paid_at) WHERE status = 'success';
CREATE INDEX idx_payments_type_status ON payments(payment_type, status) WHERE deleted_at IS NULL;

-- Enable RLS
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

-- Trigger for updated_at
CREATE TRIGGER set_payments_updated_at
  BEFORE UPDATE ON payments
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- STEP 2: Migrate existing data from booking_payments to payments
-- ============================================================================

INSERT INTO payments (
  id,
  booking_id,
  customer_id,
  payment_type,
  amount,
  currency,
  razorpay_order_id,
  razorpay_payment_id,
  razorpay_signature,
  status,
  payment_method,
  paid_at,
  failed_at,
  error_code,
  error_description,
  created_at,
  updated_at,
  created_by,
  updated_by,
  deleted_at,
  deleted_by
)
SELECT 
  id,
  booking_id,
  customer_id,
  'convenience_fee' as payment_type, -- All existing payments are convenience fees
  amount,
  currency,
  razorpay_order_id,
  razorpay_payment_id,
  razorpay_signature,
  status,
  payment_method,
  payment_completed_at as paid_at,
  payment_failed_at as failed_at,
  error_code,
  error_description,
  created_at,
  updated_at,
  created_by,
  updated_by,
  deleted_at,
  deleted_by
FROM booking_payments
WHERE NOT EXISTS (
  SELECT 1 FROM payments p WHERE p.id = booking_payments.id
);

-- ============================================================================
-- STEP 3: Update bookings table structure
-- ============================================================================

-- Remove redundant payment tracking columns from bookings
-- Keep them for now but deprecate them (remove in future migration)
-- This allows gradual transition without breaking existing code

-- Add comments to mark deprecated columns (only for columns that actually exist)
COMMENT ON COLUMN bookings.convenience_fee IS 'DEPRECATED: Use payments table with payment_type=convenience_fee. This column kept for backward compatibility only.';
COMMENT ON COLUMN bookings.total_amount IS 'DEPRECATED: Calculate from service_price + SUM(payments.amount). This column kept for backward compatibility only.';
COMMENT ON COLUMN bookings.convenience_fee_paid IS 'DEPRECATED: Check payments table WHERE payment_type=convenience_fee AND status=success. This column kept for backward compatibility only.';
COMMENT ON COLUMN bookings.service_price_paid IS 'DEPRECATED: Check payments table WHERE payment_type=service_payment AND status=success. This column kept for backward compatibility only.';

-- ============================================================================
-- STEP 4: Create helper views for easy querying
-- ============================================================================

-- View: Bookings with payment summary
CREATE OR REPLACE VIEW bookings_with_payments AS
SELECT 
  b.id,
  b.booking_number,
  b.customer_id,
  b.salon_id,
  b.service_id,
  b.booking_date,
  b.booking_time,
  b.service_price,
  b.status,
  b.customer_name,
  b.customer_phone,
  b.customer_email,
  b.created_at,
  b.updated_at,
  -- Convenience fee payment info
  cf.id as convenience_fee_payment_id,
  cf.amount as convenience_fee_amount,
  cf.status as convenience_fee_status,
  cf.paid_at as convenience_fee_paid_at,
  cf.razorpay_payment_id as convenience_fee_razorpay_payment_id,
  -- Service payment info
  sp.id as service_payment_id,
  sp.amount as service_payment_amount,
  sp.status as service_payment_status,
  sp.paid_at as service_payment_paid_at,
  sp.payment_method as service_payment_method,
  -- Computed flags (for backward compatibility)
  (cf.status = 'success') as is_convenience_fee_paid,
  (sp.status = 'success') as is_service_paid,
  (cf.status = 'success' AND sp.status = 'success') as is_fully_paid
FROM bookings b
LEFT JOIN payments cf ON cf.booking_id = b.id 
  AND cf.payment_type = 'convenience_fee' 
  AND cf.deleted_at IS NULL
LEFT JOIN payments sp ON sp.booking_id = b.id 
  AND sp.payment_type = 'service_payment' 
  AND sp.deleted_at IS NULL
WHERE b.deleted_at IS NULL;

-- View: Platform revenue (convenience fees collected)
CREATE OR REPLACE VIEW platform_revenue AS
SELECT 
  DATE(paid_at) as date,
  COUNT(*) as transaction_count,
  SUM(amount) as total_revenue,
  AVG(amount) as avg_transaction,
  currency
FROM payments
WHERE payment_type = 'convenience_fee'
  AND status = 'success'
  AND deleted_at IS NULL
GROUP BY DATE(paid_at), currency
ORDER BY date DESC;

-- View: Vendor revenue (service payments collected)
CREATE OR REPLACE VIEW vendor_revenue AS
SELECT 
  b.salon_id,
  s.business_name as salon_name,
  DATE(p.paid_at) as date,
  COUNT(*) as transaction_count,
  SUM(p.amount) as total_revenue,
  AVG(p.amount) as avg_transaction,
  p.currency
FROM payments p
JOIN bookings b ON b.id = p.booking_id
JOIN salons s ON s.id = b.salon_id
WHERE p.payment_type = 'service_payment'
  AND p.status = 'success'
  AND p.deleted_at IS NULL
  AND b.deleted_at IS NULL
GROUP BY b.salon_id, s.business_name, DATE(p.paid_at), p.currency
ORDER BY date DESC, salon_name;

-- View: Pending payments (not yet paid)
CREATE OR REPLACE VIEW pending_payments AS
SELECT 
  p.id,
  p.booking_id,
  b.booking_number,
  b.booking_date,
  b.booking_time,
  p.payment_type,
  p.amount,
  p.customer_id,
  prof.full_name as customer_name,
  b.salon_id,
  s.business_name as salon_name,
  p.created_at,
  EXTRACT(EPOCH FROM (now() - p.created_at))/3600 as hours_pending
FROM payments p
JOIN bookings b ON b.id = p.booking_id
JOIN profiles prof ON prof.id = p.customer_id
JOIN salons s ON s.id = b.salon_id
WHERE p.status = 'pending'
  AND p.deleted_at IS NULL
  AND b.deleted_at IS NULL
ORDER BY p.created_at DESC;

-- ============================================================================
-- STEP 5: Add helpful functions
-- ============================================================================

-- Function: Get booking payment status
CREATE OR REPLACE FUNCTION get_booking_payment_status(p_booking_id UUID)
RETURNS TABLE (
  booking_id UUID,
  convenience_fee_paid BOOLEAN,
  service_paid BOOLEAN,
  fully_paid BOOLEAN,
  total_paid NUMERIC,
  total_pending NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    p_booking_id,
    COALESCE(MAX(CASE WHEN payment_type = 'convenience_fee' AND status = 'success' THEN TRUE ELSE FALSE END), FALSE) as convenience_fee_paid,
    COALESCE(MAX(CASE WHEN payment_type = 'service_payment' AND status = 'success' THEN TRUE ELSE FALSE END), FALSE) as service_paid,
    COALESCE(
      MAX(CASE WHEN payment_type = 'convenience_fee' AND status = 'success' THEN TRUE ELSE FALSE END) AND
      MAX(CASE WHEN payment_type = 'service_payment' AND status = 'success' THEN TRUE ELSE FALSE END),
      FALSE
    ) as fully_paid,
    COALESCE(SUM(CASE WHEN status = 'success' THEN amount ELSE 0 END), 0) as total_paid,
    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) as total_pending
  FROM payments
  WHERE booking_id = p_booking_id
    AND deleted_at IS NULL;
END;
$$ LANGUAGE plpgsql;

-- Function: Record service payment at salon
CREATE OR REPLACE FUNCTION record_service_payment(
  p_booking_id UUID,
  p_amount NUMERIC,
  p_payment_method VARCHAR,
  p_recorded_by UUID,
  p_notes TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
  v_payment_id UUID;
  v_customer_id UUID;
BEGIN
  -- Get customer_id from booking
  SELECT customer_id INTO v_customer_id
  FROM bookings
  WHERE id = p_booking_id AND deleted_at IS NULL;
  
  IF v_customer_id IS NULL THEN
    RAISE EXCEPTION 'Booking not found: %', p_booking_id;
  END IF;
  
  -- Insert service payment record
  INSERT INTO payments (
    booking_id,
    customer_id,
    payment_type,
    amount,
    payment_method,
    status,
    paid_at,
    notes,
    created_by,
    updated_by
  ) VALUES (
    p_booking_id,
    v_customer_id,
    'service_payment',
    p_amount,
    p_payment_method,
    'success',
    now(),
    p_notes,
    p_recorded_by,
    p_recorded_by
  )
  RETURNING id INTO v_payment_id;
  
  -- Update deprecated service_paid flag in bookings for backward compatibility
  UPDATE bookings
  SET service_paid = TRUE,
      updated_by = p_recorded_by,
      updated_at = now()
  WHERE id = p_booking_id;
  
  RETURN v_payment_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 6: Table comments
-- ============================================================================

COMMENT ON TABLE payments IS 'Unified payment tracking table. Handles both online convenience fees and at-salon service payments. Replaces booking_payments table.';
COMMENT ON COLUMN payments.payment_type IS 'Type of payment: convenience_fee (online to platform), service_payment (at salon to vendor), refund';
COMMENT ON COLUMN payments.amount IS 'Payment amount in specified currency. For convenience_fee this includes GST.';
COMMENT ON COLUMN payments.razorpay_order_id IS 'Razorpay order ID (only for online payments)';
COMMENT ON COLUMN payments.razorpay_payment_id IS 'Razorpay payment ID (only for online payments, required for success status)';
COMMENT ON COLUMN payments.payment_method IS 'Payment method: razorpay (online), cash, card, upi (at salon)';
COMMENT ON COLUMN payments.status IS 'Payment status: pending (not paid), success (paid), failed (payment failed), refunded (money returned)';

-- ============================================================================
-- STEP 7: Grant necessary permissions
-- ============================================================================

-- Note: Adjust these based on your actual role setup
-- GRANT SELECT, INSERT, UPDATE ON payments TO authenticated;
-- GRANT SELECT ON bookings_with_payments TO authenticated;
-- GRANT SELECT ON platform_revenue TO admin;
-- GRANT SELECT ON vendor_revenue TO authenticated;
-- GRANT SELECT ON pending_payments TO admin;

-- ============================================================================
-- ROLLBACK PLAN (if needed)
-- ============================================================================
-- To rollback this migration:
-- DROP VIEW IF EXISTS pending_payments;
-- DROP VIEW IF EXISTS vendor_revenue;
-- DROP VIEW IF EXISTS platform_revenue;
-- DROP VIEW IF EXISTS bookings_with_payments;
-- DROP FUNCTION IF EXISTS record_service_payment;
-- DROP FUNCTION IF EXISTS get_booking_payment_status;
-- DROP TABLE IF EXISTS payments;
-- 
-- Then restore data:
-- UPDATE booking_payments SET ... (restore from backup)

COMMENT ON TABLE payments IS 'Migration completed: 20251119_refactor_payments. Old booking_payments data migrated successfully.';
