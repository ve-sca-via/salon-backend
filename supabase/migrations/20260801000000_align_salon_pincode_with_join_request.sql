-- Align salons.pincode with vendor_join_requests.pincode
--
-- WHY:
-- The RM submission form and vendor_join_requests both accept a 6- OR 10-digit
-- pincode (app/schemas/request/vendor.py: pattern ^\d{6}$|^\d{10}$, and
-- vendor_join_requests.pincode VARCHAR(10) CHECK ~ '^\d{6}$' OR ~ '^\d{10}$').
--
-- salons.pincode was never widened to match: VARCHAR(6) with a 6-digit-only
-- CHECK. Approving a request whose RM entered a 10-digit pincode therefore made
-- the salon INSERT fail with "value too long for type character varying(6)".
--
-- Because the approval flow flipped the request to 'approved' BEFORE creating
-- the salon, that failure left the request marked approved with no salon row,
-- returned a 500 to the admin panel, and skipped the vendor's registration
-- email entirely. This migration removes the schema half of that bug; the
-- ordering half is fixed in VendorApprovalService.approve_vendor_request.

ALTER TABLE "public"."salons"
    ALTER COLUMN "pincode" TYPE character varying(10);

ALTER TABLE "public"."salons"
    DROP CONSTRAINT IF EXISTS "valid_pincode_format";

ALTER TABLE "public"."salons"
    ADD CONSTRAINT "valid_pincode_format"
    CHECK (
        ("pincode")::text ~ '^\d{6}$'
        OR ("pincode")::text ~ '^\d{10}$'
    );

COMMENT ON COLUMN "public"."salons"."pincode" IS
    'Postal code copied from the originating vendor_join_request. Accepts the '
    'same 6- or 10-digit forms as vendor_join_requests.pincode - keep the two '
    'in sync or salon creation at approval time will fail.';
