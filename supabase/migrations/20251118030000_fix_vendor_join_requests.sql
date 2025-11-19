-- =====================================================
-- FIX VENDOR_JOIN_REQUESTS TABLE
-- =====================================================
-- Restores original comprehensive structure + additions
-- Based on old working schema with modern improvements
-- =====================================================

-- Drop existing incomplete table
DROP TABLE IF EXISTS public.vendor_join_requests CASCADE;

-- Recreate with proper structure
CREATE TABLE public.vendor_join_requests (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rm_id UUID NOT NULL REFERENCES rm_profiles(id) ON DELETE CASCADE,
    
    -- Business Info
    business_name VARCHAR(255) NOT NULL,
    business_type VARCHAR(50) NOT NULL, -- 'salon', 'spa', 'unisex_salon', 'barber_shop', etc.
    owner_name VARCHAR(255) NOT NULL,
    owner_email VARCHAR(255) NOT NULL,
    owner_phone VARCHAR(20) NOT NULL,
    
    -- Location
    business_address TEXT NOT NULL, -- Full address string
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    pincode VARCHAR(10) NOT NULL,
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    
    -- Legal & Compliance
    gst_number VARCHAR(50),
    pan_number VARCHAR(10), -- NEW: Tax compliance
    business_license TEXT, -- Document URL
    registration_certificate TEXT, -- NEW: Legal document URL
    documents JSONB, -- Additional documents {doc_type: url}
    
    -- Media (NEW)
    cover_image_url TEXT,
    gallery_images TEXT[], -- Array of image URLs
    
    -- Operations (NEW)
    services_offered JSONB, -- {category_id: [service_names], ...}
    staff_count INTEGER DEFAULT 1,
    opening_time TIME,
    closing_time TIME,
    working_days TEXT[], -- ['Monday', 'Tuesday', ...]
    
    -- Workflow
    status request_status NOT NULL DEFAULT 'pending',
    submitted_at TIMESTAMPTZ, -- NEW: When actually submitted (vs created_at for drafts)
    
    -- Review
    admin_notes TEXT,
    approval_notes TEXT, -- NEW: Why approved
    rejection_reason TEXT, -- NEW: Separate from admin_notes
    reviewed_by UUID REFERENCES auth.users(id),
    reviewed_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Constraints
    CONSTRAINT valid_status CHECK (
        status = ANY (
            ARRAY['draft'::request_status, 'pending'::request_status, 
                  'approved'::request_status, 'rejected'::request_status]
        )
    ),
    CONSTRAINT valid_pincode CHECK (pincode ~ '^\d{6}$' OR pincode ~ '^\d{10}$'),
    CONSTRAINT valid_gst CHECK (gst_number IS NULL OR gst_number ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'),
    CONSTRAINT valid_pan CHECK (pan_number IS NULL OR pan_number ~ '^[A-Z]{5}[0-9]{4}[A-Z]{1}$'),
    CONSTRAINT valid_coordinates CHECK (
        (latitude IS NULL AND longitude IS NULL) OR 
        (latitude IS NOT NULL AND longitude IS NOT NULL)
    )
);

-- Indexes for performance
CREATE INDEX idx_vendor_requests_rm_id ON vendor_join_requests(rm_id);
CREATE INDEX idx_vendor_requests_status ON vendor_join_requests(status);
CREATE INDEX idx_vendor_requests_status_draft ON vendor_join_requests(status) 
    WHERE status = 'draft'::request_status;
CREATE INDEX idx_vendor_requests_reviewed_by ON vendor_join_requests(reviewed_by);
CREATE INDEX idx_vendor_requests_location ON vendor_join_requests(city, state) 
    WHERE status = 'approved';
CREATE INDEX idx_vendor_requests_submitted ON vendor_join_requests(submitted_at DESC) 
    WHERE submitted_at IS NOT NULL;

-- Trigger for updated_at
CREATE TRIGGER set_vendor_requests_updated_at
    BEFORE UPDATE ON vendor_join_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- RLS Policies
ALTER TABLE vendor_join_requests ENABLE ROW LEVEL SECURITY;

-- RMs can create and view their own requests
CREATE POLICY "RMs can create vendor requests"
    ON vendor_join_requests FOR INSERT
    WITH CHECK (
        rm_id IN (
            SELECT id FROM rm_profiles WHERE id = auth.uid()
        )
    );

CREATE POLICY "RMs can view own requests"
    ON vendor_join_requests FOR SELECT
    USING (
        rm_id IN (
            SELECT id FROM rm_profiles WHERE id = auth.uid()
        )
    );

CREATE POLICY "RMs can update own draft requests"
    ON vendor_join_requests FOR UPDATE
    USING (
        rm_id IN (
            SELECT id FROM rm_profiles WHERE id = auth.uid()
        )
        AND status = 'draft'::request_status
    );

CREATE POLICY "RMs can delete own draft requests"
    ON vendor_join_requests FOR DELETE
    USING (
        rm_id IN (
            SELECT id FROM rm_profiles WHERE id = auth.uid()
        )
        AND status = 'draft'::request_status
    );

-- Admins can view and manage all requests
CREATE POLICY "Admins can view all requests"
    ON vendor_join_requests FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE profiles.id = auth.uid() 
            AND profiles.user_role = 'admin'::user_role
        )
    );

CREATE POLICY "Admins can update requests"
    ON vendor_join_requests FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM profiles 
            WHERE profiles.id = auth.uid() 
            AND profiles.user_role = 'admin'::user_role
        )
    );

-- Comment for documentation
COMMENT ON TABLE vendor_join_requests IS 'RM-submitted salon onboarding requests with comprehensive business details for admin approval';
COMMENT ON COLUMN vendor_join_requests.rm_id IS 'Relationship Manager who submitted this request';
COMMENT ON COLUMN vendor_join_requests.submitted_at IS 'When request was submitted (NULL for drafts)';
COMMENT ON COLUMN vendor_join_requests.documents IS 'Additional documents as JSONB: {doc_type: storage_url, ...}';
COMMENT ON COLUMN vendor_join_requests.services_offered IS 'Services as JSONB: {category_id: [service_names], ...}';
