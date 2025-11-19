


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

-- Enable PostGIS extension for geography type
CREATE EXTENSION IF NOT EXISTS postgis SCHEMA public;

CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE TYPE "public"."booking_status" AS ENUM (
    'pending',
    'confirmed',
    'cancelled',
    'completed',
    'no_show'
);


ALTER TYPE "public"."booking_status" OWNER TO "postgres";


COMMENT ON TYPE "public"."booking_status" IS 'Booking lifecycle states from creation to completion';



CREATE TYPE "public"."payment_status" AS ENUM (
    'pending',
    'success',
    'failed',
    'refunded'
);


ALTER TYPE "public"."payment_status" OWNER TO "postgres";


COMMENT ON TYPE "public"."payment_status" IS 'Razorpay payment states (pending→success/failed→refunded)';



CREATE TYPE "public"."payment_type" AS ENUM (
    'registration_fee',
    'convenience_fee',
    'service_payment'
);


ALTER TYPE "public"."payment_type" OWNER TO "postgres";


COMMENT ON TYPE "public"."payment_type" IS 'Classification of payment types in the platform';



CREATE TYPE "public"."request_status" AS ENUM (
    'draft',
    'pending',
    'approved',
    'rejected'
);


ALTER TYPE "public"."request_status" OWNER TO "postgres";


COMMENT ON TYPE "public"."request_status" IS 'Vendor join request workflow states';



CREATE TYPE "public"."user_role" AS ENUM (
    'admin',
    'relationship_manager',
    'vendor',
    'customer'
);


ALTER TYPE "public"."user_role" OWNER TO "postgres";


COMMENT ON TYPE "public"."user_role" IS 'User role for authorization (stored in JWT claims)';



CREATE OR REPLACE FUNCTION "public"."generate_booking_number"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  -- Format: BK-YYYYMMDD-XXXXX (e.g., BK-20251115-00001)
  NEW.booking_number := 'BK-' || 
                        TO_CHAR(CURRENT_DATE, 'YYYYMMDD') || '-' || 
                        LPAD(
                          (
                            SELECT COALESCE(MAX(SUBSTRING(booking_number FROM 14)::INTEGER), 0) + 1
                            FROM bookings
                            WHERE booking_number LIKE 'BK-' || TO_CHAR(CURRENT_DATE, 'YYYYMMDD') || '-%'
                          )::TEXT, 
                          5, 
                          '0'
                        );
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."generate_booking_number"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_salon_location"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
    NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_salon_location"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_salon_rating"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  -- Update salon's average rating
  UPDATE salons
  SET 
    average_rating = (
      SELECT ROUND(AVG(rating)::numeric, 2)
      FROM reviews
      WHERE salon_id = COALESCE(NEW.salon_id, OLD.salon_id)
        AND deleted_at IS NULL
        AND is_hidden = false
    ),
    updated_at = now()
  WHERE id = COALESCE(NEW.salon_id, OLD.salon_id);
  
  RETURN COALESCE(NEW, OLD);
END;
$$;


ALTER FUNCTION "public"."update_salon_rating"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."audit_logs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "table_name" character varying(100) NOT NULL,
    "record_id" "uuid" NOT NULL,
    "action" character varying(20) NOT NULL,
    "old_data" "jsonb",
    "new_data" "jsonb",
    "changed_fields" "text"[],
    "user_id" "uuid",
    "ip_address" "inet",
    "user_agent" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "audit_logs_action_check" CHECK ((("action")::"text" = ANY ((ARRAY['INSERT'::character varying, 'UPDATE'::character varying, 'DELETE'::character varying, 'SOFT_DELETE'::character varying])::"text"[])))
);


ALTER TABLE "public"."audit_logs" OWNER TO "postgres";


COMMENT ON TABLE "public"."audit_logs" IS 'Audit trail for all data modifications. Required for Indian IT Act 2000 and DPDP Act 2023 compliance.';



CREATE TABLE IF NOT EXISTS "public"."booking_payments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "booking_id" "uuid" NOT NULL,
    "customer_id" "uuid" NOT NULL,
    "razorpay_order_id" character varying(40),
    "razorpay_payment_id" character varying(40),
    "razorpay_signature" character varying(255),
    "amount" numeric(10,2) NOT NULL,
    "currency" character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    "payment_method" character varying(50),
    "status" "public"."payment_status" DEFAULT 'pending'::"public"."payment_status" NOT NULL,
    "payment_type" "public"."payment_type" DEFAULT 'convenience_fee'::"public"."payment_type" NOT NULL,
    "payment_initiated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "payment_completed_at" timestamp with time zone,
    "payment_failed_at" timestamp with time zone,
    "failure_reason" "text",
    "error_code" character varying(50),
    "error_description" "text",
    "refund_initiated" boolean DEFAULT false,
    "refund_completed" boolean DEFAULT false,
    "refund_amount" numeric(10,2) DEFAULT 0,
    "refund_reason" "text",
    "refunded_at" timestamp with time zone,
    "razorpay_refund_id" character varying(40),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "booking_payments_amount_check" CHECK (("amount" >= (0)::numeric)),
    CONSTRAINT "booking_payments_check" CHECK ((("refund_amount" >= (0)::numeric) AND ("refund_amount" <= "amount"))),
    CONSTRAINT "valid_payment_status_timestamp" CHECK (((("status" = 'pending'::"public"."payment_status") AND ("payment_completed_at" IS NULL) AND ("payment_failed_at" IS NULL)) OR (("status" = 'success'::"public"."payment_status") AND ("payment_completed_at" IS NOT NULL)) OR (("status" = 'failed'::"public"."payment_status") AND ("payment_failed_at" IS NOT NULL)))),
    CONSTRAINT "valid_refund_logic" CHECK (((("refund_initiated" = false) AND ("refund_completed" = false) AND ("refund_amount" = (0)::numeric)) OR (("refund_initiated" = true) AND ("refund_amount" > (0)::numeric))))
);


ALTER TABLE "public"."booking_payments" OWNER TO "postgres";


COMMENT ON TABLE "public"."booking_payments" IS 'Razorpay payment records for booking convenience fees (paid online)';



COMMENT ON COLUMN "public"."booking_payments"."razorpay_order_id" IS 'Razorpay order ID (immutable after creation)';



COMMENT ON COLUMN "public"."booking_payments"."razorpay_payment_id" IS 'Razorpay payment ID (set after successful payment)';



COMMENT ON COLUMN "public"."booking_payments"."razorpay_signature" IS 'Razorpay signature for payment verification';



