-- =====================================================
-- BACKFILL SALON JOIN_REQUEST_ID
-- =====================================================
-- Description: Update existing salons with their corresponding join_request_id
-- This links salons to their original vendor_join_request for payment processing
-- Created: 2026-01-19
-- =====================================================

-- Update salons that don't have join_request_id by matching with vendor_join_requests
-- Match criteria: business_name, phone, email, city, state
UPDATE public.salons s
SET 
    join_request_id = vjr.id,
    updated_at = now()
FROM public.vendor_join_requests vjr
WHERE 
    s.join_request_id IS NULL
    AND vjr.status = 'approved'
    AND s.business_name = vjr.business_name
    AND s.phone = vjr.owner_phone
    AND s.email = vjr.owner_email
    AND s.city = vjr.city
    AND s.state = vjr.state
    AND s.deleted_at IS NULL;

-- Add comment
COMMENT ON COLUMN public.salons.join_request_id IS 'Original vendor join request that led to this salon creation (required for payment processing)';
