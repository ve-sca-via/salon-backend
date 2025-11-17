    -- ============================================================================
    -- FIX: Remove infinite recursion in RLS policies
    -- ============================================================================
    -- The "Admins can manage all profiles" policy causes infinite recursion
    -- because it queries the profiles table FROM WITHIN a profiles policy.
    -- 
    -- Solution: Drop this policy. Admins should use service_role_key which
    -- bypasses RLS entirely for admin operations.

    DROP POLICY IF EXISTS "Admins can manage all profiles" ON profiles;

    -- Note: Admin operations should be performed server-side using the
    -- service_role_key, which bypasses RLS. Client-side admin panels
    -- should call backend API endpoints that use service_role credentials.