COMMENT ON COLUMN "public"."booking_payments"."payment_type" IS 'Type of payment: convenience_fee (platform fee), service_payment (full service), etc.';



COMMENT ON COLUMN "public"."booking_payments"."refund_amount" IS 'Must be <= original amount';



COMMENT ON COLUMN "public"."booking_payments"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."bookings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "booking_number" character varying(20) NOT NULL,
    "customer_id" "uuid" NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "service_id" "uuid" NOT NULL,
    "booking_date" "date" NOT NULL,
    "booking_time" time without time zone NOT NULL,
    "service_price" numeric(10,2) NOT NULL,
    "convenience_fee" numeric(10,2) NOT NULL,
    "total_amount" numeric(10,2) NOT NULL,
    "gst_rate" numeric(5,2) DEFAULT 18.00,
    "cgst" numeric(10,2) DEFAULT 0,
    "sgst" numeric(10,2) DEFAULT 0,
    "igst" numeric(10,2) DEFAULT 0,
    "convenience_fee_paid" boolean DEFAULT false,
    "convenience_fee_paid_at" timestamp with time zone,
    "service_price_paid" boolean DEFAULT false,
    "service_price_paid_at" timestamp with time zone,
    "status" "public"."booking_status" DEFAULT 'pending'::"public"."booking_status" NOT NULL,
    "customer_name" character varying(255) NOT NULL,
    "customer_phone" character varying(15) NOT NULL,
    "customer_email" character varying(255),
    "cancelled_at" timestamp with time zone,
    "cancellation_reason" "text",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    "duration_minutes" integer DEFAULT 60,
    "services" "jsonb",
    CONSTRAINT "bookings_cgst_check" CHECK (("cgst" >= (0)::numeric)),
    CONSTRAINT "bookings_convenience_fee_check" CHECK (("convenience_fee" >= (0)::numeric)),
    CONSTRAINT "bookings_igst_check" CHECK (("igst" >= (0)::numeric)),
    CONSTRAINT "bookings_service_price_check" CHECK (("service_price" >= (0)::numeric)),
    CONSTRAINT "bookings_sgst_check" CHECK (("sgst" >= (0)::numeric)),
    CONSTRAINT "bookings_total_amount_check" CHECK (("total_amount" >= (0)::numeric)),
    CONSTRAINT "convenience_payment_logic" CHECK (((("convenience_fee_paid" = false) AND ("convenience_fee_paid_at" IS NULL)) OR (("convenience_fee_paid" = true) AND ("convenience_fee_paid_at" IS NOT NULL)))),
    CONSTRAINT "service_payment_logic" CHECK (((("service_price_paid" = false) AND ("service_price_paid_at" IS NULL)) OR (("service_price_paid" = true) AND ("service_price_paid_at" IS NOT NULL)))),
    CONSTRAINT "valid_booking_datetime" CHECK (("booking_date" >= CURRENT_DATE)),
    CONSTRAINT "valid_gst_sum" CHECK (((("cgst" + "sgst") + "igst") >= (0)::numeric)),
    CONSTRAINT "valid_total_amount" CHECK (("total_amount" = ("service_price" + "convenience_fee")))
);


ALTER TABLE "public"."bookings" OWNER TO "postgres";


COMMENT ON TABLE "public"."bookings" IS 'Customer bookings with split payment tracking (convenience fee online, service price at salon)';



COMMENT ON COLUMN "public"."bookings"."booking_number" IS 'Auto-generated unique booking reference (BK-YYYYMMDD-XXXXX)';



COMMENT ON COLUMN "public"."bookings"."service_price" IS 'Service price paid at salon to vendor';



COMMENT ON COLUMN "public"."bookings"."convenience_fee" IS 'Platform fee paid online via Razorpay';



COMMENT ON COLUMN "public"."bookings"."total_amount" IS 'Must equal service_price + convenience_fee';



COMMENT ON COLUMN "public"."bookings"."convenience_fee_paid" IS 'true = convenience fee paid online';



COMMENT ON COLUMN "public"."bookings"."service_price_paid" IS 'true = service price paid at salon (cash/POS)';



COMMENT ON COLUMN "public"."bookings"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."cart_items" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "service_id" "uuid" NOT NULL,
    "quantity" integer DEFAULT 1,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "cart_items_quantity_check" CHECK (("quantity" > 0))
);


ALTER TABLE "public"."cart_items" OWNER TO "postgres";


COMMENT ON TABLE "public"."cart_items" IS 'Shopping cart items (normalized - no denormalization)';



CREATE TABLE IF NOT EXISTS "public"."favorites" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."favorites" OWNER TO "postgres";


COMMENT ON TABLE "public"."favorites" IS 'User favorite salons';



CREATE TABLE IF NOT EXISTS "public"."phone_verification_codes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "phone" character varying(20) NOT NULL,
    "country_code" character varying(5) DEFAULT '+91'::character varying NOT NULL,
    "otp_code" character varying(6) NOT NULL,
    "otp_hash" character varying(255) NOT NULL,
    "purpose" character varying(50) NOT NULL,
    "verified" boolean DEFAULT false,
    "verified_at" timestamp with time zone,
    "expires_at" timestamp with time zone NOT NULL,
    "attempts" integer DEFAULT 0,
    "max_attempts" integer DEFAULT 3,
    "ip_address" "inet",
    "user_agent" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "otp_rate_limit" CHECK (("created_at" > ("now"() - '01:00:00'::interval))),
    CONSTRAINT "phone_verification_codes_purpose_check" CHECK ((("purpose")::"text" = ANY ((ARRAY['signup'::character varying, 'login'::character varying, 'phone_verification'::character varying, 'password_reset'::character varying])::"text"[])))
);


ALTER TABLE "public"."phone_verification_codes" OWNER TO "postgres";


COMMENT ON TABLE "public"."phone_verification_codes" IS 'OTP codes for phone verification. Rate-limited to prevent abuse (max 5/hour).';



CREATE TABLE IF NOT EXISTS "public"."profiles" (
    "id" "uuid" NOT NULL,
    "full_name" character varying(255) NOT NULL,
    "email" character varying(255) NOT NULL,
    "phone" character varying(20),
    "avatar_url" "text",
    "address_line1" "text",
    "address_line2" "text",
    "city" character varying(100),
    "state" character varying(100),
    "pincode" character varying(6),
    "phone_verified" boolean DEFAULT false,
    "phone_verified_at" timestamp with time zone,
    "phone_verification_method" character varying(50),
    "user_role" "public"."user_role" DEFAULT 'customer'::"public"."user_role" NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "valid_email" CHECK ((("email")::"text" ~* '^[a-zA-Z0-9.!#$%&''*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'::"text")),
    CONSTRAINT "valid_phone_format" CHECK ((("phone" IS NULL) OR (("phone")::"text" ~ '^\+?[1-9]\d{1,14}$'::"text"))),
    CONSTRAINT "valid_pincode_format" CHECK ((("pincode" IS NULL) OR (("pincode")::"text" ~ '^\d{6}$'::"text")))
);


