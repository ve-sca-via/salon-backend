-- Create partner_requests table
-- Purpose: capture basic information from vendors who want to onboard ("Partner with us")
-- Submitted publicly from the marketing site; reviewed by admins in the admin portal.
CREATE TABLE IF NOT EXISTS public.partner_requests (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Basic Vendor Information
    owner_name TEXT NOT NULL,
    shop_name TEXT NOT NULL,
    shop_type TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    location TEXT NOT NULL,

    -- Request Status / Admin Review
    status TEXT NOT NULL DEFAULT 'new',
    admin_notes TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common admin queries
CREATE INDEX IF NOT EXISTS idx_partner_requests_status ON public.partner_requests(status);
CREATE INDEX IF NOT EXISTS idx_partner_requests_email ON public.partner_requests(email);
CREATE INDEX IF NOT EXISTS idx_partner_requests_created_at ON public.partner_requests(created_at DESC);

-- Constraint for valid status values
ALTER TABLE public.partner_requests
ADD CONSTRAINT partner_requests_valid_status CHECK (
    status IN ('new', 'contacted', 'approved', 'rejected')
);

-- Reuse the shared updated_at trigger function if it exists, otherwise create one
CREATE OR REPLACE FUNCTION update_partner_requests_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_partner_requests_updated_at
    BEFORE UPDATE ON public.partner_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_partner_requests_updated_at();

-- Enable Row Level Security (RLS)
ALTER TABLE public.partner_requests ENABLE ROW LEVEL SECURITY;

-- Policy: Allow public to insert (submit partner requests)
CREATE POLICY "Anyone can submit partner requests"
    ON public.partner_requests
    FOR INSERT
    TO public
    WITH CHECK (true);

-- Policy: Allow admins to view all partner requests
CREATE POLICY "Admins can view all partner requests"
    ON public.partner_requests
    FOR SELECT
    TO authenticated
    USING (
        auth.jwt() ->> 'role' = 'admin'
    );

-- Policy: Allow admins to update partner requests
CREATE POLICY "Admins can update partner requests"
    ON public.partner_requests
    FOR UPDATE
    TO authenticated
    USING (
        auth.jwt() ->> 'role' = 'admin'
    );

-- Policy: Allow admins to delete partner requests
CREATE POLICY "Admins can delete partner requests"
    ON public.partner_requests
    FOR DELETE
    TO authenticated
    USING (
        auth.jwt() ->> 'role' = 'admin'
    );

COMMENT ON TABLE public.partner_requests IS 'Stores "Partner with us" onboarding inquiries from prospective vendors';
