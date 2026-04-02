-- Create OTP attempts tracking table for rate limiting and security
-- Migration: 20260401191458_create_otp_attempts_table

-- Purpose: Track OTP attempts to prevent brute-force attacks and abuse
-- Features:
-- - Track OTP send attempts (rate limiting)
-- - Track OTP verification attempts (prevent brute force)
-- - Block phone numbers after too many failed attempts
-- - Auto-cleanup old records (TTL)

CREATE TABLE IF NOT EXISTS public.otp_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    country_code VARCHAR(5) DEFAULT '91',
    verification_id VARCHAR(255),

    -- Attempt tracking
    send_attempts INT DEFAULT 0,
    verify_attempts INT DEFAULT 0,
    last_send_at TIMESTAMP WITH TIME ZONE,
    last_verify_at TIMESTAMP WITH TIME ZONE,

    -- Security: Block after too many failures
    blocked_until TIMESTAMP WITH TIME ZONE,
    blocked_reason VARCHAR(100),

    -- Success tracking
    last_success_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    ip_address VARCHAR(45),  -- Support IPv6
    user_agent TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for efficient lookups
-- Simple index on phone for quick lookups (blocked_until check done in query)
CREATE INDEX idx_otp_attempts_phone ON public.otp_attempts(phone);

-- Index on phone + blocked_until for unblocked phone queries
CREATE INDEX idx_otp_attempts_phone_blocked ON public.otp_attempts(phone, blocked_until);

-- Partial index for verification_id (only when not NULL)
CREATE INDEX idx_otp_attempts_verification_id ON public.otp_attempts(verification_id)
WHERE verification_id IS NOT NULL;

-- Index for time-based queries and cleanup
CREATE INDEX idx_otp_attempts_created_at ON public.otp_attempts(created_at);

-- Row Level Security (RLS)
-- Since this is internal tracking, disable RLS (service role only)
ALTER TABLE public.otp_attempts ENABLE ROW LEVEL SECURITY;

-- Service role bypass (already has full access)
CREATE POLICY "Service role can manage otp_attempts" ON public.otp_attempts
    FOR ALL
    USING (
        auth.jwt() ->> 'role' = 'service_role'
    );

-- Documentation
COMMENT ON TABLE public.otp_attempts IS
'Tracks OTP send and verification attempts for rate limiting and security. Auto-cleanup records older than 7 days.';

COMMENT ON COLUMN public.otp_attempts.phone IS
'Phone number in E.164 format (e.g., +919876543210)';

COMMENT ON COLUMN public.otp_attempts.send_attempts IS
'Number of OTP send attempts (reset after successful verification or timeout)';

COMMENT ON COLUMN public.otp_attempts.verify_attempts IS
'Number of OTP verification attempts (max 5 before blocking)';

COMMENT ON COLUMN public.otp_attempts.blocked_until IS
'Timestamp until phone is blocked from OTP requests. NULL = not blocked.';

-- Function to cleanup old OTP attempts (run daily via cron)
CREATE OR REPLACE FUNCTION cleanup_old_otp_attempts()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM public.otp_attempts
    WHERE created_at < NOW() - INTERVAL '7 days';

    RAISE NOTICE 'Cleaned up old OTP attempts';
END;
$$;

COMMENT ON FUNCTION cleanup_old_otp_attempts IS
'Cleanup OTP attempts older than 7 days. Should be run daily via cron job.';