ALTER TABLE "public"."profiles" OWNER TO "postgres";


COMMENT ON TABLE "public"."profiles" IS 'User profiles with Indian compliance (DPDP Act 2023). Supports phone OTP authentication.';



COMMENT ON COLUMN "public"."profiles"."pincode" IS 'Indian 6-digit pincode (validated)';



COMMENT ON COLUMN "public"."profiles"."phone_verified" IS 'Whether phone number is verified via OTP';



COMMENT ON COLUMN "public"."profiles"."phone_verification_method" IS 'How phone was verified: otp, call, or manual';



COMMENT ON COLUMN "public"."profiles"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."reviews" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "booking_id" "uuid" NOT NULL,
    "customer_id" "uuid" NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "service_id" "uuid" NOT NULL,
    "rating" integer NOT NULL,
    "review_text" "text",
    "image_urls" "text"[],
    "vendor_response" "text",
    "vendor_responded_at" timestamp with time zone,
    "is_verified" boolean DEFAULT false,
    "is_featured" boolean DEFAULT false,
    "is_hidden" boolean DEFAULT false,
    "hidden_reason" "text",
    "helpful_count" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "reviews_helpful_count_check" CHECK (("helpful_count" >= 0)),
    CONSTRAINT "reviews_rating_check" CHECK ((("rating" >= 1) AND ("rating" <= 5)))
);


ALTER TABLE "public"."reviews" OWNER TO "postgres";


COMMENT ON TABLE "public"."reviews" IS 'Customer reviews with auto-updating salon average rating';



COMMENT ON COLUMN "public"."reviews"."rating" IS 'Star rating (1-5)';



COMMENT ON COLUMN "public"."reviews"."is_verified" IS 'true = customer actually completed the booking';



COMMENT ON COLUMN "public"."reviews"."is_featured" IS 'true = featured on homepage/salon page';



COMMENT ON COLUMN "public"."reviews"."is_hidden" IS 'true = hidden by admin (spam/inappropriate content)';



COMMENT ON COLUMN "public"."reviews"."helpful_count" IS 'Number of users who found this review helpful';



COMMENT ON COLUMN "public"."reviews"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."rm_profiles" (
    "id" "uuid" NOT NULL,
    "full_name" character varying(255) NOT NULL,
    "phone" character varying(20) NOT NULL,
    "email" character varying(255) NOT NULL,
    "assigned_territories" "text"[],
    "performance_score" integer DEFAULT 0,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."rm_profiles" OWNER TO "postgres";


COMMENT ON TABLE "public"."rm_profiles" IS 'Relationship Manager profiles for vendor management';



CREATE TABLE IF NOT EXISTS "public"."rm_score_history" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "rm_id" "uuid" NOT NULL,
    "action" character varying(100) NOT NULL,
    "points" integer NOT NULL,
    "description" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."rm_score_history" OWNER TO "postgres";


COMMENT ON TABLE "public"."rm_score_history" IS 'RM performance score history and tracking';



CREATE TABLE IF NOT EXISTS "public"."salon_staff" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "user_id" "uuid",
    "name" character varying(255) NOT NULL,
    "phone" character varying(20),
    "email" character varying(255),
    "role" character varying(100),
    "specialization" "text"[],
    "profile_image" "text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."salon_staff" OWNER TO "postgres";


COMMENT ON TABLE "public"."salon_staff" IS 'Staff members working at salons';



CREATE TABLE IF NOT EXISTS "public"."salon_subscriptions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "plan_name" character varying(100) NOT NULL,
    "plan_type" character varying(50) DEFAULT 'monthly'::character varying NOT NULL,
    "status" character varying(50) DEFAULT 'active'::character varying NOT NULL,
    "start_date" timestamp with time zone NOT NULL,
    "end_date" timestamp with time zone NOT NULL,
    "amount" numeric(10,2) NOT NULL,
    "payment_id" "uuid",
    "auto_renew" boolean DEFAULT true,
    "cancelled_at" timestamp with time zone,
    "cancellation_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "salon_subscriptions_amount_check" CHECK (("amount" >= (0)::numeric)),
    CONSTRAINT "salon_subscriptions_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['active'::character varying, 'expired'::character varying, 'cancelled'::character varying, 'suspended'::character varying])::"text"[])))
);


ALTER TABLE "public"."salon_subscriptions" OWNER TO "postgres";


COMMENT ON TABLE "public"."salon_subscriptions" IS 'Subscription plans for salons (future use - currently one-time registration only)';



