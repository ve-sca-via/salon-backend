-- Regular buyers (B2B product-only buyers, salon_type = 'regular_buyer') generally
-- have no email on file and now activate their account via phone OTP instead of
-- an emailed registration link (see app/services/vendor_service.py
-- send_buyer_phone_activation_otp / complete_buyer_phone_registration).
--
-- Both columns below were NOT NULL, which blocked submitting or approving a
-- regular_buyer request with no owner_email at all. Normal salon/vendor
-- requests are unaffected - the application layer still requires owner_email
-- for request_type != 'regular_buyer' (see VendorJoinRequestBase's model
-- validator in app/schemas/request/vendor.py).

ALTER TABLE "public"."vendor_join_requests"
    ALTER COLUMN "owner_email" DROP NOT NULL;

ALTER TABLE "public"."salons"
    ALTER COLUMN "email" DROP NOT NULL;
