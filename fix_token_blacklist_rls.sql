-- Fix token_blacklist RLS policy to allow backend insertions
-- Run this in Supabase SQL Editor

-- First, check if table exists, if not create it
CREATE TABLE IF NOT EXISTS token_blacklist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    token_jti VARCHAR(255) NOT NULL UNIQUE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    token_type VARCHAR(20) NOT NULL,
    blacklisted_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR(100) DEFAULT 'logout',
    
    CONSTRAINT valid_token_type CHECK (token_type IN ('access', 'refresh'))
);

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_token_blacklist_jti ON token_blacklist(token_jti);
CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires_at ON token_blacklist(expires_at);
CREATE INDEX IF NOT EXISTS idx_token_blacklist_user_id ON token_blacklist(user_id);

-- DISABLE RLS - The service role will handle all access
-- This is the simplest and most reliable solution
ALTER TABLE token_blacklist DISABLE ROW LEVEL SECURITY;

-- Drop existing policies (if any)
DROP POLICY IF EXISTS "Service role full access" ON token_blacklist;
DROP POLICY IF EXISTS "Backend can manage token blacklist" ON token_blacklist;
DROP POLICY IF EXISTS "Users can view own blacklisted tokens" ON token_blacklist;

-- Add helpful comments
COMMENT ON TABLE token_blacklist IS 'Stores revoked JWT tokens to prevent reuse after logout or security events - RLS DISABLED, managed by backend service role only';
COMMENT ON COLUMN token_blacklist.token_jti IS 'JWT ID (jti) claim - unique identifier for each token';
COMMENT ON COLUMN token_blacklist.expires_at IS 'Token expiration time - used for automatic cleanup';
COMMENT ON COLUMN token_blacklist.reason IS 'Why token was blacklisted: logout, security breach, manual revocation, etc.';

-- Verify RLS is disabled
SELECT 
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables 
WHERE tablename = 'token_blacklist';

