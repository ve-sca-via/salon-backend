-- The RM now verifies a regular_buyer owner's phone via OTP at intake (before
-- submission), and admin approval creates the buyer's account immediately - there
-- is no more buyer-facing self-service activation step (see
-- app/services/vendor_approval_service.py's regular_buyer approval branch and
-- app/services/rm_service.py's _apply_regular_buyer_phone_verification).
--
-- That means two things now have to be collected at intake instead of from the
-- buyer themselves later: age/gender (profiles.age/gender are NOT NULL), and proof
-- the phone was actually OTP-verified. All columns are nullable here - enforcement
-- stays at the Pydantic layer (VendorJoinRequestBase), conditional on request_type,
-- same pattern already used for owner_email.
--
-- Verified-phone column names mirror profiles.phone_verified / phone_verified_at /
-- phone_verification_method (see db-schema/current_schema.sql).

ALTER TABLE "public"."vendor_join_requests"
    ADD COLUMN "owner_age" integer,
    ADD COLUMN "owner_gender" character varying(20),
    ADD COLUMN "owner_phone_verified" boolean DEFAULT false,
    ADD COLUMN "owner_phone_verified_at" timestamp with time zone,
    ADD COLUMN "owner_phone_verification_method" character varying(50);

ALTER TABLE "public"."vendor_join_requests"
    ADD CONSTRAINT "valid_owner_age" CHECK ("owner_age" IS NULL OR ("owner_age" BETWEEN 13 AND 120)),
    ADD CONSTRAINT "valid_owner_gender" CHECK ("owner_gender" IS NULL OR ("owner_gender")::"text" = ANY ((ARRAY['male'::character varying, 'female'::character varying, 'other'::character varying])::"text"[]));
