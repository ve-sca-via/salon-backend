-- ============================================================================
-- FIX MISSING RM PROFILES
-- ============================================================================
-- Creates RM profiles for users with role 'relationship_manager' but no RM profile

INSERT INTO rm_profiles (id, full_name, phone, email, assigned_territories, performance_score, is_active)
SELECT 
  p.id,
  p.full_name,
  COALESCE(p.phone, '0000000000'),  -- Default phone if null
  p.email,
  ARRAY[]::TEXT[],  -- Empty territories array
  0,  -- Initial score
  p.is_active
FROM profiles p
LEFT JOIN rm_profiles rm ON p.id = rm.id
WHERE p.user_role = 'relationship_manager'
  AND rm.id IS NULL;  -- Only insert if RM profile doesn't exist

-- Show created RM profiles
SELECT 
  rm.id,
  rm.full_name,
  rm.email,
  rm.performance_score,
  rm.is_active
FROM rm_profiles rm
ORDER BY rm.created_at DESC;
