-- ============================================================================
-- PAYMENTS TABLE RLS POLICIES
-- ============================================================================
-- Add Row Level Security policies for payments table to allow proper access
-- for customers, vendors, and admins

-- Drop existing policies if any
DROP POLICY IF EXISTS "payments_insert_for_authenticated" ON payments;
DROP POLICY IF EXISTS "payments_select_own" ON payments;
DROP POLICY IF EXISTS "payments_select_vendor" ON payments;
DROP POLICY IF EXISTS "payments_update_own" ON payments;
DROP POLICY IF EXISTS "payments_admin_all" ON payments;

-- ============================================================================
-- INSERT POLICIES
-- ============================================================================

-- Allow authenticated users to insert their own payment records
-- Used when creating bookings with payment
CREATE POLICY "payments_insert_for_authenticated"
ON payments
FOR INSERT
TO authenticated
WITH CHECK (
  customer_id = auth.uid()
);

-- ============================================================================
-- SELECT POLICIES
-- ============================================================================

-- Customers can view their own payments
CREATE POLICY "payments_select_own"
ON payments
FOR SELECT
TO authenticated
USING (
  customer_id = auth.uid()
  AND deleted_at IS NULL
);

-- Vendors can view payments for their salon's bookings
CREATE POLICY "payments_select_vendor"
ON payments
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM bookings b
    JOIN salons s ON b.salon_id = s.id
    WHERE b.id = payments.booking_id
    AND s.vendor_id = auth.uid()
    AND payments.deleted_at IS NULL
  )
);

-- Admins can view all payments
CREATE POLICY "payments_select_admin"
ON payments
FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM profiles
    WHERE profiles.id = auth.uid()
    AND profiles.user_role = 'admin'
  )
  AND deleted_at IS NULL
);

-- ============================================================================
-- UPDATE POLICIES
-- ============================================================================

-- Vendors can update service_payment status for their bookings
CREATE POLICY "payments_update_vendor"
ON payments
FOR UPDATE
TO authenticated
USING (
  payment_type = 'service_payment'
  AND EXISTS (
    SELECT 1 FROM bookings b
    JOIN salons s ON b.salon_id = s.id
    WHERE b.id = payments.booking_id
    AND s.vendor_id = auth.uid()
  )
  AND deleted_at IS NULL
)
WITH CHECK (
  payment_type = 'service_payment'
  AND EXISTS (
    SELECT 1 FROM bookings b
    JOIN salons s ON b.salon_id = s.id
    WHERE b.id = payments.booking_id
    AND s.vendor_id = auth.uid()
  )
  AND deleted_at IS NULL
);

-- Admins can update any payment
CREATE POLICY "payments_update_admin"
ON payments
FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM profiles
    WHERE profiles.id = auth.uid()
    AND profiles.user_role = 'admin'
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM profiles
    WHERE profiles.id = auth.uid()
    AND profiles.user_role = 'admin'
  )
);

-- ============================================================================
-- DELETE POLICIES (Soft delete only)
-- ============================================================================

-- Only admins can soft delete payments
CREATE POLICY "payments_delete_admin"
ON payments
FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM profiles
    WHERE profiles.id = auth.uid()
    AND profiles.user_role = 'admin'
  )
)
WITH CHECK (
  deleted_at IS NOT NULL
);

COMMENT ON TABLE payments IS 'RLS policies added: customers can insert/view own, vendors can view/update salon payments, admins have full access';
