-- ============================================================================
-- DISABLE ROW LEVEL SECURITY FOR SERVICE ROLE ARCHITECTURE
-- ============================================================================
-- 
-- ARCHITECTURE DECISION:
-- We use FastAPI as a backend-only application with service_role key.
-- All authentication/authorization is handled in FastAPI code via JWT tokens.
-- RLS is not needed because:
--   1. Backend uses service_role key which bypasses RLS anyway
--   2. All authorization logic is in Python code (get_current_user, require_admin, etc.)
--   3. Frontend never directly accesses Supabase database
--   4. This is the standard pattern for backend-driven Supabase applications
--
-- Security model:
--   - Service role key stays in backend only (never exposed to frontend)
--   - Every protected endpoint validates JWT and checks user roles
--   - Authorization is explicit and auditable in Python code
--   - No confusion about what auth.uid() returns (it's always NULL with service_role)
--
-- Migration date: 2025-11-23
-- ============================================================================

-- Drop all existing RLS policies (they don't work with service_role anyway)
-- These policies were written for authenticated users with Supabase JWTs,
-- but we use custom FastAPI JWTs instead.

-- ============================================================================
-- DROP ALL POLICIES
-- ============================================================================

-- audit_logs policies
DROP POLICY IF EXISTS "Admins can view audit logs" ON audit_logs;
DROP POLICY IF EXISTS "System can insert audit logs" ON audit_logs;

-- booking_payments policies
DROP POLICY IF EXISTS "Admins can manage all payments" ON booking_payments;
DROP POLICY IF EXISTS "Customers can view own payments" ON booking_payments;
DROP POLICY IF EXISTS "System can create payments" ON booking_payments;
DROP POLICY IF EXISTS "System can update payments" ON booking_payments;
DROP POLICY IF EXISTS "Vendors can view salon payments" ON booking_payments;
DROP POLICY IF EXISTS "payments_insert_for_authenticated" ON booking_payments;
DROP POLICY IF EXISTS "payments_select_own" ON booking_payments;
DROP POLICY IF EXISTS "payments_select_vendor" ON booking_payments;
DROP POLICY IF EXISTS "payments_update_vendor" ON booking_payments;
DROP POLICY IF EXISTS "payments_select_admin" ON booking_payments;

-- bookings policies
DROP POLICY IF EXISTS "Admins can manage all bookings" ON bookings;
DROP POLICY IF EXISTS "Customers can create bookings" ON bookings;
DROP POLICY IF EXISTS "Customers can update own bookings" ON bookings;
DROP POLICY IF EXISTS "Customers can view own bookings" ON bookings;
DROP POLICY IF EXISTS "Vendors can update salon bookings" ON bookings;
DROP POLICY IF EXISTS "Vendors can view salon bookings" ON bookings;

-- cart_items policies
DROP POLICY IF EXISTS "Users can manage own cart" ON cart_items;

-- favorites policies
DROP POLICY IF EXISTS "Users can manage own favorites" ON favorites;

-- profiles policies
DROP POLICY IF EXISTS "Public profiles are viewable by everyone" ON profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;

-- reviews policies
DROP POLICY IF EXISTS "Admins can manage all reviews" ON reviews;
DROP POLICY IF EXISTS "Customers can create reviews" ON reviews;
DROP POLICY IF EXISTS "Customers can update own reviews" ON reviews;
DROP POLICY IF EXISTS "Public can view reviews" ON reviews;
DROP POLICY IF EXISTS "Vendors can respond to reviews" ON reviews;

-- rm_profiles policies
DROP POLICY IF EXISTS "Admins can manage RMs" ON rm_profiles;
DROP POLICY IF EXISTS "Admins can view RMs" ON rm_profiles;

-- rm_score_history policies
DROP POLICY IF EXISTS "Admins can view all score history" ON rm_score_history;
DROP POLICY IF EXISTS "RMs can view own score history" ON rm_score_history;
DROP POLICY IF EXISTS "System can insert score history" ON rm_score_history;

-- salon_staff policies
DROP POLICY IF EXISTS "Active staff viewable by everyone" ON salon_staff;
DROP POLICY IF EXISTS "Admins can manage all staff" ON salon_staff;
DROP POLICY IF EXISTS "Vendors can manage salon staff" ON salon_staff;

-- salon_subscriptions policies
DROP POLICY IF EXISTS "Admins can manage subscriptions" ON salon_subscriptions;
DROP POLICY IF EXISTS "Vendors can view own subscriptions" ON salon_subscriptions;

-- salons policies
DROP POLICY IF EXISTS "Active salons are viewable by everyone" ON salons;
DROP POLICY IF EXISTS "Admins and RMs can manage salons" ON salons;
DROP POLICY IF EXISTS "Vendors can create salon" ON salons;
DROP POLICY IF EXISTS "Vendors can update own salon" ON salons;

-- service_categories policies
DROP POLICY IF EXISTS "Active categories viewable by everyone" ON service_categories;
DROP POLICY IF EXISTS "Admins can manage categories" ON service_categories;

-- services policies
DROP POLICY IF EXISTS "Active services viewable by everyone" ON services;
DROP POLICY IF EXISTS "Admins can manage all services" ON services;
DROP POLICY IF EXISTS "Vendors can manage own salon services" ON services;

-- staff_availability policies
DROP POLICY IF EXISTS "Staff availability viewable by everyone" ON staff_availability;
DROP POLICY IF EXISTS "Vendors can manage staff availability" ON staff_availability;

-- token_blacklist policies
DROP POLICY IF EXISTS "System can insert blacklisted tokens" ON token_blacklist;
DROP POLICY IF EXISTS "Users can view own blacklisted tokens" ON token_blacklist;

-- vendor_join_requests policies
DROP POLICY IF EXISTS "Admins and RMs can update join requests" ON vendor_join_requests;
DROP POLICY IF EXISTS "Admins and RMs can view join requests" ON vendor_join_requests;
DROP POLICY IF EXISTS "Users can create join requests" ON vendor_join_requests;
DROP POLICY IF EXISTS "Users can view own join requests" ON vendor_join_requests;

-- vendor_registration_payments policies
DROP POLICY IF EXISTS "Admins can manage registration payments" ON vendor_registration_payments;
DROP POLICY IF EXISTS "System can create registration payments" ON vendor_registration_payments;
DROP POLICY IF EXISTS "System can update registration payments" ON vendor_registration_payments;
DROP POLICY IF EXISTS "Vendors can view own registration payments" ON vendor_registration_payments;

-- payments table policies (if it exists as separate from booking_payments)
DROP POLICY IF EXISTS "payments_insert_for_authenticated" ON payments;
DROP POLICY IF EXISTS "payments_select_own" ON payments;
DROP POLICY IF EXISTS "payments_select_vendor" ON payments;
DROP POLICY IF EXISTS "payments_update_own" ON payments;
DROP POLICY IF EXISTS "payments_admin_all" ON payments;

-- ============================================================================
-- DISABLE ROW LEVEL SECURITY ON ALL TABLES
-- ============================================================================
-- With service_role key, RLS is bypassed anyway, but explicitly disabling
-- makes the architecture decision clear and removes confusion.

ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY;
ALTER TABLE booking_payments DISABLE ROW LEVEL SECURITY;
ALTER TABLE bookings DISABLE ROW LEVEL SECURITY;
ALTER TABLE cart_items DISABLE ROW LEVEL SECURITY;
ALTER TABLE favorites DISABLE ROW LEVEL SECURITY;
ALTER TABLE phone_verification_codes DISABLE ROW LEVEL SECURITY;
ALTER TABLE profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE reviews DISABLE ROW LEVEL SECURITY;
ALTER TABLE rm_profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE rm_score_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE salon_staff DISABLE ROW LEVEL SECURITY;
ALTER TABLE salon_subscriptions DISABLE ROW LEVEL SECURITY;
ALTER TABLE salons DISABLE ROW LEVEL SECURITY;
ALTER TABLE service_categories DISABLE ROW LEVEL SECURITY;
ALTER TABLE services DISABLE ROW LEVEL SECURITY;
ALTER TABLE staff_availability DISABLE ROW LEVEL SECURITY;
ALTER TABLE token_blacklist DISABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_join_requests DISABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_registration_payments DISABLE ROW LEVEL SECURITY;

-- Additional tables that might exist
ALTER TABLE IF EXISTS payments DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS career_applications DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS activity_logs DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- SECURITY NOTES
-- ============================================================================
-- 
-- With RLS disabled, ALL security enforcement happens in FastAPI:
-- 
-- 1. JWT Validation:
--    - Every protected endpoint must use Depends(get_current_user)
--    - JWT signature is verified with JWT_SECRET_KEY
--    - Token expiration is checked
--    - Blacklisted tokens are rejected
-- 
-- 2. Authorization Checks:
--    - Role-based: Depends(require_admin), Depends(require_vendor), etc.
--    - Resource ownership: if current_user.user_id != resource.owner_id
--    - Business logic: Custom checks in service layer
-- 
-- 3. CRITICAL: Service role key must NEVER be exposed:
--    - Keep in backend .env only
--    - Never in frontend code
--    - Never in git commits
--    - Never in logs or error messages
-- 
-- 4. Audit all endpoints:
--    - Public endpoints: Read-only operations on public data
--    - Protected endpoints: MUST use get_current_user dependency
--    - Admin endpoints: MUST use require_admin or RoleChecker(["admin"])
-- 
-- ============================================================================

COMMENT ON TABLE audit_logs IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE booking_payments IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE bookings IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE cart_items IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE favorites IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE profiles IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE reviews IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE rm_profiles IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE rm_score_history IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE salon_staff IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE salon_subscriptions IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE salons IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE service_categories IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE services IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE staff_availability IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE token_blacklist IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE vendor_join_requests IS 'RLS disabled - backend uses service_role with FastAPI auth';
COMMENT ON TABLE vendor_registration_payments IS 'RLS disabled - backend uses service_role with FastAPI auth';
