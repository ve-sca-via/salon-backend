-- Tighten every pincode CHECK to six digits
--
-- WHY:
-- `vendor_join_requests.pincode` was widened to "6 OR 10 digits" by
-- 20251118030000_fix_vendor_join_requests.sql, and 20260801000000 widened
-- `salons.pincode` to match so approval would stop crashing on the mismatch.
-- Neither 10-digit form is a real postal code - Indian PINs are six digits, and
-- both RM forms have only ever accepted six. The 10-digit branch was an accident
-- that existed purely to make the two tables agree, so it goes away on both
-- sides at once, together with the `^\d{10}$` branch in
-- app/schemas/request/vendor.py.
--
-- The columns stay VARCHAR(10). Narrowing them back to VARCHAR(6) would rewrite
-- both tables and buys nothing once the CHECK is six digits.
--
-- EXISTING ROWS: the constraints are added NOT VALID, so a legacy 10-digit row
-- cannot block this migration - it is only refused on the next INSERT or UPDATE
-- of that row. The DO block below reports how many such rows exist. To finish the
-- job once they are cleaned up:
--
--     SELECT id, pincode FROM salons WHERE pincode !~ '^\d{6}$';
--     SELECT id, pincode FROM vendor_join_requests WHERE pincode !~ '^\d{6}$';
--     ALTER TABLE salons VALIDATE CONSTRAINT valid_pincode_format;
--     ALTER TABLE vendor_join_requests VALIDATE CONSTRAINT valid_pincode;

DO $$
DECLARE
    salon_count integer;
    request_count integer;
BEGIN
    SELECT count(*) INTO salon_count FROM "public"."salons"
        WHERE "pincode" IS NOT NULL AND "pincode" !~ '^\d{6}$';
    SELECT count(*) INTO request_count FROM "public"."vendor_join_requests"
        WHERE "pincode" IS NOT NULL AND "pincode" !~ '^\d{6}$';

    IF salon_count > 0 OR request_count > 0 THEN
        RAISE WARNING
            'Pincode tightening: % salon row(s) and % join request(s) still hold a non-6-digit pincode. They keep their value but can no longer be updated until fixed; see this migration''s header.',
            salon_count, request_count;
    ELSE
        RAISE NOTICE 'Pincode tightening: no existing rows violate the 6-digit rule.';
    END IF;
END $$;

ALTER TABLE "public"."salons"
    DROP CONSTRAINT IF EXISTS "valid_pincode_format";

ALTER TABLE "public"."salons"
    ADD CONSTRAINT "valid_pincode_format"
    CHECK (("pincode")::text ~ '^\d{6}$')
    NOT VALID;

ALTER TABLE "public"."vendor_join_requests"
    DROP CONSTRAINT IF EXISTS "valid_pincode";

ALTER TABLE "public"."vendor_join_requests"
    ADD CONSTRAINT "valid_pincode"
    CHECK (("pincode")::text ~ '^\d{6}$')
    NOT VALID;

COMMENT ON COLUMN "public"."salons"."pincode" IS
    'Six-digit Indian PIN, copied from the originating vendor_join_request. Both '
    'tables and app/schemas/request/vendor.py enforce the same rule - keep them in '
    'sync or salon creation at approval time will fail.';

COMMENT ON COLUMN "public"."vendor_join_requests"."pincode" IS
    'Six-digit Indian PIN as entered on the RM salon form. Verified against India '
    'Post by GET /api/v1/location/pincode/{pincode} before submission.';
