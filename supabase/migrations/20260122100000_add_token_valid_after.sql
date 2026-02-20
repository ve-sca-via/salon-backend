-- Add token_valid_after column for efficient logout_all implementation
-- Migration: 20260122100000_add_token_valid_after

-- Strategy: Instead of blacklisting every token (inefficient and incomplete),
-- we add a timestamp column. When user clicks "Logout All", we update this timestamp.
-- During token verification, if token.issued_at < user.token_valid_after, reject the token.
-- This invalidates ALL tokens issued before the logout_all action.

-- Add token_valid_after column (nullable - NULL means no logout_all has been performed)
ALTER TABLE public.profiles 
ADD COLUMN token_valid_after TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Create index for efficient lookup during token verification
CREATE INDEX idx_profiles_token_valid_after 
ON public.profiles(id, token_valid_after) 
WHERE token_valid_after IS NOT NULL;

-- Add documentation
COMMENT ON COLUMN public.profiles.token_valid_after IS 
'Timestamp that invalidates all tokens issued before it. Used for logout_all feature. NULL = no mass logout performed.';
