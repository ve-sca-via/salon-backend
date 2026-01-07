-- Migration: Add cached counters and triggers for RM statistics (Phase 2)
-- Date: 2025-12-06
-- Purpose: Add denormalized counter columns with auto-update triggers for O(1) dashboard queries
-- Note: This is an optional optimization. Phase 1 (database aggregation) provides good performance.
-- Deploy this if you need maximum performance with RMs having 100+ requests

-- Step 1: Add counter columns to rm_profiles
ALTER TABLE public.rm_profiles 
ADD COLUMN IF NOT EXISTS total_requests_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS pending_requests_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS approved_requests_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS rejected_requests_count INTEGER DEFAULT 0;

COMMENT ON COLUMN public.rm_profiles.total_requests_count IS 'Cached count of all vendor requests (auto-updated by trigger)';
COMMENT ON COLUMN public.rm_profiles.pending_requests_count IS 'Cached count of pending requests (auto-updated by trigger)';
COMMENT ON COLUMN public.rm_profiles.approved_requests_count IS 'Cached count of approved requests (auto-updated by trigger)';
COMMENT ON COLUMN public.rm_profiles.rejected_requests_count IS 'Cached count of rejected requests (auto-updated by trigger)';

-- Step 2: Create trigger function to auto-update counters
CREATE OR REPLACE FUNCTION update_rm_stats_counters()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- New request added
        UPDATE public.rm_profiles 
        SET 
            total_requests_count = total_requests_count + 1,
            pending_requests_count = CASE WHEN NEW.status = 'pending' THEN pending_requests_count + 1 ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN NEW.status = 'approved' THEN approved_requests_count + 1 ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1 ELSE rejected_requests_count END,
            total_salons_added = CASE WHEN NEW.status = 'approved' THEN total_salons_added + 1 ELSE total_salons_added END,
            total_approved_salons = CASE WHEN NEW.status = 'approved' THEN total_approved_salons + 1 ELSE total_approved_salons END,
            updated_at = NOW()
        WHERE id = NEW.rm_id;
        
        RETURN NEW;
        
    ELSIF TG_OP = 'UPDATE' THEN
        -- Status changed
        IF OLD.status IS DISTINCT FROM NEW.status THEN
            UPDATE public.rm_profiles 
            SET 
                pending_requests_count = CASE 
                    WHEN OLD.status = 'pending' THEN pending_requests_count - 1 
                    WHEN NEW.status = 'pending' THEN pending_requests_count + 1 
                    ELSE pending_requests_count 
                END,
                approved_requests_count = CASE 
                    WHEN OLD.status = 'approved' THEN approved_requests_count - 1 
                    WHEN NEW.status = 'approved' THEN approved_requests_count + 1 
                    ELSE approved_requests_count 
                END,
                rejected_requests_count = CASE 
                    WHEN OLD.status = 'rejected' THEN rejected_requests_count - 1 
                    WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1 
                    ELSE rejected_requests_count 
                END,
                total_salons_added = CASE 
                    WHEN OLD.status != 'approved' AND NEW.status = 'approved' THEN total_salons_added + 1 
                    WHEN OLD.status = 'approved' AND NEW.status != 'approved' THEN total_salons_added - 1 
                    ELSE total_salons_added 
                END,
                total_approved_salons = CASE 
                    WHEN OLD.status != 'approved' AND NEW.status = 'approved' THEN total_approved_salons + 1 
                    WHEN OLD.status = 'approved' AND NEW.status != 'approved' THEN total_approved_salons - 1 
                    ELSE total_approved_salons 
                END,
                updated_at = NOW()
            WHERE id = NEW.rm_id;
        END IF;
        
        RETURN NEW;
        
    ELSIF TG_OP = 'DELETE' THEN
        -- Request deleted (soft or hard delete)
        UPDATE public.rm_profiles 
        SET 
            total_requests_count = GREATEST(total_requests_count - 1, 0),
            pending_requests_count = CASE WHEN OLD.status = 'pending' THEN GREATEST(pending_requests_count - 1, 0) ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN OLD.status = 'approved' THEN GREATEST(approved_requests_count - 1, 0) ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN OLD.status = 'rejected' THEN GREATEST(rejected_requests_count - 1, 0) ELSE rejected_requests_count END,
            total_salons_added = CASE WHEN OLD.status = 'approved' THEN GREATEST(total_salons_added - 1, 0) ELSE total_salons_added END,
            total_approved_salons = CASE WHEN OLD.status = 'approved' THEN GREATEST(total_approved_salons - 1, 0) ELSE total_approved_salons END,
            updated_at = NOW()
        WHERE id = OLD.rm_id;
        
        RETURN OLD;
    END IF;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_rm_stats_counters IS 'Auto-updates RM statistics counters when vendor requests are inserted, updated, or deleted';

