-- Fix activity_logs table to allow inserts
-- The original migration only had SELECT policy, blocking all inserts

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Admins can view all activity logs" ON activity_logs;

-- Recreate SELECT policy
CREATE POLICY "Admins can view all activity logs"
    ON activity_logs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid()
            AND profiles.user_role = 'admin'
        )
    );

-- Add INSERT policy - Allow service role to insert (for backend logging)
CREATE POLICY "Service role can insert activity logs"
    ON activity_logs
    FOR INSERT
    WITH CHECK (true);

-- Add comment explaining the policy
COMMENT ON POLICY "Service role can insert activity logs" ON activity_logs IS 
    'Allows backend service (using service role key) to insert activity logs for audit trail';
