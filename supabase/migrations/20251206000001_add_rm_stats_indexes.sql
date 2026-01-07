-- Migration: Add indexes for efficient RM statistics queries
-- Date: 2025-12-06
-- Purpose: Optimize vendor_join_requests queries for RM dashboard statistics
-- Performance: Enables O(1) COUNT queries instead of O(n) full table scans

-- Add composite index for counting requests by RM and status
CREATE INDEX IF NOT EXISTS idx_vendor_join_requests_rm_status 
ON public.vendor_join_requests(rm_id, status);

-- Add index for counting total requests per RM
CREATE INDEX IF NOT EXISTS idx_vendor_join_requests_rm_id 
ON public.vendor_join_requests(rm_id);

-- Add index for RM dashboard queries (frequently accessed)
CREATE INDEX IF NOT EXISTS idx_vendor_join_requests_rm_created 
ON public.vendor_join_requests(rm_id, created_at DESC);

COMMENT ON INDEX idx_vendor_join_requests_rm_status IS 'Optimizes COUNT queries for RM statistics by status';
COMMENT ON INDEX idx_vendor_join_requests_rm_id IS 'Optimizes COUNT queries for total RM requests';
COMMENT ON INDEX idx_vendor_join_requests_rm_created IS 'Optimizes recent requests queries for RM dashboard';