CREATE TABLE IF NOT EXISTS "public"."salons" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "business_name" character varying(255) NOT NULL,
    "description" "text",
    "email" character varying(255) NOT NULL,
    "phone" character varying(20) NOT NULL,
    "vendor_id" "uuid" NOT NULL,
    "address" "text" NOT NULL,
    "city" character varying(100) NOT NULL,
    "state" character varying(100) NOT NULL,
    "pincode" character varying(6) NOT NULL,
    "latitude" numeric(10,8),
    "longitude" numeric(11,8),
    "location" "public"."geography"(Point,4326),
    "gst_number" character varying(15),
    "pan_number" character varying(10),
    "logo_url" "text",
    "cover_images" "text"[] DEFAULT ARRAY[]::"text"[],
    "average_rating" numeric(3,2) DEFAULT 0.0,
    "total_reviews" integer DEFAULT 0,
    "opening_time" time without time zone,
    "closing_time" time without time zone,
    "working_days" character varying(100)[],
    "is_active" boolean DEFAULT true,
    "is_verified" boolean DEFAULT false,
    "verified_at" timestamp with time zone,
    "verified_by" "uuid",
    "registration_fee_paid" boolean DEFAULT false,
    "registration_payment_id" "uuid",
    "assigned_rm" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "valid_coordinates" CHECK (((("latitude" IS NULL) AND ("longitude" IS NULL)) OR (("latitude" IS NOT NULL) AND ("longitude" IS NOT NULL) AND (("latitude" >= ('-90'::integer)::numeric) AND ("latitude" <= (90)::numeric)) AND (("longitude" >= ('-180'::integer)::numeric) AND ("longitude" <= (180)::numeric))))),
    CONSTRAINT "valid_gst_format" CHECK ((("gst_number" IS NULL) OR (("gst_number")::"text" ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'::"text"))),
    CONSTRAINT "valid_pincode_format" CHECK ((("pincode")::"text" ~ '^\d{6}$'::"text")),
    CONSTRAINT "valid_rating" CHECK ((("average_rating" >= (0)::numeric) AND ("average_rating" <= (5)::numeric)))
);


ALTER TABLE "public"."salons" OWNER TO "postgres";


COMMENT ON TABLE "public"."salons" IS 'Salon business profiles with Indian GST compliance and geospatial location';



COMMENT ON COLUMN "public"."salons"."location" IS 'PostGIS geography point for nearby salon queries (auto-populated from lat/lng)';



COMMENT ON COLUMN "public"."salons"."gst_number" IS 'Indian GST number (15 chars: 2-digit state code + 10-char PAN + entity + checksum)';



COMMENT ON COLUMN "public"."salons"."registration_fee_paid" IS 'Whether vendor paid one-time platform registration fee';



COMMENT ON COLUMN "public"."salons"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."service_categories" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" character varying(100) NOT NULL,
    "description" "text",
    "icon_url" "text",
    "display_order" integer DEFAULT 0,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."service_categories" OWNER TO "postgres";


COMMENT ON TABLE "public"."service_categories" IS 'Service categories (Hair, Spa, Nails, Makeup, etc.)';



CREATE TABLE IF NOT EXISTS "public"."services" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" character varying(255) NOT NULL,
    "description" "text",
    "category_id" "uuid" NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "price" numeric(10,2) NOT NULL,
    "discounted_price" numeric(10,2),
    "duration_minutes" integer NOT NULL,
    "image_url" "text",
    "is_active" boolean DEFAULT true,
    "is_featured" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "services_discounted_price_check" CHECK ((("discounted_price" IS NULL) OR ("discounted_price" >= (0)::numeric))),
    CONSTRAINT "services_duration_minutes_check" CHECK (("duration_minutes" > 0)),
    CONSTRAINT "services_price_check" CHECK (("price" >= (0)::numeric)),
    CONSTRAINT "valid_discount" CHECK ((("discounted_price" IS NULL) OR ("discounted_price" < "price")))
);


ALTER TABLE "public"."services" OWNER TO "postgres";


COMMENT ON TABLE "public"."services" IS 'Services offered by salons with pricing and duration';



COMMENT ON COLUMN "public"."services"."price" IS 'Regular price (paid at salon)';



COMMENT ON COLUMN "public"."services"."discounted_price" IS 'Discounted price (if any). Must be less than regular price';



COMMENT ON COLUMN "public"."services"."duration_minutes" IS 'Estimated service duration in minutes';



COMMENT ON COLUMN "public"."services"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."staff_availability" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "staff_id" "uuid" NOT NULL,
    "day_of_week" integer NOT NULL,
    "start_time" time without time zone NOT NULL,
    "end_time" time without time zone NOT NULL,
    "is_available" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "staff_availability_day_of_week_check" CHECK ((("day_of_week" >= 0) AND ("day_of_week" <= 6)))
);


ALTER TABLE "public"."staff_availability" OWNER TO "postgres";


COMMENT ON TABLE "public"."staff_availability" IS 'Staff weekly availability schedule';



CREATE TABLE IF NOT EXISTS "public"."token_blacklist" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "token_jti" character varying(255) NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."token_blacklist" OWNER TO "postgres";


COMMENT ON TABLE "public"."token_blacklist" IS 'Blacklisted JWT tokens (for logout tracking)';



CREATE TABLE IF NOT EXISTS "public"."vendor_join_requests" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "business_name" character varying(255) NOT NULL,
    "email" character varying(255) NOT NULL,
    "phone" character varying(20) NOT NULL,
    "city" character varying(100) NOT NULL,
    "state" character varying(100) NOT NULL,
    "pincode" character varying(6) NOT NULL,
    "gst_number" character varying(15),
    "status" "public"."request_status" DEFAULT 'pending'::"public"."request_status" NOT NULL,
    "submitted_at" timestamp with time zone DEFAULT "now"(),
    "reviewed_at" timestamp with time zone,
    "reviewed_by" "uuid",
    "rejection_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "valid_pincode_format" CHECK ((("pincode")::"text" ~ '^\d{6}$'::"text"))
);


ALTER TABLE "public"."vendor_join_requests" OWNER TO "postgres";


COMMENT ON TABLE "public"."vendor_join_requests" IS 'Vendor onboarding requests awaiting approval';



CREATE TABLE IF NOT EXISTS "public"."vendor_registration_payments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "vendor_id" "uuid" NOT NULL,
    "razorpay_order_id" character varying(40),
    "razorpay_payment_id" character varying(40),
    "razorpay_signature" character varying(255),
    "amount" numeric(10,2) NOT NULL,
    "currency" character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    "payment_method" character varying(50),
    "status" "public"."payment_status" DEFAULT 'pending'::"public"."payment_status" NOT NULL,
    "payment_initiated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "payment_completed_at" timestamp with time zone,
    "payment_failed_at" timestamp with time zone,
    "failure_reason" "text",
    "error_code" character varying(50),
    "error_description" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    CONSTRAINT "valid_vendor_payment_status" CHECK (((("status" = 'pending'::"public"."payment_status") AND ("payment_completed_at" IS NULL) AND ("payment_failed_at" IS NULL)) OR (("status" = 'success'::"public"."payment_status") AND ("payment_completed_at" IS NOT NULL)) OR (("status" = 'failed'::"public"."payment_status") AND ("payment_failed_at" IS NOT NULL)))),
    CONSTRAINT "vendor_registration_payments_amount_check" CHECK (("amount" >= (0)::numeric))
);


ALTER TABLE "public"."vendor_registration_payments" OWNER TO "postgres";


COMMENT ON TABLE "public"."vendor_registration_payments" IS 'Razorpay payment records for vendor one-time registration fees';



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_razorpay_order_id_key" UNIQUE ("razorpay_order_id");



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_razorpay_payment_id_key" UNIQUE ("razorpay_payment_id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_booking_number_key" UNIQUE ("booking_number");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_user_id_service_id_key" UNIQUE ("user_id", "service_id");



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_user_id_salon_id_key" UNIQUE ("user_id", "salon_id");



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "one_review_per_booking" UNIQUE ("booking_id");



