-- Lock the product-order SECURITY DEFINER RPCs to the backend only.
--
-- decrement_product_stock(UUID) and redeem_product_coupon(UUID, UUID, UUID, NUMERIC)
-- run as their owner and trust the caller's arguments (order id, user id,
-- discount). They were granted to `authenticated`, so any logged-in user could
-- call them through PostgREST /rpc and decrement stock on someone else's or an
-- unpaid order, or redeem a coupon against an arbitrary order.
--
-- The backend only ever calls them through the service-role client
-- (app/core/database.get_db), so service_role is the only role that needs them.
-- Postgres grants EXECUTE to PUBLIC on CREATE FUNCTION and Supabase's default
-- privileges grant it to anon/authenticated, so all three are revoked.
--
-- The 20261103/20261104 migrations were edited to match, but they may already
-- have been applied, so this migration carries the fix. REVOKE/GRANT are
-- idempotent: safe whether or not the originals ran with the old grants.

REVOKE EXECUTE ON FUNCTION decrement_product_stock(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION decrement_product_stock(UUID) TO service_role;

REVOKE EXECUTE ON FUNCTION redeem_product_coupon(UUID, UUID, UUID, NUMERIC) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION redeem_product_coupon(UUID, UUID, UUID, NUMERIC) TO service_role;