-- Step 3: Create trigger
DROP TRIGGER IF EXISTS trigger_update_rm_stats ON public.vendor_join_requests;
CREATE TRIGGER trigger_update_rm_stats
AFTER INSERT OR UPDATE OF status OR DELETE ON public.vendor_join_requests
FOR EACH ROW
EXECUTE FUNCTION update_rm_stats_counters();

COMMENT ON TRIGGER trigger_update_rm_stats ON public.vendor_join_requests IS 'Maintains real-time RM statistics counters';

-- Step 4: Initial sync of existing data
-- This ensures counters match current data before trigger takes over
UPDATE public.rm_profiles rm
SET 
    total_requests_count = (
        SELECT COUNT(*) 
        FROM public.vendor_join_requests 
        WHERE rm_id = rm.id
    ),
    pending_requests_count = (
        SELECT COUNT(*) 
        FROM public.vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'pending'
    ),
    approved_requests_count = (
        SELECT COUNT(*) 
        FROM public.vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'approved'
    ),
    rejected_requests_count = (
        SELECT COUNT(*) 
        FROM public.vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'rejected'
    ),
    total_salons_added = (
        SELECT COUNT(*) 
        FROM public.vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'approved'
    ),
    total_approved_salons = (
        SELECT COUNT(*) 
        FROM public.vendor_join_requests 
        WHERE rm_id = rm.id AND status = 'approved'
    ),
    updated_at = NOW()
WHERE EXISTS (
    SELECT 1 FROM public.vendor_join_requests WHERE rm_id = rm.id
);

-- Step 5: Add constraints to prevent negative counts
ALTER TABLE public.rm_profiles 
ADD CONSTRAINT check_total_requests_count_non_negative CHECK (total_requests_count >= 0),
ADD CONSTRAINT check_pending_requests_count_non_negative CHECK (pending_requests_count >= 0),
ADD CONSTRAINT check_approved_requests_count_non_negative CHECK (approved_requests_count >= 0),
ADD CONSTRAINT check_rejected_requests_count_non_negative CHECK (rejected_requests_count >= 0);

-- Step 6: Create validation function (optional - for data integrity checks)
CREATE OR REPLACE FUNCTION validate_rm_stats_counters(p_rm_id UUID)
RETURNS TABLE(
    counter_name TEXT,
    cached_value INTEGER,
    actual_value BIGINT,
    is_valid BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'total_requests_count'::TEXT,
        rm.total_requests_count,
        COUNT(*)::BIGINT,
        rm.total_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.total_requests_count
    
    UNION ALL
    
    SELECT 
        'pending_requests_count'::TEXT,
        rm.pending_requests_count,
        COUNT(*)::BIGINT,
        rm.pending_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.status = 'pending' AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.pending_requests_count
    
    UNION ALL
    
    SELECT 
        'approved_requests_count'::TEXT,
        rm.approved_requests_count,
        COUNT(*)::BIGINT,
        rm.approved_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.status = 'approved' AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.approved_requests_count
    
    UNION ALL
    
    SELECT 
        'rejected_requests_count'::TEXT,
        rm.rejected_requests_count,
        COUNT(*)::BIGINT,
        rm.rejected_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.status = 'rejected' AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.rejected_requests_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_rm_stats_counters IS 'Validates cached RM statistics match actual database counts (for debugging)';

-- Example usage: SELECT * FROM validate_rm_stats_counters('rm-uuid-here');
