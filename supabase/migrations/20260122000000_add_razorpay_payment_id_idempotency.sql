-- Migration: Add razorpay_payment_id to bookings table for idempotency
-- Purpose: Prevent duplicate booking creation from the same payment
-- Date: 2026-01-22

-- =====================================================
-- CONSTRAINT 1: Prevent duplicate bookings from same payment
-- =====================================================

-- Add razorpay_payment_id column to bookings table
ALTER TABLE bookings 
ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT;

-- Add comment to explain the column's purpose
COMMENT ON COLUMN bookings.razorpay_payment_id IS 'Razorpay payment ID used for this booking. Used for idempotency checks to prevent duplicate bookings from the same payment.';

-- Create unique constraint to enforce idempotency
-- This ensures that the same payment_id cannot be used for multiple bookings
-- Allows NULL values (for bookings without Razorpay payments)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'unique_razorpay_payment'
    ) THEN
        ALTER TABLE bookings 
        ADD CONSTRAINT unique_razorpay_payment 
        UNIQUE(razorpay_payment_id);
    END IF;
END $$;

-- Add index for faster lookups during idempotency checks
CREATE INDEX IF NOT EXISTS idx_bookings_razorpay_payment_id 
ON bookings(razorpay_payment_id)
WHERE razorpay_payment_id IS NOT NULL;

-- Add comment to explain the idempotency pattern
COMMENT ON CONSTRAINT unique_razorpay_payment ON bookings IS 'Enforces idempotency: prevents duplicate bookings from the same Razorpay payment. Protects against network retries and double-clicks.';

-- =====================================================
-- CONSTRAINT 2: Prevent duplicate payment records for same booking
-- =====================================================

-- Ensure each booking has only one payment record per payment_type
-- Example: Only one "convenience_fee" payment and one "service_payment" per booking
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'unique_booking_payment_type'
    ) THEN
        ALTER TABLE payments 
        ADD CONSTRAINT unique_booking_payment_type 
        UNIQUE(booking_id, payment_type);
    END IF;
END $$;

-- Add comment to explain this constraint
COMMENT ON CONSTRAINT unique_booking_payment_type ON payments IS 'Ensures each booking has only one payment record per payment_type (e.g., one convenience_fee, one service_payment). Prevents duplicate payment records.';
