-- Fix RLS Policies for vendor_join_requests table
-- This allows RM agents to insert requests and enables realtime for admin panel

-- Drop existing policies if any
DROP POLICY IF EXISTS "Enable realtime for anon" ON public.vendor_join_requests;
DROP POLICY IF EXISTS "RMs can insert own requests" ON public.vendor_join_requests;
DROP POLICY IF EXISTS "RMs can view own requests" ON public.vendor_join_requests;
DROP POLICY IF EXISTS "Admins can view all requests" ON public.vendor_join_requests;
DROP POLICY IF EXISTS "Admins can update requests" ON public.vendor_join_requests;
DROP POLICY IF EXISTS "Service role has full access" ON public.vendor_join_requests;

-- Create comprehensive RLS policies

-- 1. Allow service role (backend) full access
CREATE POLICY "Service role has full access"
ON public.vendor_join_requests
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- 2. Allow authenticated RMs to INSERT their own requests
CREATE POLICY "RMs can insert own requests"
ON public.vendor_join_requests
FOR INSERT
TO authenticated
WITH CHECK (
    -- User must be authenticated
    auth.uid() IS NOT NULL
    AND
    -- User must be an RM (check rm_profiles table)
    EXISTS (
        SELECT 1 FROM public.rm_profiles
        WHERE id = auth.uid() AND is_active = true
    )
    AND
    -- The rm_id in the request must match the authenticated user
    rm_id = auth.uid()
);

-- 3. Allow RMs to SELECT/VIEW their own requests
CREATE POLICY "RMs can view own requests"
ON public.vendor_join_requests
FOR SELECT
TO authenticated
USING (
    auth.uid() = rm_id
    OR
    -- Allow admins to view all
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND role = 'admin'
    )
);

-- 4. Allow admins to view all requests
CREATE POLICY "Admins can view all requests"
ON public.vendor_join_requests
FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND role = 'admin'
    )
);

-- 5. Allow admins to update requests (approve/reject)
CREATE POLICY "Admins can update requests"
ON public.vendor_join_requests
FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND role = 'admin'
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = auth.uid() AND role = 'admin'
    )
);

-- 6. Enable realtime for anon role (for admin panel real-time notifications)
CREATE POLICY "Enable realtime for anon"
ON public.vendor_join_requests
FOR SELECT
TO anon
USING (true);

-- Enable realtime publication for the table (if not already added)
DO $$
BEGIN
    -- Check if table is already in publication
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = 'vendor_join_requests'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.vendor_join_requests;
    END IF;
END $$;

-- Verify policies
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE tablename = 'vendor_join_requests'
ORDER BY policyname;

COMMENT ON TABLE public.vendor_join_requests IS 'Salon submission requests from RM agents. RLS policies ensure RMs can only insert/view their own requests, and admins can view/update all.';