COMMENT ON CONSTRAINT "one_review_per_booking" ON "public"."reviews" IS 'One review per booking (prevents spam)';



ALTER TABLE ONLY "public"."phone_verification_codes"
    ADD CONSTRAINT "phone_verification_codes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rm_profiles"
    ADD CONSTRAINT "rm_profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rm_score_history"
    ADD CONSTRAINT "rm_score_history_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."salon_staff"
    ADD CONSTRAINT "salon_staff_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."salon_subscriptions"
    ADD CONSTRAINT "salon_subscriptions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."service_categories"
    ADD CONSTRAINT "service_categories_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."service_categories"
    ADD CONSTRAINT "service_categories_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."staff_availability"
    ADD CONSTRAINT "staff_availability_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."staff_availability"
    ADD CONSTRAINT "staff_availability_staff_id_day_of_week_key" UNIQUE ("staff_id", "day_of_week");



ALTER TABLE ONLY "public"."token_blacklist"
    ADD CONSTRAINT "token_blacklist_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."token_blacklist"
    ADD CONSTRAINT "token_blacklist_token_jti_key" UNIQUE ("token_jti");



ALTER TABLE ONLY "public"."vendor_join_requests"
    ADD CONSTRAINT "vendor_join_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_razorpay_order_id_key" UNIQUE ("razorpay_order_id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_razorpay_payment_id_key" UNIQUE ("razorpay_payment_id");



CREATE INDEX "idx_audit_logs_action" ON "public"."audit_logs" USING "btree" ("action");



CREATE INDEX "idx_audit_logs_created_at" ON "public"."audit_logs" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_audit_logs_table_record" ON "public"."audit_logs" USING "btree" ("table_name", "record_id");



CREATE INDEX "idx_audit_logs_user_id" ON "public"."audit_logs" USING "btree" ("user_id");



CREATE INDEX "idx_booking_payments_booking_id" ON "public"."booking_payments" USING "btree" ("booking_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_booking_payments_customer_id" ON "public"."booking_payments" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_booking_payments_deleted_at" ON "public"."booking_payments" USING "btree" ("deleted_at");



CREATE INDEX "idx_booking_payments_payment_type" ON "public"."booking_payments" USING "btree" ("payment_type") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_booking_payments_razorpay_order" ON "public"."booking_payments" USING "btree" ("razorpay_order_id");



CREATE INDEX "idx_booking_payments_razorpay_payment" ON "public"."booking_payments" USING "btree" ("razorpay_payment_id");



CREATE INDEX "idx_booking_payments_refund" ON "public"."booking_payments" USING "btree" ("refund_initiated", "refund_completed") WHERE ("refund_initiated" = true);



CREATE INDEX "idx_booking_payments_status" ON "public"."booking_payments" USING "btree" ("status") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_booking_number" ON "public"."bookings" USING "btree" ("booking_number");



CREATE INDEX "idx_bookings_customer_id" ON "public"."bookings" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_date" ON "public"."bookings" USING "btree" ("booking_date") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_datetime" ON "public"."bookings" USING "btree" ("booking_date", "booking_time") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_deleted_at" ON "public"."bookings" USING "btree" ("deleted_at");



CREATE UNIQUE INDEX "idx_bookings_no_double_booking" ON "public"."bookings" USING "btree" ("salon_id", "booking_date", "booking_time") WHERE (("status" <> ALL (ARRAY['cancelled'::"public"."booking_status", 'completed'::"public"."booking_status"])) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_bookings_payment_status" ON "public"."bookings" USING "btree" ("convenience_fee_paid", "service_price_paid") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_salon_id" ON "public"."bookings" USING "btree" ("salon_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_service_id" ON "public"."bookings" USING "btree" ("service_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_status" ON "public"."bookings" USING "btree" ("status") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_cart_items_salon_id" ON "public"."cart_items" USING "btree" ("salon_id");



CREATE INDEX "idx_cart_items_user_id" ON "public"."cart_items" USING "btree" ("user_id");



CREATE INDEX "idx_favorites_created_at" ON "public"."favorites" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_favorites_salon_id" ON "public"."favorites" USING "btree" ("salon_id");



CREATE INDEX "idx_favorites_user_id" ON "public"."favorites" USING "btree" ("user_id");



CREATE INDEX "idx_phone_otp_created" ON "public"."phone_verification_codes" USING "btree" ("created_at");



CREATE INDEX "idx_phone_otp_expires" ON "public"."phone_verification_codes" USING "btree" ("expires_at") WHERE ("verified" = false);



CREATE INDEX "idx_phone_otp_phone" ON "public"."phone_verification_codes" USING "btree" ("phone") WHERE ("verified" = false);



CREATE INDEX "idx_profiles_city_state" ON "public"."profiles" USING "btree" ("city", "state") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_profiles_deleted_at" ON "public"."profiles" USING "btree" ("deleted_at");



CREATE INDEX "idx_profiles_email" ON "public"."profiles" USING "btree" ("email") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_profiles_phone" ON "public"."profiles" USING "btree" ("phone") WHERE (("phone" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE UNIQUE INDEX "idx_profiles_phone_unique" ON "public"."profiles" USING "btree" ("phone") WHERE (("phone_verified" = true) AND ("phone" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_profiles_user_role" ON "public"."profiles" USING "btree" ("user_role");



CREATE INDEX "idx_reviews_customer_id" ON "public"."reviews" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_reviews_deleted_at" ON "public"."reviews" USING "btree" ("deleted_at");



CREATE INDEX "idx_reviews_featured" ON "public"."reviews" USING "btree" ("is_featured") WHERE (("is_featured" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_reviews_hidden" ON "public"."reviews" USING "btree" ("is_hidden") WHERE ("is_hidden" = true);



CREATE INDEX "idx_reviews_rating" ON "public"."reviews" USING "btree" ("rating") WHERE (("deleted_at" IS NULL) AND ("is_hidden" = false));



CREATE INDEX "idx_reviews_salon_id" ON "public"."reviews" USING "btree" ("salon_id") WHERE (("deleted_at" IS NULL) AND ("is_hidden" = false));



CREATE INDEX "idx_reviews_service_id" ON "public"."reviews" USING "btree" ("service_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_reviews_verified" ON "public"."reviews" USING "btree" ("is_verified") WHERE (("is_verified" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_rm_profiles_active" ON "public"."rm_profiles" USING "btree" ("is_active");



CREATE INDEX "idx_rm_score_history_created_at" ON "public"."rm_score_history" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_rm_score_history_rm_id" ON "public"."rm_score_history" USING "btree" ("rm_id");



CREATE INDEX "idx_salon_staff_salon_id" ON "public"."salon_staff" USING "btree" ("salon_id");



CREATE INDEX "idx_salon_staff_user_id" ON "public"."salon_staff" USING "btree" ("user_id") WHERE ("user_id" IS NOT NULL);



CREATE INDEX "idx_salon_subscriptions_end_date" ON "public"."salon_subscriptions" USING "btree" ("end_date") WHERE (("status")::"text" = 'active'::"text");



CREATE INDEX "idx_salon_subscriptions_salon_id" ON "public"."salon_subscriptions" USING "btree" ("salon_id");



CREATE INDEX "idx_salon_subscriptions_status" ON "public"."salon_subscriptions" USING "btree" ("status");



CREATE INDEX "idx_salons_active_verified" ON "public"."salons" USING "btree" ("is_active", "is_verified", "registration_fee_paid") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_assigned_rm" ON "public"."salons" USING "btree" ("assigned_rm") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_city_state" ON "public"."salons" USING "btree" ("city", "state") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_deleted_at" ON "public"."salons" USING "btree" ("deleted_at");



CREATE UNIQUE INDEX "idx_salons_gst_unique" ON "public"."salons" USING "btree" ("gst_number") WHERE (("gst_number" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_salons_location" ON "public"."salons" USING "gist" ("location") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_rating" ON "public"."salons" USING "btree" ("average_rating" DESC) WHERE (("is_active" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_salons_vendor_id" ON "public"."salons" USING "btree" ("vendor_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_service_categories_active" ON "public"."service_categories" USING "btree" ("is_active", "display_order");



CREATE INDEX "idx_services_active" ON "public"."services" USING "btree" ("is_active") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_services_category_id" ON "public"."services" USING "btree" ("category_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_services_deleted_at" ON "public"."services" USING "btree" ("deleted_at");



CREATE INDEX "idx_services_featured" ON "public"."services" USING "btree" ("is_featured") WHERE (("is_featured" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_services_price" ON "public"."services" USING "btree" ("price") WHERE (("is_active" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_services_salon_id" ON "public"."services" USING "btree" ("salon_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_staff_availability_staff_id" ON "public"."staff_availability" USING "btree" ("staff_id");



CREATE INDEX "idx_token_blacklist_expires" ON "public"."token_blacklist" USING "btree" ("expires_at");



CREATE INDEX "idx_token_blacklist_jti" ON "public"."token_blacklist" USING "btree" ("token_jti");



CREATE INDEX "idx_token_blacklist_user_id" ON "public"."token_blacklist" USING "btree" ("user_id");



CREATE INDEX "idx_vendor_join_requests_status" ON "public"."vendor_join_requests" USING "btree" ("status");



CREATE INDEX "idx_vendor_join_requests_user_id" ON "public"."vendor_join_requests" USING "btree" ("user_id");



CREATE INDEX "idx_vendor_registration_payments_razorpay_order" ON "public"."vendor_registration_payments" USING "btree" ("razorpay_order_id");



CREATE INDEX "idx_vendor_registration_payments_razorpay_payment" ON "public"."vendor_registration_payments" USING "btree" ("razorpay_payment_id");



CREATE INDEX "idx_vendor_registration_payments_status" ON "public"."vendor_registration_payments" USING "btree" ("status");



CREATE INDEX "idx_vendor_registration_payments_vendor" ON "public"."vendor_registration_payments" USING "btree" ("vendor_id");



CREATE OR REPLACE TRIGGER "set_booking_number" BEFORE INSERT ON "public"."bookings" FOR EACH ROW WHEN ((("new"."booking_number" IS NULL) OR (("new"."booking_number")::"text" = ''::"text"))) EXECUTE FUNCTION "public"."generate_booking_number"();



CREATE OR REPLACE TRIGGER "set_salon_location" BEFORE INSERT OR UPDATE OF "latitude", "longitude" ON "public"."salons" FOR EACH ROW EXECUTE FUNCTION "public"."update_salon_location"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."booking_payments" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."bookings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."profiles" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."reviews" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."salons" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."service_categories" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."services" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."vendor_registration_payments" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_salon_rating_on_review_delete" AFTER UPDATE ON "public"."reviews" FOR EACH ROW WHEN ((("old"."deleted_at" IS NULL) AND ("new"."deleted_at" IS NOT NULL))) EXECUTE FUNCTION "public"."update_salon_rating"();



CREATE OR REPLACE TRIGGER "update_salon_rating_on_review_insert" AFTER INSERT ON "public"."reviews" FOR EACH ROW EXECUTE FUNCTION "public"."update_salon_rating"();



CREATE OR REPLACE TRIGGER "update_salon_rating_on_review_update" AFTER UPDATE ON "public"."reviews" FOR EACH ROW WHEN ((("old"."rating" IS DISTINCT FROM "new"."rating") OR ("old"."is_hidden" IS DISTINCT FROM "new"."is_hidden") OR ("old"."deleted_at" IS DISTINCT FROM "new"."deleted_at"))) EXECUTE FUNCTION "public"."update_salon_rating"();



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_booking_id_fkey" FOREIGN KEY ("booking_id") REFERENCES "public"."bookings"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."booking_payments"
    ADD CONSTRAINT "booking_payments_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_service_id_fkey" FOREIGN KEY ("service_id") REFERENCES "public"."services"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_service_id_fkey" FOREIGN KEY ("service_id") REFERENCES "public"."services"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_booking_id_fkey" FOREIGN KEY ("booking_id") REFERENCES "public"."bookings"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_service_id_fkey" FOREIGN KEY ("service_id") REFERENCES "public"."services"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."rm_profiles"
    ADD CONSTRAINT "rm_profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."rm_score_history"
    ADD CONSTRAINT "rm_score_history_rm_id_fkey" FOREIGN KEY ("rm_id") REFERENCES "public"."rm_profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."salon_staff"
    ADD CONSTRAINT "salon_staff_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."salon_staff"
    ADD CONSTRAINT "salon_staff_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."salon_subscriptions"
    ADD CONSTRAINT "salon_subscriptions_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salon_subscriptions"
    ADD CONSTRAINT "salon_subscriptions_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salon_subscriptions"
    ADD CONSTRAINT "salon_subscriptions_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."salon_subscriptions"
    ADD CONSTRAINT "salon_subscriptions_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_assigned_rm_fkey" FOREIGN KEY ("assigned_rm") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "auth"."users"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_verified_by_fkey" FOREIGN KEY ("verified_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_category_id_fkey" FOREIGN KEY ("category_id") REFERENCES "public"."service_categories"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."staff_availability"
    ADD CONSTRAINT "staff_availability_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "public"."salon_staff"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."token_blacklist"
    ADD CONSTRAINT "token_blacklist_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."vendor_join_requests"
    ADD CONSTRAINT "vendor_join_requests_reviewed_by_fkey" FOREIGN KEY ("reviewed_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."vendor_join_requests"
    ADD CONSTRAINT "vendor_join_requests_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



CREATE POLICY "Active categories viewable by everyone" ON "public"."service_categories" FOR SELECT USING (("is_active" = true));



CREATE POLICY "Active salons are viewable by everyone" ON "public"."salons" FOR SELECT USING ((("is_verified" = true) AND ("is_active" = true) AND ("deleted_at" IS NULL)));



CREATE POLICY "Active services viewable by everyone" ON "public"."services" FOR SELECT USING ((("is_active" = true) AND ("deleted_at" IS NULL)));



CREATE POLICY "Active staff viewable by everyone" ON "public"."salon_staff" FOR SELECT USING (("is_active" = true));



CREATE POLICY "Admins and RMs can manage salons" ON "public"."salons" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = ANY (ARRAY['admin'::"public"."user_role", 'relationship_manager'::"public"."user_role"]))))));



CREATE POLICY "Admins and RMs can update join requests" ON "public"."vendor_join_requests" FOR UPDATE USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = ANY (ARRAY['admin'::"public"."user_role", 'relationship_manager'::"public"."user_role"]))))));



CREATE POLICY "Admins and RMs can view join requests" ON "public"."vendor_join_requests" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = ANY (ARRAY['admin'::"public"."user_role", 'relationship_manager'::"public"."user_role"]))))));



CREATE POLICY "Admins can manage RMs" ON "public"."rm_profiles" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage all bookings" ON "public"."bookings" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage all payments" ON "public"."booking_payments" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage all reviews" ON "public"."reviews" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage all services" ON "public"."services" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage all staff" ON "public"."salon_staff" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage categories" ON "public"."service_categories" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage registration payments" ON "public"."vendor_registration_payments" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can manage subscriptions" ON "public"."salon_subscriptions" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can view RMs" ON "public"."rm_profiles" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = ANY (ARRAY['admin'::"public"."user_role", 'relationship_manager'::"public"."user_role"]))))));



CREATE POLICY "Admins can view all score history" ON "public"."rm_score_history" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can view audit logs" ON "public"."audit_logs" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Customers can create bookings" ON "public"."bookings" FOR INSERT WITH CHECK ((("customer_id" = "auth"."uid"()) AND (EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'customer'::"public"."user_role"))))));



