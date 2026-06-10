-- Migration: Fix RM approval-rate calculation (total_salons_added counter)
-- Date: 2026-06-02
-- Purpose:
--   The leaderboard computes approval rate as total_approved_salons / total_salons_added.
--   Previously BOTH counters were incremented only when status = 'approved', so they were
--   always equal and the approval rate was always 100%.
--
--   Correct semantic (matches the live dashboard in rm_service.get_rm_stats):
--     total_salons_added    = ALL vendor requests the RM submitted (any status)
--     total_approved_salons = only approved requests
--   so approval_rate = total_approved_salons / total_salons_added is meaningful.

-- Step 1: Replace the trigger function so total_salons_added counts every submission.
CREATE OR REPLACE FUNCTION update_rm_stats_counters()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- New request added (counts toward total submissions regardless of status)
        UPDATE public.rm_profiles
        SET
            total_requests_count = total_requests_count + 1,
            pending_requests_count = CASE WHEN NEW.status = 'pending' THEN pending_requests_count + 1 ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN NEW.status = 'approved' THEN approved_requests_count + 1 ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1 ELSE rejected_requests_count END,
            -- FIX: total_salons_added now counts ALL submissions (denominator for approval rate)
            total_salons_added = total_salons_added + 1,
            total_approved_salons = CASE WHEN NEW.status = 'approved' THEN total_approved_salons + 1 ELSE total_approved_salons END,
            updated_at = NOW()
        WHERE id = NEW.rm_id;

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Status changed. total_salons_added does NOT change (already counted at submission);
        -- only the approved counters move.
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
                -- FIX: do not change total_salons_added on status transitions
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
            -- FIX: any deleted submission decrements total_salons_added
            total_salons_added = GREATEST(total_salons_added - 1, 0),
            total_approved_salons = CASE WHEN OLD.status = 'approved' THEN GREATEST(total_approved_salons - 1, 0) ELSE total_approved_salons END,
            updated_at = NOW()
        WHERE id = OLD.rm_id;

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Step 2: Backfill existing rows so total_salons_added reflects ALL submissions.
UPDATE public.rm_profiles rm
SET
    total_salons_added = (
        SELECT COUNT(*)
        FROM public.vendor_join_requests
        WHERE rm_id = rm.id
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

COMMENT ON COLUMN public.rm_profiles.total_salons_added IS 'Cached count of ALL vendor requests submitted by the RM (denominator for approval rate)';
COMMENT ON COLUMN public.rm_profiles.total_approved_salons IS 'Cached count of approved vendor requests (numerator for approval rate)';
