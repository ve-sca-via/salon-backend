-- Lock redeem_coupon() to the backend only.
--
-- redeem_coupon(UUID, UUID, UUID, NUMERIC, NUMERIC) is SECURITY DEFINER and
-- trusts its arguments (coupon id, user id, booking id, discount amounts). It
-- was granted to `authenticated` (and, via Supabase default privileges, to
-- `anon`), so anyone could call it through PostgREST /rpc and burn a coupon's
-- usage limit or record redemptions against bookings that aren't theirs.
--
-- Same fix as 20261105000000_restrict_product_rpc_grants for the product RPCs.
-- The backend only calls it through the service-role client
-- (app/services/coupon_service.py -> app/core/database.get_db), and no
-- frontend calls it directly, so service_role is the only role that needs it.
--
-- The 4-argument overload from 20260614000001 was dropped in 20260617000000,
-- so only the 5-argument signature exists. REVOKE/GRANT are idempotent.

REVOKE EXECUTE ON FUNCTION redeem_coupon(UUID, UUID, UUID, NUMERIC, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION redeem_coupon(UUID, UUID, UUID, NUMERIC, NUMERIC) TO service_role;