CREATE POLICY "Customers can create reviews" ON "public"."reviews" FOR INSERT WITH CHECK ((("customer_id" = "auth"."uid"()) AND (EXISTS ( SELECT 1
   FROM "public"."bookings"
  WHERE (("bookings"."id" = "reviews"."booking_id") AND ("bookings"."customer_id" = "auth"."uid"()) AND ("bookings"."status" = 'completed'::"public"."booking_status"))))));



CREATE POLICY "Customers can update own bookings" ON "public"."bookings" FOR UPDATE USING ((("customer_id" = "auth"."uid"()) AND ("status" = 'pending'::"public"."booking_status"))) WITH CHECK (("customer_id" = "auth"."uid"()));



CREATE POLICY "Customers can update own reviews" ON "public"."reviews" FOR UPDATE USING (("customer_id" = "auth"."uid"())) WITH CHECK (("customer_id" = "auth"."uid"()));



CREATE POLICY "Customers can view own bookings" ON "public"."bookings" FOR SELECT USING ((("customer_id" = "auth"."uid"()) AND ("deleted_at" IS NULL)));



CREATE POLICY "Customers can view own payments" ON "public"."booking_payments" FOR SELECT USING ((("customer_id" = "auth"."uid"()) AND ("deleted_at" IS NULL)));



