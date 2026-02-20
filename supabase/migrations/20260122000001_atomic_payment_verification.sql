-- ============================================================================
-- ATOMIC PAYMENT VERIFICATION - Transaction Safety
-- ============================================================================
-- Creates database function to verify payment and update booking atomically
-- Fixes data consistency issue where payment is marked complete but booking
-- remains pending if server crashes between the two updates.
--
-- Problem:
--   Step 1: UPDATE payments SET status='completed'  ✅ COMMITTED
--   ⚠️ CRASH HERE
--   Step 2: UPDATE bookings SET status='confirmed'  ❌ NEVER RUNS
--   Result: Payment completed but booking still pending!
--
-- Solution:
--   Wrap both updates in a database transaction (atomic operation)
--   Both succeed together or both fail together - no partial state
-- ============================================================================

CREATE OR REPLACE FUNCTION verify_payment_and_confirm_booking(
    p_razorpay_order_id VARCHAR,
    p_razorpay_payment_id VARCHAR,
    p_razorpay_signature VARCHAR
)
RETURNS TABLE (
    success BOOLEAN,
    payment_id VARCHAR,
    booking_id UUID,
    salon_name VARCHAR,
    booking_date DATE,
    time_slots TEXT[],
    amount_paid NUMERIC,
    was_already_verified BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER -- Run with elevated privileges
AS $$
DECLARE
    v_payment_record RECORD;
    v_booking_record RECORD;
    v_updated_rows INTEGER;
BEGIN
    -- ========================================================================
    -- STEP 1: Fetch payment and booking data (with lock to prevent race conditions)
    -- ========================================================================
    SELECT 
        bp.*,
        b.id as booking_id,
        b.customer_id as booking_customer_id,
        b.booking_date,
        b.time_slots,
        s.business_name as salon_name
    INTO v_payment_record
    FROM booking_payments bp
    INNER JOIN bookings b ON b.id = bp.booking_id
    INNER JOIN salons s ON s.id = b.salon_id
    WHERE bp.razorpay_order_id = p_razorpay_order_id
    FOR UPDATE OF bp; -- Lock the payment row to prevent concurrent modifications
    
    -- Check if payment exists
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Payment record not found for order_id: %', p_razorpay_order_id;
    END IF;
    
    -- ========================================================================
    -- STEP 2: Check if payment is already verified (idempotency)
    -- ========================================================================
    IF v_payment_record.status = 'completed' THEN
        -- Payment already processed, return existing data (idempotent response)
        RETURN QUERY SELECT 
            TRUE as success,
            v_payment_record.razorpay_payment_id::VARCHAR as payment_id,
            v_payment_record.booking_id::UUID,
            v_payment_record.salon_name::VARCHAR,
            v_payment_record.booking_date::DATE,
            v_payment_record.time_slots::TEXT[],
            v_payment_record.amount::NUMERIC,
            TRUE as was_already_verified;
        RETURN;
    END IF;
    
    -- ========================================================================
    -- STEP 3: ATOMIC UPDATE - Both updates happen in same transaction
    -- ========================================================================
    -- This is the key fix: Both updates are wrapped in a single transaction
    -- If anything fails, both updates are rolled back automatically
    -- PostgreSQL guarantees atomicity (all-or-nothing)
    
    -- Update 1: Mark payment as completed
    UPDATE booking_payments
    SET 
        razorpay_payment_id = p_razorpay_payment_id,
        razorpay_signature = p_razorpay_signature,
        status = 'completed',
        payment_completed_at = now(),
        updated_at = now()
    WHERE razorpay_order_id = p_razorpay_order_id
      AND status = 'pending'; -- Only update if still pending (optimistic lock)
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    -- Check if update succeeded (race condition check)
    IF v_updated_rows = 0 THEN
        -- Another request already processed this payment
        -- Re-fetch the completed payment data
        SELECT 
            bp.*,
            b.id as booking_id,
            b.booking_date,
            b.time_slots,
            s.business_name as salon_name
        INTO v_payment_record
        FROM booking_payments bp
        INNER JOIN bookings b ON b.id = bp.booking_id
        INNER JOIN salons s ON s.id = b.salon_id
        WHERE bp.razorpay_order_id = p_razorpay_order_id;
        
        RETURN QUERY SELECT 
            TRUE as success,
            v_payment_record.razorpay_payment_id::VARCHAR as payment_id,
            v_payment_record.booking_id::UUID,
            v_payment_record.salon_name::VARCHAR,
            v_payment_record.booking_date::DATE,
            v_payment_record.time_slots::TEXT[],
            v_payment_record.amount::NUMERIC,
            TRUE as was_already_verified;
        RETURN;
    END IF;
    
    -- Update 2: Mark booking as confirmed
    -- This happens in the SAME transaction as Update 1
    -- If this fails, Update 1 is automatically rolled back!
    UPDATE bookings
    SET 
        convenience_fee_paid = TRUE,
        status = 'confirmed',
        confirmed_at = now(),
        updated_at = now()
    WHERE id = v_payment_record.booking_id;
    
    -- ========================================================================
    -- STEP 4: Return success response
    -- ========================================================================
    -- Transaction commits automatically when function returns successfully
    RETURN QUERY SELECT 
        TRUE as success,
        p_razorpay_payment_id::VARCHAR as payment_id,
        v_payment_record.booking_id::UUID,
        v_payment_record.salon_name::VARCHAR,
        v_payment_record.booking_date::DATE,
        v_payment_record.time_slots::TEXT[],
        v_payment_record.amount::NUMERIC,
        FALSE as was_already_verified;
    
EXCEPTION
    WHEN OTHERS THEN
        -- Any error automatically rolls back BOTH updates
        -- This ensures data consistency
        RAISE EXCEPTION 'Payment verification failed: %', SQLERRM;
END;
$$;

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================
-- Allow authenticated users to call this function
GRANT EXECUTE ON FUNCTION verify_payment_and_confirm_booking TO authenticated;
GRANT EXECUTE ON FUNCTION verify_payment_and_confirm_booking TO service_role;

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON FUNCTION verify_payment_and_confirm_booking IS 
'Atomically verifies payment and confirms booking in a single transaction.
Prevents data inconsistency where payment is marked complete but booking remains pending.
Implements idempotency and race condition protection.';