CREATE POLICY "Public can view reviews" ON "public"."reviews" FOR SELECT USING ((("is_hidden" = false) AND ("deleted_at" IS NULL)));



CREATE POLICY "Public profiles are viewable by everyone" ON "public"."profiles" FOR SELECT USING (("deleted_at" IS NULL));



CREATE POLICY "RMs can view own score history" ON "public"."rm_score_history" FOR SELECT USING (("rm_id" = "auth"."uid"()));



CREATE POLICY "Staff availability viewable by everyone" ON "public"."staff_availability" FOR SELECT USING (("is_available" = true));



CREATE POLICY "System can create payments" ON "public"."booking_payments" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can create registration payments" ON "public"."vendor_registration_payments" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can insert audit logs" ON "public"."audit_logs" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can insert blacklisted tokens" ON "public"."token_blacklist" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can insert score history" ON "public"."rm_score_history" FOR INSERT WITH CHECK (true);



CREATE POLICY "System can update payments" ON "public"."booking_payments" FOR UPDATE USING (true);



CREATE POLICY "System can update registration payments" ON "public"."vendor_registration_payments" FOR UPDATE USING (true);



CREATE POLICY "Users can create join requests" ON "public"."vendor_join_requests" FOR INSERT WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "Users can insert own profile" ON "public"."profiles" FOR INSERT WITH CHECK (("auth"."uid"() = "id"));



CREATE POLICY "Users can manage own cart" ON "public"."cart_items" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "Users can manage own favorites" ON "public"."favorites" USING (("user_id" = "auth"."uid"())) WITH CHECK (("user_id" = "auth"."uid"()));



CREATE POLICY "Users can update own profile" ON "public"."profiles" FOR UPDATE USING (("auth"."uid"() = "id")) WITH CHECK (("auth"."uid"() = "id"));



CREATE POLICY "Users can view own blacklisted tokens" ON "public"."token_blacklist" FOR SELECT USING (("user_id" = "auth"."uid"()));



CREATE POLICY "Users can view own join requests" ON "public"."vendor_join_requests" FOR SELECT USING (("user_id" = "auth"."uid"()));



CREATE POLICY "Vendors can create salon" ON "public"."salons" FOR INSERT WITH CHECK ((("vendor_id" = "auth"."uid"()) AND (EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'vendor'::"public"."user_role"))))));



CREATE POLICY "Vendors can manage own salon services" ON "public"."services" USING ((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "services"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"())))));



CREATE POLICY "Vendors can manage salon staff" ON "public"."salon_staff" USING ((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "salon_staff"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"())))));



CREATE POLICY "Vendors can manage staff availability" ON "public"."staff_availability" USING ((EXISTS ( SELECT 1
   FROM ("public"."salon_staff"
     JOIN "public"."salons" ON (("salons"."id" = "salon_staff"."salon_id")))
  WHERE (("salon_staff"."id" = "staff_availability"."staff_id") AND ("salons"."vendor_id" = "auth"."uid"())))));



CREATE POLICY "Vendors can respond to reviews" ON "public"."reviews" FOR UPDATE USING ((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "reviews"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "reviews"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"())))));



CREATE POLICY "Vendors can update own salon" ON "public"."salons" FOR UPDATE USING (("vendor_id" = "auth"."uid"())) WITH CHECK (("vendor_id" = "auth"."uid"()));



CREATE POLICY "Vendors can update salon bookings" ON "public"."bookings" FOR UPDATE USING ((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "bookings"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"())))));



CREATE POLICY "Vendors can view own registration payments" ON "public"."vendor_registration_payments" FOR SELECT USING (("vendor_id" = "auth"."uid"()));



CREATE POLICY "Vendors can view own subscriptions" ON "public"."salon_subscriptions" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "salon_subscriptions"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"())))));



CREATE POLICY "Vendors can view salon bookings" ON "public"."bookings" FOR SELECT USING (((EXISTS ( SELECT 1
   FROM "public"."salons"
  WHERE (("salons"."id" = "bookings"."salon_id") AND ("salons"."vendor_id" = "auth"."uid"())))) AND ("deleted_at" IS NULL)));



CREATE POLICY "Vendors can view salon payments" ON "public"."booking_payments" FOR SELECT USING (((EXISTS ( SELECT 1
   FROM ("public"."bookings"
     JOIN "public"."salons" ON (("salons"."id" = "bookings"."salon_id")))
  WHERE (("bookings"."id" = "booking_payments"."booking_id") AND ("salons"."vendor_id" = "auth"."uid"())))) AND ("deleted_at" IS NULL)));



ALTER TABLE "public"."booking_payments" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."bookings" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."cart_items" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."favorites" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."profiles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."reviews" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."rm_profiles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."rm_score_history" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."salon_staff" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."salons" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."service_categories" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."services" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."staff_availability" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."token_blacklist" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."vendor_registration_payments" ENABLE ROW LEVEL SECURITY;


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON FUNCTION "public"."generate_booking_number"() TO "anon";
GRANT ALL ON FUNCTION "public"."generate_booking_number"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."generate_booking_number"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_salon_location"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_salon_location"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_salon_location"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_salon_rating"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_salon_rating"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_salon_rating"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";



GRANT ALL ON TABLE "public"."audit_logs" TO "anon";
GRANT ALL ON TABLE "public"."audit_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."audit_logs" TO "service_role";



GRANT ALL ON TABLE "public"."booking_payments" TO "anon";
GRANT ALL ON TABLE "public"."booking_payments" TO "authenticated";
GRANT ALL ON TABLE "public"."booking_payments" TO "service_role";



GRANT ALL ON TABLE "public"."bookings" TO "anon";
GRANT ALL ON TABLE "public"."bookings" TO "authenticated";
GRANT ALL ON TABLE "public"."bookings" TO "service_role";



GRANT ALL ON TABLE "public"."cart_items" TO "anon";
GRANT ALL ON TABLE "public"."cart_items" TO "authenticated";
GRANT ALL ON TABLE "public"."cart_items" TO "service_role";



GRANT ALL ON TABLE "public"."favorites" TO "anon";
GRANT ALL ON TABLE "public"."favorites" TO "authenticated";
GRANT ALL ON TABLE "public"."favorites" TO "service_role";



GRANT ALL ON TABLE "public"."phone_verification_codes" TO "anon";
GRANT ALL ON TABLE "public"."phone_verification_codes" TO "authenticated";
GRANT ALL ON TABLE "public"."phone_verification_codes" TO "service_role";



GRANT ALL ON TABLE "public"."profiles" TO "anon";
GRANT ALL ON TABLE "public"."profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."profiles" TO "service_role";



GRANT ALL ON TABLE "public"."reviews" TO "anon";
GRANT ALL ON TABLE "public"."reviews" TO "authenticated";
GRANT ALL ON TABLE "public"."reviews" TO "service_role";



GRANT ALL ON TABLE "public"."rm_profiles" TO "anon";
GRANT ALL ON TABLE "public"."rm_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."rm_profiles" TO "service_role";



GRANT ALL ON TABLE "public"."rm_score_history" TO "anon";
GRANT ALL ON TABLE "public"."rm_score_history" TO "authenticated";
GRANT ALL ON TABLE "public"."rm_score_history" TO "service_role";



GRANT ALL ON TABLE "public"."salon_staff" TO "anon";
GRANT ALL ON TABLE "public"."salon_staff" TO "authenticated";
GRANT ALL ON TABLE "public"."salon_staff" TO "service_role";



GRANT ALL ON TABLE "public"."salon_subscriptions" TO "anon";
GRANT ALL ON TABLE "public"."salon_subscriptions" TO "authenticated";
GRANT ALL ON TABLE "public"."salon_subscriptions" TO "service_role";



GRANT ALL ON TABLE "public"."salons" TO "anon";
GRANT ALL ON TABLE "public"."salons" TO "authenticated";
GRANT ALL ON TABLE "public"."salons" TO "service_role";



GRANT ALL ON TABLE "public"."service_categories" TO "anon";
GRANT ALL ON TABLE "public"."service_categories" TO "authenticated";
GRANT ALL ON TABLE "public"."service_categories" TO "service_role";



GRANT ALL ON TABLE "public"."services" TO "anon";
GRANT ALL ON TABLE "public"."services" TO "authenticated";
GRANT ALL ON TABLE "public"."services" TO "service_role";



GRANT ALL ON TABLE "public"."staff_availability" TO "anon";
GRANT ALL ON TABLE "public"."staff_availability" TO "authenticated";
GRANT ALL ON TABLE "public"."staff_availability" TO "service_role";



GRANT ALL ON TABLE "public"."token_blacklist" TO "anon";
GRANT ALL ON TABLE "public"."token_blacklist" TO "authenticated";
GRANT ALL ON TABLE "public"."token_blacklist" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_join_requests" TO "anon";
GRANT ALL ON TABLE "public"."vendor_join_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_join_requests" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_registration_payments" TO "anon";
GRANT ALL ON TABLE "public"."vendor_registration_payments" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_registration_payments" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";







