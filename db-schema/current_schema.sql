
-- GENERATED FILE - do not hand-edit.
--
-- Live `public` schema of the linked Supabase project (lubist_staging,
-- ref uqcckstwaddrnxxwgtov), dumped straight from the database - this is the
-- actual current state after every applied migration, not a hand-maintained
-- snapshot. Kept outside supabase/ (which the Supabase CLI owns: migrations,
-- config.toml, seed data) so it's clearly a read-only reference, not
-- something `supabase` tooling will look at or manage.
--
-- Regenerate after applying new migrations:
--   supabase db dump --linked --schema public -f db-schema/current_schema.sql
-- (needs Docker Desktop running and the project linked - `supabase link`.)
--
-- Last generated: 2026-09-05

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



CREATE TYPE "public"."feature_status" AS ENUM (
    'internal',
    'enabled',
    'disabled'
);


ALTER TYPE "public"."feature_status" OWNER TO "postgres";


COMMENT ON TYPE "public"."feature_status" IS 'internal = built but unsold (staff only) | enabled = client has it | disabled = kill switch, off for everyone';



CREATE TYPE "public"."outlet_type" AS ENUM (
    'franchisee',
    'Company owned'
);


ALTER TYPE "public"."outlet_type" OWNER TO "postgres";


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
    'customer',
    'regular_buyer'
);


ALTER TYPE "public"."user_role" OWNER TO "postgres";


COMMENT ON TYPE "public"."user_role" IS 'User role for authorization (stored in JWT claims)';



CREATE OR REPLACE FUNCTION "public"."cleanup_old_otp_attempts"() RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    DELETE FROM public.otp_attempts
    WHERE created_at < NOW() - INTERVAL '7 days';

    RAISE NOTICE 'Cleaned up old OTP attempts';
END;
$$;


ALTER FUNCTION "public"."cleanup_old_otp_attempts"() OWNER TO "postgres";


COMMENT ON FUNCTION "public"."cleanup_old_otp_attempts"() IS 'Cleanup OTP attempts older than 7 days. Should be run daily via cron job.';



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


CREATE OR REPLACE FUNCTION "public"."get_booking_payment_status"("p_booking_id" "uuid") RETURNS TABLE("booking_id" "uuid", "convenience_fee_paid" boolean, "service_paid" boolean, "fully_paid" boolean, "total_paid" numeric, "total_pending" numeric)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT 
    p_booking_id,
    COALESCE(MAX(CASE WHEN payment_type = 'convenience_fee' AND status = 'success' THEN TRUE ELSE FALSE END), FALSE) as convenience_fee_paid,
    COALESCE(MAX(CASE WHEN payment_type = 'service_payment' AND status = 'success' THEN TRUE ELSE FALSE END), FALSE) as service_paid,
    COALESCE(
      MAX(CASE WHEN payment_type = 'convenience_fee' AND status = 'success' THEN TRUE ELSE FALSE END) AND
      MAX(CASE WHEN payment_type = 'service_payment' AND status = 'success' THEN TRUE ELSE FALSE END),
      FALSE
    ) as fully_paid,
    COALESCE(SUM(CASE WHEN status = 'success' THEN amount ELSE 0 END), 0) as total_paid,
    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0) as total_pending
  FROM payments
  WHERE booking_id = p_booking_id
    AND deleted_at IS NULL;
END;
$$;


ALTER FUNCTION "public"."get_booking_payment_status"("p_booking_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_nearby_salons"("user_lat" double precision, "user_lon" double precision, "radius_km" double precision DEFAULT 10.0, "max_results" integer DEFAULT 50) RETURNS TABLE("id" "uuid", "business_name" character varying, "description" "text", "address" "text", "city" character varying, "state" character varying, "pincode" character varying, "phone" character varying, "email" character varying, "latitude" numeric, "longitude" numeric, "location" "public"."geography", "average_rating" numeric, "total_reviews" integer, "logo_url" "text", "cover_images" "text"[], "opening_time" time without time zone, "closing_time" time without time zone, "working_days" character varying[], "is_active" boolean, "is_verified" boolean, "registration_fee_paid" boolean, "vendor_id" "uuid", "assigned_rm" "uuid", "distance_km" double precision, "created_at" timestamp with time zone)
    LANGUAGE "plpgsql" STABLE
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id,
        s.business_name,
        s.description,
        s.address,
        s.city,
        s.state,
        s.pincode,
        s.phone,
        s.email,
        s.latitude,
        s.longitude,
        s.location,
        s.average_rating,
        s.total_reviews,
        s.logo_url,
        s.cover_images,
        s.opening_time,
        s.closing_time,
        s.working_days,
        s.is_active,
        s.is_verified,
        s.registration_fee_paid,
        s.vendor_id,
        s.assigned_rm,
        -- Calculate distance in kilometers using PostGIS
        ST_Distance(
            s.location::geography,
            ST_SetSRID(ST_MakePoint(user_lon, user_lat), 4326)::geography
        ) / 1000.0 AS distance_km,
        s.created_at
    FROM 
        salons s
    WHERE 
        s.is_active = true
        AND s.is_verified = true
        AND s.registration_fee_paid = true
        AND s.deleted_at IS NULL
        AND s.location IS NOT NULL
        -- Filter by radius using PostGIS distance function
        AND ST_DWithin(
            s.location::geography,
            ST_SetSRID(ST_MakePoint(user_lon, user_lat), 4326)::geography,
            radius_km * 1000  -- Convert km to meters
        )
    ORDER BY 
        distance_km ASC
    LIMIT max_results;
END;
$$;


ALTER FUNCTION "public"."get_nearby_salons"("user_lat" double precision, "user_lon" double precision, "radius_km" double precision, "max_results" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_nearby_salons"("user_lat" double precision, "user_lon" double precision, "radius_km" double precision, "max_results" integer) IS 'Find salons within a radius using PostGIS spatial queries';



CREATE OR REPLACE FUNCTION "public"."get_popular_cities"("result_limit" integer DEFAULT 8) RETURNS TABLE("city" "text", "salon_count" bigint)
    LANGUAGE "plpgsql" STABLE
    AS $$
BEGIN
  RETURN QUERY
  SELECT 
    LOWER(TRIM(s.city)) as city,
    COUNT(*)::BIGINT as salon_count
  FROM salons s
  WHERE s.is_active = true 
    AND s.is_verified = true 
    AND s.registration_fee_paid = true
    AND s.city IS NOT NULL
    AND TRIM(s.city) != ''
  GROUP BY LOWER(TRIM(s.city))
  ORDER BY salon_count DESC, city ASC
  LIMIT result_limit;
END;
$$;


ALTER FUNCTION "public"."get_popular_cities"("result_limit" integer) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."get_popular_cities"("result_limit" integer) IS 'Returns top cities by salon count. Only includes active, verified salons. Case-insensitive city matching.';



CREATE OR REPLACE FUNCTION "public"."record_service_payment"("p_booking_id" "uuid", "p_amount" numeric, "p_payment_method" character varying, "p_recorded_by" "uuid", "p_notes" "text" DEFAULT NULL::"text") RETURNS "uuid"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_payment_id UUID;
  v_customer_id UUID;
BEGIN
  -- Get customer_id from booking
  SELECT customer_id INTO v_customer_id
  FROM bookings
  WHERE id = p_booking_id AND deleted_at IS NULL;
  
  IF v_customer_id IS NULL THEN
    RAISE EXCEPTION 'Booking not found: %', p_booking_id;
  END IF;
  
  -- Insert service payment record
  INSERT INTO payments (
    booking_id,
    customer_id,
    payment_type,
    amount,
    payment_method,
    status,
    paid_at,
    notes,
    created_by,
    updated_by
  ) VALUES (
    p_booking_id,
    v_customer_id,
    'service_payment',
    p_amount,
    p_payment_method,
    'success',
    now(),
    p_notes,
    p_recorded_by,
    p_recorded_by
  )
  RETURNING id INTO v_payment_id;
  
  -- Update deprecated service_paid flag in bookings for backward compatibility
  UPDATE bookings
  SET service_paid = TRUE,
      updated_by = p_recorded_by,
      updated_at = now()
  WHERE id = p_booking_id;
  
  RETURN v_payment_id;
END;
$$;


ALTER FUNCTION "public"."record_service_payment"("p_booking_id" "uuid", "p_amount" numeric, "p_payment_method" character varying, "p_recorded_by" "uuid", "p_notes" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."redeem_coupon"("p_coupon_id" "uuid", "p_user_id" "uuid", "p_booking_id" "uuid", "p_discount_amount" numeric, "p_gross_discount" numeric DEFAULT NULL::numeric) RETURNS TABLE("success" boolean, "reason" "text", "was_already_redeemed" boolean)
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
    v_coupon           RECORD;
    v_booking          RECORD;
    v_user_redemptions INTEGER;
    v_prior_bookings   INTEGER;
    v_existing         UUID;
    v_now              TIMESTAMPTZ := now();
BEGIN
    -- Idempotency: this coupon already redeemed for this booking
    SELECT id INTO v_existing
    FROM coupon_redemptions
    WHERE coupon_id = p_coupon_id AND booking_id = p_booking_id;

    IF FOUND THEN
        RETURN QUERY SELECT TRUE, 'already_redeemed'::TEXT, TRUE;
        RETURN;
    END IF;

    -- Lock the coupon row so concurrent redemptions serialize on it
    SELECT * INTO v_coupon
    FROM coupons
    WHERE id = p_coupon_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'coupon_not_found'::TEXT, FALSE;
        RETURN;
    END IF;

    IF NOT v_coupon.is_active THEN
        RETURN QUERY SELECT FALSE, 'coupon_inactive'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Validity window (was previously NOT re-checked at redemption)
    IF v_coupon.valid_from IS NOT NULL AND v_now < v_coupon.valid_from THEN
        RETURN QUERY SELECT FALSE, 'not_started'::TEXT, FALSE;
        RETURN;
    END IF;
    IF v_coupon.valid_until IS NOT NULL AND v_now > v_coupon.valid_until THEN
        RETURN QUERY SELECT FALSE, 'expired'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Booking is needed for salon scope + first-time + snapshot
    SELECT id, salon_id, customer_id INTO v_booking
    FROM bookings
    WHERE id = p_booking_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'booking_not_found'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Salon scope: vendor coupons only at their salon
    IF v_coupon.scope = 'vendor'
       AND v_coupon.salon_id IS DISTINCT FROM v_booking.salon_id THEN
        RETURN QUERY SELECT FALSE, 'wrong_salon'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Total usage limit
    IF v_coupon.usage_limit_total IS NOT NULL
       AND v_coupon.used_count >= v_coupon.usage_limit_total THEN
        RETURN QUERY SELECT FALSE, 'total_limit_reached'::TEXT, FALSE;
        RETURN;
    END IF;

    -- Per-user usage limit
    IF v_coupon.usage_limit_per_user IS NOT NULL THEN
        SELECT COUNT(*) INTO v_user_redemptions
        FROM coupon_redemptions
        WHERE coupon_id = p_coupon_id AND user_id = p_user_id;

        IF v_user_redemptions >= v_coupon.usage_limit_per_user THEN
            RETURN QUERY SELECT FALSE, 'per_user_limit_reached'::TEXT, FALSE;
            RETURN;
        END IF;
    END IF;

    -- First-time restriction (enforced here so a NULL per-user limit cannot be
    -- abused, and concurrent first bookings cannot both pass). Excludes the
    -- current booking, cancelled bookings and soft-deleted rows (D3).
    IF v_coupon.first_time_scope IS NOT NULL THEN
        SELECT COUNT(*) INTO v_prior_bookings
        FROM bookings b
        WHERE b.customer_id = p_user_id
          AND b.id <> p_booking_id
          AND b.deleted_at IS NULL
          AND b.status <> 'cancelled'
          AND (
              v_coupon.first_time_scope <> 'vendor'
              OR b.salon_id = v_coupon.salon_id
          );

        IF v_prior_bookings > 0 THEN
            RETURN QUERY SELECT FALSE, 'not_first_time'::TEXT, FALSE;
            RETURN;
        END IF;
    END IF;

    -- Record redemption (+ snapshot) and bump cached counter (same transaction)
    INSERT INTO coupon_redemptions (
        coupon_id, user_id, booking_id, discount_amount,
        gross_discount, salon_id, coupon_code, funded_by, scope
    )
    VALUES (
        p_coupon_id, p_user_id, p_booking_id, COALESCE(p_discount_amount, 0),
        COALESCE(p_gross_discount, p_discount_amount, 0),
        v_booking.salon_id, v_coupon.code, v_coupon.funded_by, v_coupon.scope
    );

    UPDATE coupons SET used_count = used_count + 1 WHERE id = p_coupon_id;

    RETURN QUERY SELECT TRUE, 'redeemed'::TEXT, FALSE;
END;
$$;


ALTER FUNCTION "public"."redeem_coupon"("p_coupon_id" "uuid", "p_user_id" "uuid", "p_booking_id" "uuid", "p_discount_amount" numeric, "p_gross_discount" numeric) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."redeem_coupon"("p_coupon_id" "uuid", "p_user_id" "uuid", "p_booking_id" "uuid", "p_discount_amount" numeric, "p_gross_discount" numeric) IS 'Atomically re-validates a coupon (active, window, scope, first-time, total & per-user limits) under FOR UPDATE and records a snapshotted redemption. Idempotent per (coupon_id, booking_id).';



CREATE OR REPLACE FUNCTION "public"."update_banners_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_banners_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_blog_posts_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_blog_posts_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_career_applications_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_career_applications_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_coupons_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_coupons_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_email_logs_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_email_logs_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_feature_flags_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();

    -- Stamp enabled_at the first time a feature is handed to the client, and
    -- clear it if it is ever pulled back, so the column always answers
    -- "since when has the client had this?"
    IF NEW.status = 'enabled' AND OLD.status <> 'enabled' THEN
        NEW.enabled_at = now();
    ELSIF NEW.status <> 'enabled' THEN
        NEW.enabled_at = NULL;
        NEW.enabled_by = NULL;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_feature_flags_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_partner_requests_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_partner_requests_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_products_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_products_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_rm_stats_counters"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- New request added (counts toward total submissions regardless of status)
        UPDATE public.rm_profiles
        SET
            total_requests_count = total_requests_count + 1,
            pending_requests_count = CASE WHEN NEW.status = 'pending' THEN pending_requests_count + 1 ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN NEW.status = 'approved' THEN approved_requests_count + 1 ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1 ELSE rejected_requests_count END,
            -- FIX: total_salons_added now counts ALL submissions (denominator for approval rate)
            total_salons_added = total_salons_added + 1,
            total_approved_salons = CASE WHEN NEW.status = 'approved' THEN total_approved_salons + 1 ELSE total_approved_salons END,
            updated_at = NOW()
        WHERE id = NEW.rm_id;

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Status changed. total_salons_added does NOT change (already counted at submission);
        -- only the approved counters move.
        IF OLD.status IS DISTINCT FROM NEW.status THEN
            UPDATE public.rm_profiles
            SET
                pending_requests_count = CASE
                    WHEN OLD.status = 'pending' THEN pending_requests_count - 1
                    WHEN NEW.status = 'pending' THEN pending_requests_count + 1
                    ELSE pending_requests_count
                END,
                approved_requests_count = CASE
                    WHEN OLD.status = 'approved' THEN approved_requests_count - 1
                    WHEN NEW.status = 'approved' THEN approved_requests_count + 1
                    ELSE approved_requests_count
                END,
                rejected_requests_count = CASE
                    WHEN OLD.status = 'rejected' THEN rejected_requests_count - 1
                    WHEN NEW.status = 'rejected' THEN rejected_requests_count + 1
                    ELSE rejected_requests_count
                END,
                -- FIX: do not change total_salons_added on status transitions
                total_approved_salons = CASE
                    WHEN OLD.status != 'approved' AND NEW.status = 'approved' THEN total_approved_salons + 1
                    WHEN OLD.status = 'approved' AND NEW.status != 'approved' THEN total_approved_salons - 1
                    ELSE total_approved_salons
                END,
                updated_at = NOW()
            WHERE id = NEW.rm_id;
        END IF;

        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        -- Request deleted (soft or hard delete)
        UPDATE public.rm_profiles
        SET
            total_requests_count = GREATEST(total_requests_count - 1, 0),
            pending_requests_count = CASE WHEN OLD.status = 'pending' THEN GREATEST(pending_requests_count - 1, 0) ELSE pending_requests_count END,
            approved_requests_count = CASE WHEN OLD.status = 'approved' THEN GREATEST(approved_requests_count - 1, 0) ELSE approved_requests_count END,
            rejected_requests_count = CASE WHEN OLD.status = 'rejected' THEN GREATEST(rejected_requests_count - 1, 0) ELSE rejected_requests_count END,
            -- FIX: any deleted submission decrements total_salons_added
            total_salons_added = GREATEST(total_salons_added - 1, 0),
            total_approved_salons = CASE WHEN OLD.status = 'approved' THEN GREATEST(total_approved_salons - 1, 0) ELSE total_approved_salons END,
            updated_at = NOW()
        WHERE id = OLD.rm_id;

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;


ALTER FUNCTION "public"."update_rm_stats_counters"() OWNER TO "postgres";


COMMENT ON FUNCTION "public"."update_rm_stats_counters"() IS 'Auto-updates RM statistics counters when vendor requests are inserted, updated, or deleted';



CREATE OR REPLACE FUNCTION "public"."update_salon_discount_promotions_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_salon_discount_promotions_updated_at"() OWNER TO "postgres";


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
  UPDATE salons
  SET
    average_rating = COALESCE((
      SELECT ROUND(AVG(rating)::numeric, 2)
      FROM reviews
      WHERE salon_id = COALESCE(NEW.salon_id, OLD.salon_id)
        AND deleted_at IS NULL
        AND is_hidden = false
    ), 0),
    total_reviews = (
      SELECT COUNT(*)
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


CREATE OR REPLACE FUNCTION "public"."update_service_subcategories_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_service_subcategories_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."validate_rm_stats_counters"("p_rm_id" "uuid") RETURNS TABLE("counter_name" "text", "cached_value" integer, "actual_value" bigint, "is_valid" boolean)
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'total_requests_count'::TEXT,
        rm.total_requests_count,
        COUNT(*)::BIGINT,
        rm.total_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.total_requests_count
    
    UNION ALL
    
    SELECT 
        'pending_requests_count'::TEXT,
        rm.pending_requests_count,
        COUNT(*)::BIGINT,
        rm.pending_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.status = 'pending' AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.pending_requests_count
    
    UNION ALL
    
    SELECT 
        'approved_requests_count'::TEXT,
        rm.approved_requests_count,
        COUNT(*)::BIGINT,
        rm.approved_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.status = 'approved' AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.approved_requests_count
    
    UNION ALL
    
    SELECT 
        'rejected_requests_count'::TEXT,
        rm.rejected_requests_count,
        COUNT(*)::BIGINT,
        rm.rejected_requests_count = COUNT(*)::INTEGER
    FROM public.rm_profiles rm
    LEFT JOIN public.vendor_join_requests vjr ON vjr.rm_id = rm.id AND vjr.status = 'rejected' AND vjr.deleted_at IS NULL
    WHERE rm.id = p_rm_id
    GROUP BY rm.id, rm.rejected_requests_count;
END;
$$;


ALTER FUNCTION "public"."validate_rm_stats_counters"("p_rm_id" "uuid") OWNER TO "postgres";


COMMENT ON FUNCTION "public"."validate_rm_stats_counters"("p_rm_id" "uuid") IS 'Validates cached RM statistics match actual database counts (for debugging)';



CREATE OR REPLACE FUNCTION "public"."verify_payment_and_confirm_booking"("p_razorpay_order_id" character varying, "p_razorpay_payment_id" character varying, "p_razorpay_signature" character varying) RETURNS TABLE("success" boolean, "payment_id" character varying, "booking_id" "uuid", "salon_name" character varying, "booking_date" "date", "time_slots" "text"[], "amount_paid" numeric, "was_already_verified" boolean)
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
    v_payment_record RECORD;
    v_booking_record RECORD;
    v_updated_rows INTEGER;
BEGIN
    -- ========================================================================
    -- STEP 1: Fetch payment and booking data (with lock to prevent race conditions)
    -- ========================================================================
    SELECT 
        bp.*,
        b.id as booking_id,
        b.customer_id as booking_customer_id,
        b.booking_date,
        b.time_slots,
        s.business_name as salon_name
    INTO v_payment_record
    FROM booking_payments bp
    INNER JOIN bookings b ON b.id = bp.booking_id
    INNER JOIN salons s ON s.id = b.salon_id
    WHERE bp.razorpay_order_id = p_razorpay_order_id
    FOR UPDATE OF bp; -- Lock the payment row to prevent concurrent modifications
    
    -- Check if payment exists
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Payment record not found for order_id: %', p_razorpay_order_id;
    END IF;
    
    -- ========================================================================
    -- STEP 2: Check if payment is already verified (idempotency)
    -- ========================================================================
    IF v_payment_record.status = 'completed' THEN
        -- Payment already processed, return existing data (idempotent response)
        RETURN QUERY SELECT 
            TRUE as success,
            v_payment_record.razorpay_payment_id::VARCHAR as payment_id,
            v_payment_record.booking_id::UUID,
            v_payment_record.salon_name::VARCHAR,
            v_payment_record.booking_date::DATE,
            v_payment_record.time_slots::TEXT[],
            v_payment_record.amount::NUMERIC,
            TRUE as was_already_verified;
        RETURN;
    END IF;
    
    -- ========================================================================
    -- STEP 3: ATOMIC UPDATE - Both updates happen in same transaction
    -- ========================================================================
    -- This is the key fix: Both updates are wrapped in a single transaction
    -- If anything fails, both updates are rolled back automatically
    -- PostgreSQL guarantees atomicity (all-or-nothing)
    
    -- Update 1: Mark payment as completed
    UPDATE booking_payments
    SET 
        razorpay_payment_id = p_razorpay_payment_id,
        razorpay_signature = p_razorpay_signature,
        status = 'completed',
        payment_completed_at = now(),
        updated_at = now()
    WHERE razorpay_order_id = p_razorpay_order_id
      AND status = 'pending'; -- Only update if still pending (optimistic lock)
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    -- Check if update succeeded (race condition check)
    IF v_updated_rows = 0 THEN
        -- Another request already processed this payment
        -- Re-fetch the completed payment data
        SELECT 
            bp.*,
            b.id as booking_id,
            b.booking_date,
            b.time_slots,
            s.business_name as salon_name
        INTO v_payment_record
        FROM booking_payments bp
        INNER JOIN bookings b ON b.id = bp.booking_id
        INNER JOIN salons s ON s.id = b.salon_id
        WHERE bp.razorpay_order_id = p_razorpay_order_id;
        
        RETURN QUERY SELECT 
            TRUE as success,
            v_payment_record.razorpay_payment_id::VARCHAR as payment_id,
            v_payment_record.booking_id::UUID,
            v_payment_record.salon_name::VARCHAR,
            v_payment_record.booking_date::DATE,
            v_payment_record.time_slots::TEXT[],
            v_payment_record.amount::NUMERIC,
            TRUE as was_already_verified;
        RETURN;
    END IF;
    
    -- Update 2: Mark booking as confirmed
    -- This happens in the SAME transaction as Update 1
    -- If this fails, Update 1 is automatically rolled back!
    UPDATE bookings
    SET 
        convenience_fee_paid = TRUE,
        status = 'confirmed',
        confirmed_at = now(),
        updated_at = now()
    WHERE id = v_payment_record.booking_id;
    
    -- ========================================================================
    -- STEP 4: Return success response
    -- ========================================================================
    -- Transaction commits automatically when function returns successfully
    RETURN QUERY SELECT 
        TRUE as success,
        p_razorpay_payment_id::VARCHAR as payment_id,
        v_payment_record.booking_id::UUID,
        v_payment_record.salon_name::VARCHAR,
        v_payment_record.booking_date::DATE,
        v_payment_record.time_slots::TEXT[],
        v_payment_record.amount::NUMERIC,
        FALSE as was_already_verified;
    
EXCEPTION
    WHEN OTHERS THEN
        -- Any error automatically rolls back BOTH updates
        -- This ensures data consistency
        RAISE EXCEPTION 'Payment verification failed: %', SQLERRM;
END;
$$;


ALTER FUNCTION "public"."verify_payment_and_confirm_booking"("p_razorpay_order_id" character varying, "p_razorpay_payment_id" character varying, "p_razorpay_signature" character varying) OWNER TO "postgres";


COMMENT ON FUNCTION "public"."verify_payment_and_confirm_booking"("p_razorpay_order_id" character varying, "p_razorpay_payment_id" character varying, "p_razorpay_signature" character varying) IS 'Atomically verifies payment and confirms booking in a single transaction.
Prevents data inconsistency where payment is marked complete but booking remains pending.
Implements idempotency and race condition protection.';


SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."activity_logs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "action" character varying(100) NOT NULL,
    "entity_type" character varying(50),
    "entity_id" character varying(100),
    "details" "jsonb",
    "ip_address" character varying(45),
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."activity_logs" OWNER TO "postgres";


COMMENT ON TABLE "public"."activity_logs" IS 'Audit trail for critical admin actions and system events';



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
    CONSTRAINT "audit_logs_action_check" CHECK ((("action")::"text" = ANY (ARRAY[('INSERT'::character varying)::"text", ('UPDATE'::character varying)::"text", ('DELETE'::character varying)::"text", ('SOFT_DELETE'::character varying)::"text"])))
);


ALTER TABLE "public"."audit_logs" OWNER TO "postgres";


COMMENT ON TABLE "public"."audit_logs" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."banners" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "title" "text",
    "image_url" "text" NOT NULL,
    "link_url" "text",
    "sort_order" integer DEFAULT 0 NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "starts_at" timestamp with time zone,
    "ends_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."banners" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."blog_posts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "slug" "text" NOT NULL,
    "title" "text" NOT NULL,
    "excerpt" "text",
    "content" "text" DEFAULT ''::"text" NOT NULL,
    "cover_image_url" "text",
    "cover_image_alt" "text",
    "meta_title" "text",
    "meta_description" "text",
    "focus_keyword" "text",
    "tags" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "author_name" "text",
    "status" "text" DEFAULT 'draft'::"text" NOT NULL,
    "published_at" timestamp with time zone,
    "reading_minutes" integer DEFAULT 1 NOT NULL,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "faqs" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    CONSTRAINT "blog_posts_status_check" CHECK (("status" = ANY (ARRAY['draft'::"text", 'published'::"text", 'archived'::"text"])))
);


ALTER TABLE "public"."blog_posts" OWNER TO "postgres";


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


COMMENT ON TABLE "public"."booking_payments" IS 'RLS disabled - backend uses service_role with FastAPI auth';



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
    "booking_date" "date" NOT NULL,
    "service_price" numeric(10,2) NOT NULL,
    "convenience_fee" numeric(10,2) NOT NULL,
    "total_amount" numeric(10,2) NOT NULL,
    "status" "public"."booking_status" DEFAULT 'pending'::"public"."booking_status" NOT NULL,
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
    "time_slots" "jsonb" DEFAULT '[]'::"jsonb",
    "razorpay_payment_id" "text",
    "subtotal_service_price" numeric(10,2),
    "discount_amount" numeric(10,2) DEFAULT 0 NOT NULL,
    "convenience_fee_discount" numeric(10,2) DEFAULT 0 NOT NULL,
    "coupon_id" "uuid",
    "coupon_code" "text",
    CONSTRAINT "bookings_convenience_fee_check" CHECK (("convenience_fee" >= (0)::numeric)),
    CONSTRAINT "bookings_must_have_services" CHECK ((("services" IS NOT NULL) AND ("jsonb_array_length"("services") > 0))),
    CONSTRAINT "bookings_service_price_check" CHECK (("service_price" >= (0)::numeric)),
    CONSTRAINT "bookings_total_amount_check" CHECK (("total_amount" >= (0)::numeric)),
    CONSTRAINT "time_slots_is_array" CHECK (("jsonb_typeof"("time_slots") = 'array'::"text")),
    CONSTRAINT "time_slots_max_3" CHECK (("jsonb_array_length"("time_slots") <= 3)),
    CONSTRAINT "time_slots_not_empty" CHECK (("jsonb_array_length"("time_slots") > 0)),
    CONSTRAINT "valid_booking_datetime" CHECK (("booking_date" >= CURRENT_DATE)),
    CONSTRAINT "valid_total_amount" CHECK (("total_amount" = ("service_price" + "convenience_fee")))
);


ALTER TABLE "public"."bookings" OWNER TO "postgres";


COMMENT ON TABLE "public"."bookings" IS 'Normalized bookings table. Customer data (name, phone, email) is fetched via JOIN with profiles table to maintain data consistency.';



COMMENT ON COLUMN "public"."bookings"."booking_number" IS 'Auto-generated unique booking reference (BK-YYYYMMDD-XXXXX)';



COMMENT ON COLUMN "public"."bookings"."customer_id" IS 'Foreign key to profiles.id. Use JOIN to fetch current customer name, phone, email.';



COMMENT ON COLUMN "public"."bookings"."service_price" IS 'Total service amount to be paid at salon (sum of all line_total in services array)';



COMMENT ON COLUMN "public"."bookings"."convenience_fee" IS 'Platform booking fee (6% of service_price) paid online via Razorpay';



COMMENT ON COLUMN "public"."bookings"."total_amount" IS 'Complete booking amount: service_price + convenience_fee';



COMMENT ON COLUMN "public"."bookings"."created_at" IS 'Timestamp when the booking was created. This is the true "booking time" (when customer made the booking).';



COMMENT ON COLUMN "public"."bookings"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



COMMENT ON COLUMN "public"."bookings"."duration_minutes" IS 'Total duration of all services in the booking';



COMMENT ON COLUMN "public"."bookings"."services" IS 'Historical snapshot of booked services with prices and quantities at booking time. Preserved even if service prices change or services are deleted. This JSONB array is intentionally denormalized for audit trail purposes.';



COMMENT ON COLUMN "public"."bookings"."time_slots" IS 'Array of appointment time slots (1-3 slots). This is the primary field for appointment times. Format: ["2:30 PM", "4:45 PM"]';



COMMENT ON COLUMN "public"."bookings"."razorpay_payment_id" IS 'Razorpay payment ID used for this booking. Used for idempotency checks to prevent duplicate bookings from the same payment.';



COMMENT ON COLUMN "public"."bookings"."subtotal_service_price" IS 'Service total before any coupon discount (sum of sale/discounted line totals). NULL for legacy rows.';



COMMENT ON COLUMN "public"."bookings"."discount_amount" IS 'Coupon discount applied to the service price (the "pay at salon" amount).';



COMMENT ON COLUMN "public"."bookings"."convenience_fee_discount" IS 'Coupon discount applied to the convenience fee (the online "pay now" amount).';



COMMENT ON COLUMN "public"."bookings"."coupon_id" IS 'Coupon applied to this booking, if any.';



COMMENT ON COLUMN "public"."bookings"."coupon_code" IS 'Snapshot of the coupon code used at booking time.';



COMMENT ON CONSTRAINT "bookings_must_have_services" ON "public"."bookings" IS 'Ensures booking has services array populated with at least one service';



COMMENT ON CONSTRAINT "valid_total_amount" ON "public"."bookings" IS 'Ensures total equals service price + convenience fee (all taxes included in service price)';



CREATE TABLE IF NOT EXISTS "public"."payments" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "booking_id" "uuid" NOT NULL,
    "customer_id" "uuid" NOT NULL,
    "payment_type" character varying(50) NOT NULL,
    "amount" numeric(10,2) NOT NULL,
    "currency" character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    "razorpay_order_id" character varying(100),
    "razorpay_payment_id" character varying(100),
    "razorpay_signature" character varying(255),
    "status" character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    "payment_method" character varying(50),
    "paid_at" timestamp with time zone,
    "failed_at" timestamp with time zone,
    "refunded_at" timestamp with time zone,
    "payment_metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "error_code" character varying(100),
    "error_description" "text",
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "created_by" "uuid",
    "updated_by" "uuid",
    "deleted_at" timestamp with time zone,
    "deleted_by" "uuid",
    CONSTRAINT "payment_online_requires_razorpay" CHECK (((("payment_type")::"text" <> 'convenience_fee'::"text") OR (("razorpay_payment_id" IS NOT NULL) AND ("razorpay_signature" IS NOT NULL)) OR (("status")::"text" <> 'success'::"text"))),
    CONSTRAINT "payment_success_requires_paid_at" CHECK (((("status")::"text" <> 'success'::"text") OR ("paid_at" IS NOT NULL))),
    CONSTRAINT "payments_amount_check" CHECK (("amount" >= (0)::numeric)),
    CONSTRAINT "payments_payment_type_check" CHECK ((("payment_type")::"text" = ANY ((ARRAY['convenience_fee'::character varying, 'service_payment'::character varying, 'refund'::character varying])::"text"[]))),
    CONSTRAINT "payments_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['pending'::character varying, 'success'::character varying, 'failed'::character varying, 'refunded'::character varying])::"text"[])))
);


ALTER TABLE "public"."payments" OWNER TO "postgres";


COMMENT ON TABLE "public"."payments" IS 'RLS policies added: customers can insert/view own, vendors can view/update salon payments, admins have full access';



COMMENT ON COLUMN "public"."payments"."payment_type" IS 'Type of payment: convenience_fee (online to platform), service_payment (at salon to vendor), refund';



COMMENT ON COLUMN "public"."payments"."amount" IS 'Payment amount in specified currency. For convenience_fee this includes GST.';



COMMENT ON COLUMN "public"."payments"."razorpay_order_id" IS 'Razorpay order ID (only for online payments)';



COMMENT ON COLUMN "public"."payments"."razorpay_payment_id" IS 'Razorpay payment ID (only for online payments, required for success status)';



COMMENT ON COLUMN "public"."payments"."status" IS 'Payment status: pending (not paid), success (paid), failed (payment failed), refunded (money returned)';



COMMENT ON COLUMN "public"."payments"."payment_method" IS 'Payment method: razorpay (online), cash, card, upi (at salon)';



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
    "age" integer NOT NULL,
    "gender" character varying(20) NOT NULL,
    "token_valid_after" timestamp with time zone,
    "is_internal" boolean DEFAULT false NOT NULL,
    CONSTRAINT "valid_age_range" CHECK ((("age" >= 13) AND ("age" <= 120))),
    CONSTRAINT "valid_email" CHECK ((("email")::"text" ~* '^[a-zA-Z0-9.!#$%&''*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'::"text")),
    CONSTRAINT "valid_gender_value" CHECK ((("gender")::"text" = ANY ((ARRAY['male'::character varying, 'female'::character varying, 'other'::character varying])::"text"[]))),
    CONSTRAINT "valid_phone_format" CHECK ((("phone" IS NULL) OR (("phone")::"text" ~ '^\+?[1-9]\d{1,14}$'::"text"))),
    CONSTRAINT "valid_pincode_format" CHECK ((("pincode" IS NULL) OR (("pincode")::"text" ~ '^\d{6}$'::"text")))
);


ALTER TABLE "public"."profiles" OWNER TO "postgres";


COMMENT ON TABLE "public"."profiles" IS 'RLS disabled - backend uses service_role with FastAPI auth';



COMMENT ON COLUMN "public"."profiles"."pincode" IS 'Indian 6-digit pincode (validated)';



COMMENT ON COLUMN "public"."profiles"."phone_verified" IS 'Whether phone number is verified via OTP';



COMMENT ON COLUMN "public"."profiles"."phone_verification_method" IS 'How phone was verified: otp, call, or manual';



COMMENT ON COLUMN "public"."profiles"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



COMMENT ON COLUMN "public"."profiles"."age" IS 'User age (13-120 years, required)';



COMMENT ON COLUMN "public"."profiles"."gender" IS 'User gender: male, female, or other (required)';



COMMENT ON COLUMN "public"."profiles"."token_valid_after" IS 'Timestamp that invalidates all tokens issued before it. Used for logout_all feature. NULL = no mass logout performed.';



COMMENT ON COLUMN "public"."profiles"."is_internal" IS 'Internal staff (developer/agency). Bypasses feature entitlement gates. Grants no role permissions on its own.';



CREATE OR REPLACE VIEW "public"."bookings_with_payments" AS
 SELECT "b"."id",
    "b"."booking_number",
    "b"."customer_id",
    "b"."salon_id",
    "b"."services",
    "b"."booking_date",
    "b"."time_slots",
    "b"."service_price",
    "b"."subtotal_service_price",
    "b"."discount_amount",
    "b"."convenience_fee",
    "b"."convenience_fee_discount",
    "b"."total_amount",
    "b"."coupon_id",
    "b"."coupon_code",
    "b"."status",
    "b"."created_at",
    "b"."updated_at",
    "b"."deleted_at",
    "p"."full_name" AS "customer_name",
    "p"."phone" AS "customer_phone",
    "p"."email" AS "customer_email",
    "cf"."id" AS "convenience_fee_payment_id",
    "cf"."amount" AS "convenience_fee_amount",
    "cf"."status" AS "convenience_fee_status",
    "cf"."paid_at" AS "convenience_fee_paid_at",
    "cf"."razorpay_payment_id" AS "convenience_fee_razorpay_payment_id",
    "sp"."id" AS "service_payment_id",
    "sp"."amount" AS "service_payment_amount",
    "sp"."status" AS "service_payment_status",
    "sp"."paid_at" AS "service_payment_paid_at",
    "sp"."payment_method" AS "service_payment_method",
    (("cf"."status")::"text" = 'success'::"text") AS "is_convenience_fee_paid",
    (("sp"."status")::"text" = 'success'::"text") AS "is_service_paid",
    ((("cf"."status")::"text" = 'success'::"text") AND (("sp"."status")::"text" = 'success'::"text")) AS "is_fully_paid"
   FROM ((("public"."bookings" "b"
     LEFT JOIN "public"."profiles" "p" ON (("p"."id" = "b"."customer_id")))
     LEFT JOIN "public"."payments" "cf" ON ((("cf"."booking_id" = "b"."id") AND (("cf"."payment_type")::"text" = 'convenience_fee'::"text") AND ("cf"."deleted_at" IS NULL))))
     LEFT JOIN "public"."payments" "sp" ON ((("sp"."booking_id" = "b"."id") AND (("sp"."payment_type")::"text" = 'service_payment'::"text") AND ("sp"."deleted_at" IS NULL))))
  WHERE ("b"."deleted_at" IS NULL);


ALTER VIEW "public"."bookings_with_payments" OWNER TO "postgres";


COMMENT ON VIEW "public"."bookings_with_payments" IS 'Bookings with payment summary, customer data and coupon discount breakdown. Customer information is fetched from profiles via JOIN.';



CREATE TABLE IF NOT EXISTS "public"."career_applications" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "full_name" "text" NOT NULL,
    "email" "text" NOT NULL,
    "phone" "text" NOT NULL,
    "current_address" "text",
    "position" "text" DEFAULT 'Relationship Manager'::"text" NOT NULL,
    "experience_years" integer DEFAULT 0,
    "highest_qualification" "text",
    "cover_letter" "text",
    "resume_url" "text" NOT NULL,
    "aadhaar_url" "text" NOT NULL,
    "photo_url" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "admin_notes" "text",
    "rejection_reason" "text",
    "interview_scheduled_at" timestamp with time zone,
    "interview_location" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "application_number" "text" NOT NULL,
    "age" integer,
    "permanent_address" "text",
    CONSTRAINT "career_applications_valid_age" CHECK ((("age" IS NULL) OR (("age" >= 18) AND ("age" <= 70)))),
    CONSTRAINT "valid_status" CHECK (("status" = ANY (ARRAY['pending'::"text", 'under_review'::"text", 'shortlisted'::"text", 'interview_scheduled'::"text", 'rejected'::"text", 'hired'::"text"])))
);


ALTER TABLE "public"."career_applications" OWNER TO "postgres";


COMMENT ON TABLE "public"."career_applications" IS 'Stores career job applications for RM and other positions';



COMMENT ON COLUMN "public"."career_applications"."application_number" IS 'Unique application number in format CA-YYYYMMDD-XXXXXXXX for applicant reference';



COMMENT ON COLUMN "public"."career_applications"."age" IS 'Applicant age (18-70 years, optional)';



COMMENT ON COLUMN "public"."career_applications"."permanent_address" IS 'Applicant permanent/home address';



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


COMMENT ON TABLE "public"."cart_items" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."coupon_redemptions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "coupon_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "booking_id" "uuid",
    "discount_amount" numeric(10,2) DEFAULT 0 NOT NULL,
    "redeemed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "gross_discount" numeric(10,2) DEFAULT 0 NOT NULL,
    "salon_id" "uuid",
    "coupon_code" "text",
    "funded_by" "text",
    "scope" "text"
);


ALTER TABLE "public"."coupon_redemptions" OWNER TO "postgres";


COMMENT ON TABLE "public"."coupon_redemptions" IS 'One row per coupon redemption, used to enforce total and per-user usage limits and for settlement reporting.';



COMMENT ON COLUMN "public"."coupon_redemptions"."gross_discount" IS 'Full coupon discount value at redemption (independent of any concurrent salon sale). discount_amount stays the net delta recorded against the booking.';



COMMENT ON COLUMN "public"."coupon_redemptions"."salon_id" IS 'Salon the redemption occurred at (snapshot from the booking).';



COMMENT ON COLUMN "public"."coupon_redemptions"."coupon_code" IS 'Coupon code at redemption time (snapshot; the coupons row may be edited or the code reissued).';



COMMENT ON COLUMN "public"."coupon_redemptions"."funded_by" IS 'Who funded the discount at redemption time: platform | vendor (snapshot).';



COMMENT ON COLUMN "public"."coupon_redemptions"."scope" IS 'Coupon scope at redemption time: platform | vendor (snapshot).';



CREATE TABLE IF NOT EXISTS "public"."coupons" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "code" "text" NOT NULL,
    "title" "text" NOT NULL,
    "scope" "text" NOT NULL,
    "salon_id" "uuid",
    "created_by" "uuid",
    "funded_by" "text" NOT NULL,
    "applies_to" "text" NOT NULL,
    "discount_type" "text" NOT NULL,
    "discount_value" numeric(10,2) NOT NULL,
    "max_discount_cap" numeric(10,2),
    "min_order_amount" numeric(10,2),
    "first_time_scope" "text",
    "usage_limit_total" integer,
    "usage_limit_per_user" integer DEFAULT 1,
    "used_count" integer DEFAULT 0 NOT NULL,
    "valid_from" timestamp with time zone DEFAULT "now"() NOT NULL,
    "valid_until" timestamp with time zone,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "coupons_applies_to_check" CHECK (("applies_to" = ANY (ARRAY['service'::"text", 'convenience_fee'::"text"]))),
    CONSTRAINT "coupons_discount_type_check" CHECK (("discount_type" = ANY (ARRAY['percentage'::"text", 'flat_amount'::"text"]))),
    CONSTRAINT "coupons_discount_value_check" CHECK (("discount_value" > (0)::numeric)),
    CONSTRAINT "coupons_first_time_scope_check" CHECK ((("first_time_scope" IS NULL) OR ("first_time_scope" = ANY (ARRAY['platform'::"text", 'vendor'::"text"])))),
    CONSTRAINT "coupons_funded_by_check" CHECK (("funded_by" = ANY (ARRAY['platform'::"text", 'vendor'::"text"]))),
    CONSTRAINT "coupons_max_discount_cap_check" CHECK ((("max_discount_cap" IS NULL) OR ("max_discount_cap" >= (0)::numeric))),
    CONSTRAINT "coupons_min_order_amount_check" CHECK ((("min_order_amount" IS NULL) OR ("min_order_amount" >= (0)::numeric))),
    CONSTRAINT "coupons_percentage_cap" CHECK ((("discount_type" <> 'percentage'::"text") OR (("discount_value" > (0)::numeric) AND ("discount_value" <= (100)::numeric)))),
    CONSTRAINT "coupons_scope_check" CHECK (("scope" = ANY (ARRAY['platform'::"text", 'vendor'::"text"]))),
    CONSTRAINT "coupons_scope_salon" CHECK (((("scope" = 'vendor'::"text") AND ("salon_id" IS NOT NULL)) OR (("scope" = 'platform'::"text") AND ("salon_id" IS NULL)))),
    CONSTRAINT "coupons_usage_limit_per_user_check" CHECK ((("usage_limit_per_user" IS NULL) OR ("usage_limit_per_user" >= 0))),
    CONSTRAINT "coupons_usage_limit_total_check" CHECK ((("usage_limit_total" IS NULL) OR ("usage_limit_total" >= 0))),
    CONSTRAINT "coupons_valid_window" CHECK ((("valid_until" IS NULL) OR ("valid_until" >= "valid_from")))
);


ALTER TABLE "public"."coupons" OWNER TO "postgres";


COMMENT ON TABLE "public"."coupons" IS 'Coupon definitions for vendor- and admin-issued discounts. Applied at checkout time via PricingService; never mutates the service catalog.';



CREATE TABLE IF NOT EXISTS "public"."salons" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "business_name" character varying(255) NOT NULL,
    "description" "text",
    "email" character varying(255) NOT NULL,
    "phone" character varying(20) NOT NULL,
    "vendor_id" "uuid",
    "address" "text" NOT NULL,
    "city" character varying(100) NOT NULL,
    "state" character varying(100) NOT NULL,
    "pincode" character varying(10) NOT NULL,
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
    "join_request_id" "uuid",
    "accepting_bookings" boolean DEFAULT true NOT NULL,
    "agreement_document_url" "text",
    "business_hours" "jsonb",
    "outlet" "public"."outlet_type",
    "is_gst" boolean DEFAULT false,
    "facilities" "jsonb" DEFAULT '{}'::"jsonb",
    "salon_type" "text" DEFAULT 'salon'::"text",
    CONSTRAINT "salons_salon_type_check" CHECK (("salon_type" = ANY (ARRAY['salon'::"text", 'regular_buyer'::"text"]))),
    CONSTRAINT "valid_coordinates" CHECK (((("latitude" IS NULL) AND ("longitude" IS NULL)) OR (("latitude" IS NOT NULL) AND ("longitude" IS NOT NULL) AND (("latitude" >= ('-90'::integer)::numeric) AND ("latitude" <= (90)::numeric)) AND (("longitude" >= ('-180'::integer)::numeric) AND ("longitude" <= (180)::numeric))))),
    CONSTRAINT "valid_gst_format" CHECK ((("gst_number" IS NULL) OR (("gst_number")::"text" ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'::"text"))),
    CONSTRAINT "valid_pincode_format" CHECK (((("pincode")::"text" ~ '^\d{6}$'::"text") OR (("pincode")::"text" ~ '^\d{10}$'::"text"))),
    CONSTRAINT "valid_rating" CHECK ((("average_rating" >= (0)::numeric) AND ("average_rating" <= (5)::numeric)))
);


ALTER TABLE "public"."salons" OWNER TO "postgres";


COMMENT ON TABLE "public"."salons" IS 'RLS disabled - backend uses service_role with FastAPI auth';



COMMENT ON COLUMN "public"."salons"."vendor_id" IS 'Vendor profile ID (NULL until vendor completes registration after approval)';



COMMENT ON COLUMN "public"."salons"."pincode" IS 'Postal code copied from the originating vendor_join_request. Accepts the same 6- or 10-digit forms as vendor_join_requests.pincode - keep the two in sync or salon creation at approval time will fail.';



COMMENT ON COLUMN "public"."salons"."location" IS 'PostGIS geography point for nearby salon queries (auto-populated from lat/lng)';



COMMENT ON COLUMN "public"."salons"."gst_number" IS 'Indian GST number (15 chars: 2-digit state code + 10-char PAN + entity + checksum)';



COMMENT ON COLUMN "public"."salons"."registration_fee_paid" IS 'Whether vendor paid one-time platform registration fee';



COMMENT ON COLUMN "public"."salons"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



COMMENT ON COLUMN "public"."salons"."join_request_id" IS 'Original vendor join request that led to this salon creation (required for payment processing)';



COMMENT ON COLUMN "public"."salons"."accepting_bookings" IS 'Whether salon is currently accepting new bookings (vendor can toggle)';



COMMENT ON COLUMN "public"."salons"."agreement_document_url" IS 'URL of the salon agreement document (PDF or image) submitted during registration';



COMMENT ON COLUMN "public"."salons"."business_hours" IS 'Day-wise business hours in JSONB format {monday: "9:00 AM - 6:00 PM", tuesday: "Closed", ...}';



COMMENT ON COLUMN "public"."salons"."outlet" IS 'Type of outlet: franchisee or Company owned';



COMMENT ON COLUMN "public"."salons"."is_gst" IS 'Whether the salon has GST registration';



COMMENT ON COLUMN "public"."salons"."salon_type" IS 'Distinguishes between service-providing salons and product-only regular buyers';



CREATE OR REPLACE VIEW "public"."coupon_redemption_report" AS
 SELECT "cr"."id" AS "redemption_id",
    "cr"."coupon_id",
    "cr"."coupon_code",
    "cr"."scope",
    "cr"."funded_by",
    "cr"."salon_id",
    "cr"."user_id",
    "cr"."booking_id",
    "cr"."discount_amount",
    "cr"."gross_discount",
    "cr"."redeemed_at",
    "c"."title" AS "coupon_title",
    "c"."applies_to",
    "c"."discount_type",
    "c"."discount_value",
    "s"."business_name" AS "salon_name"
   FROM (("public"."coupon_redemptions" "cr"
     LEFT JOIN "public"."coupons" "c" ON (("c"."id" = "cr"."coupon_id")))
     LEFT JOIN "public"."salons" "s" ON (("s"."id" = "cr"."salon_id")));


ALTER VIEW "public"."coupon_redemption_report" OWNER TO "postgres";


COMMENT ON VIEW "public"."coupon_redemption_report" IS 'Flat, settlement-ready view of coupon redemptions using the redemption-time snapshot (code/scope/funded_by/salon) rather than the mutable coupons row.';



CREATE TABLE IF NOT EXISTS "public"."email_logs" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "recipient_email" "text" NOT NULL,
    "email_type" "text" NOT NULL,
    "subject" "text" NOT NULL,
    "status" "text" NOT NULL,
    "error_message" "text",
    "related_entity_type" "text",
    "related_entity_id" "uuid",
    "email_data" "jsonb",
    "retry_count" integer DEFAULT 0,
    "max_retries" integer DEFAULT 3,
    "next_retry_at" timestamp with time zone,
    "sent_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "email_logs_status_check" CHECK (("status" = ANY (ARRAY['sent'::"text", 'failed'::"text", 'pending'::"text"])))
);


ALTER TABLE "public"."email_logs" OWNER TO "postgres";


COMMENT ON TABLE "public"."email_logs" IS 'Tracks all emails sent by the system for audit trail and retry mechanism';



COMMENT ON COLUMN "public"."email_logs"."email_type" IS 'Type of email: vendor_approval, vendor_rejection, booking_confirmation, booking_cancellation, payment_receipt, welcome_vendor, career_application, rm_notification';



COMMENT ON COLUMN "public"."email_logs"."status" IS 'Current status: sent (successfully sent), failed (delivery failed), pending (queued for sending)';



COMMENT ON COLUMN "public"."email_logs"."email_data" IS 'JSON blob containing template variables for email recreation/resending';



COMMENT ON COLUMN "public"."email_logs"."retry_count" IS 'Number of retry attempts made';



COMMENT ON COLUMN "public"."email_logs"."next_retry_at" IS 'Timestamp for next retry attempt (for failed emails)';



CREATE TABLE IF NOT EXISTS "public"."favorites" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."favorites" OWNER TO "postgres";


COMMENT ON TABLE "public"."favorites" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."feature_flags" (
    "key" character varying(64) NOT NULL,
    "name" character varying(120) NOT NULL,
    "description" "text",
    "status" "public"."feature_status" DEFAULT 'internal'::"public"."feature_status" NOT NULL,
    "enabled_at" timestamp with time zone,
    "enabled_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."feature_flags" OWNER TO "postgres";


COMMENT ON TABLE "public"."feature_flags" IS 'Sellable-feature registry. One row per gateable feature; new features default to internal.';



CREATE TABLE IF NOT EXISTS "public"."otp_attempts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "phone" character varying(20) NOT NULL,
    "country_code" character varying(5) DEFAULT '91'::character varying,
    "verification_id" character varying(255),
    "send_attempts" integer DEFAULT 0,
    "verify_attempts" integer DEFAULT 0,
    "last_send_at" timestamp with time zone,
    "last_verify_at" timestamp with time zone,
    "blocked_until" timestamp with time zone,
    "blocked_reason" character varying(100),
    "last_success_at" timestamp with time zone,
    "ip_address" character varying(45),
    "user_agent" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."otp_attempts" OWNER TO "postgres";


COMMENT ON TABLE "public"."otp_attempts" IS 'Tracks OTP send and verification attempts for rate limiting and security. Auto-cleanup records older than 7 days.';



COMMENT ON COLUMN "public"."otp_attempts"."phone" IS 'Phone number in E.164 format (e.g., +919876543210)';



COMMENT ON COLUMN "public"."otp_attempts"."send_attempts" IS 'Number of OTP send attempts (reset after successful verification or timeout)';



COMMENT ON COLUMN "public"."otp_attempts"."verify_attempts" IS 'Number of OTP verification attempts (max 5 before blocking)';



COMMENT ON COLUMN "public"."otp_attempts"."blocked_until" IS 'Timestamp until phone is blocked from OTP requests. NULL = not blocked.';



CREATE TABLE IF NOT EXISTS "public"."partner_requests" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "owner_name" "text" NOT NULL,
    "shop_name" "text" NOT NULL,
    "shop_type" "text" NOT NULL,
    "email" "text" NOT NULL,
    "phone" "text" NOT NULL,
    "location" "text" NOT NULL,
    "status" "text" DEFAULT 'new'::"text" NOT NULL,
    "admin_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "partner_requests_valid_status" CHECK (("status" = ANY (ARRAY['new'::"text", 'contacted'::"text", 'approved'::"text", 'rejected'::"text"])))
);


ALTER TABLE "public"."partner_requests" OWNER TO "postgres";


COMMENT ON TABLE "public"."partner_requests" IS 'Stores "Partner with us" onboarding inquiries from prospective vendors';



CREATE OR REPLACE VIEW "public"."pending_payments" AS
 SELECT "p"."id",
    "p"."booking_id",
    "b"."booking_number",
    "b"."booking_date",
    "b"."time_slots",
    "p"."payment_type",
    "p"."amount",
    "p"."customer_id",
    "prof"."full_name" AS "customer_name",
    "b"."salon_id",
    "s"."business_name" AS "salon_name",
    "p"."created_at",
    (EXTRACT(epoch FROM ("now"() - "p"."created_at")) / (3600)::numeric) AS "hours_pending"
   FROM ((("public"."payments" "p"
     JOIN "public"."bookings" "b" ON (("b"."id" = "p"."booking_id")))
     JOIN "public"."profiles" "prof" ON (("prof"."id" = "p"."customer_id")))
     JOIN "public"."salons" "s" ON (("s"."id" = "b"."salon_id")))
  WHERE ((("p"."status")::"text" = 'pending'::"text") AND ("p"."deleted_at" IS NULL) AND ("b"."deleted_at" IS NULL))
  ORDER BY "p"."created_at" DESC;


ALTER VIEW "public"."pending_payments" OWNER TO "postgres";


COMMENT ON VIEW "public"."pending_payments" IS 'Pending payments view. Uses time_slots array instead of deprecated booking_time field.';



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
    CONSTRAINT "phone_verification_codes_purpose_check" CHECK ((("purpose")::"text" = ANY (ARRAY[('signup'::character varying)::"text", ('login'::character varying)::"text", ('phone_verification'::character varying)::"text", ('password_reset'::character varying)::"text"])))
);


ALTER TABLE "public"."phone_verification_codes" OWNER TO "postgres";


COMMENT ON TABLE "public"."phone_verification_codes" IS 'OTP codes for phone verification. Rate-limited to prevent abuse (max 5/hour).';



CREATE OR REPLACE VIEW "public"."platform_revenue" AS
 SELECT "date"("paid_at") AS "date",
    "count"(*) AS "transaction_count",
    "sum"("amount") AS "total_revenue",
    "avg"("amount") AS "avg_transaction",
    "currency"
   FROM "public"."payments"
  WHERE ((("payment_type")::"text" = 'convenience_fee'::"text") AND (("status")::"text" = 'success'::"text") AND ("deleted_at" IS NULL))
  GROUP BY ("date"("paid_at")), "currency"
  ORDER BY ("date"("paid_at")) DESC;


ALTER VIEW "public"."platform_revenue" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."product_cart_items" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "quantity" integer DEFAULT 1 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    CONSTRAINT "product_cart_items_quantity_check" CHECK (("quantity" > 0))
);


ALTER TABLE "public"."product_cart_items" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."product_favorites" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."product_favorites" OWNER TO "postgres";


COMMENT ON TABLE "public"."product_favorites" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."product_order_items" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "order_id" "uuid" NOT NULL,
    "product_id" "uuid" NOT NULL,
    "product_name" "text" NOT NULL,
    "quantity" integer DEFAULT 1 NOT NULL,
    "unit_price" numeric(10,2) NOT NULL,
    "total_price" numeric(10,2) NOT NULL,
    "image_url" "text"
);


ALTER TABLE "public"."product_order_items" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."product_orders" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "order_number" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "subtotal" numeric(10,2) NOT NULL,
    "discount_total" numeric(10,2) DEFAULT 0,
    "total_amount" numeric(10,2) NOT NULL,
    "shipping_address" "jsonb",
    "razorpay_order_id" "text",
    "razorpay_payment_id" "text",
    "payment_status" "text" DEFAULT 'pending'::"text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "user_type" "text" DEFAULT 'customer'::"text"
);


ALTER TABLE "public"."product_orders" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."products" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "slug" "text" NOT NULL,
    "description" "text",
    "short_description" "text",
    "price" numeric(10,2) NOT NULL,
    "discount_price" numeric(10,2),
    "discount_percentage" numeric(5,2),
    "sku" "text",
    "category" "text" DEFAULT 'general'::"text" NOT NULL,
    "brand" "text",
    "image_urls" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "stock_quantity" integer DEFAULT 0 NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "is_featured" boolean DEFAULT false NOT NULL,
    "tags" "text"[] DEFAULT '{}'::"text"[],
    "weight" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "b2b_discount_price" numeric(10,2),
    "b2b_discount_percentage" numeric(5,2),
    CONSTRAINT "products_b2b_discount_percentage_check" CHECK ((("b2b_discount_percentage" IS NULL) OR (("b2b_discount_percentage" >= (0)::numeric) AND ("b2b_discount_percentage" <= (100)::numeric)))),
    CONSTRAINT "products_b2b_discount_price_check" CHECK ((("b2b_discount_price" IS NULL) OR ("b2b_discount_price" >= (0)::numeric))),
    CONSTRAINT "products_discount_percentage_check" CHECK ((("discount_percentage" IS NULL) OR (("discount_percentage" >= (0)::numeric) AND ("discount_percentage" <= (100)::numeric)))),
    CONSTRAINT "products_discount_price_check" CHECK ((("discount_price" IS NULL) OR ("discount_price" >= (0)::numeric))),
    CONSTRAINT "products_price_check" CHECK (("price" >= (0)::numeric)),
    CONSTRAINT "products_stock_quantity_check" CHECK (("stock_quantity" >= 0))
);


ALTER TABLE "public"."products" OWNER TO "postgres";


COMMENT ON COLUMN "public"."products"."b2b_discount_price" IS 'Wholesale discounted price for Vendors and Regular Buyers';



COMMENT ON COLUMN "public"."products"."b2b_discount_percentage" IS 'Calculated discount percentage for B2B pricing';



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


COMMENT ON TABLE "public"."reviews" IS 'RLS disabled - backend uses service_role with FastAPI auth';



COMMENT ON COLUMN "public"."reviews"."rating" IS 'Star rating (1-5)';



COMMENT ON COLUMN "public"."reviews"."is_verified" IS 'true = customer actually completed the booking';



COMMENT ON COLUMN "public"."reviews"."is_featured" IS 'true = featured on homepage/salon page';



COMMENT ON COLUMN "public"."reviews"."is_hidden" IS 'true = hidden by admin (spam/inappropriate content)';



COMMENT ON COLUMN "public"."reviews"."helpful_count" IS 'Number of users who found this review helpful';



COMMENT ON COLUMN "public"."reviews"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



CREATE TABLE IF NOT EXISTS "public"."rm_profiles" (
    "id" "uuid" NOT NULL,
    "assigned_territories" "text"[],
    "performance_score" integer DEFAULT 0,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "employee_id" character varying,
    "total_salons_added" integer DEFAULT 0,
    "total_approved_salons" integer DEFAULT 0,
    "joining_date" "date" DEFAULT CURRENT_DATE,
    "manager_notes" "text",
    "total_requests_count" integer DEFAULT 0,
    "pending_requests_count" integer DEFAULT 0,
    "approved_requests_count" integer DEFAULT 0,
    "rejected_requests_count" integer DEFAULT 0,
    CONSTRAINT "check_approved_requests_count_non_negative" CHECK (("approved_requests_count" >= 0)),
    CONSTRAINT "check_pending_requests_count_non_negative" CHECK (("pending_requests_count" >= 0)),
    CONSTRAINT "check_rejected_requests_count_non_negative" CHECK (("rejected_requests_count" >= 0)),
    CONSTRAINT "check_total_requests_count_non_negative" CHECK (("total_requests_count" >= 0))
);


ALTER TABLE "public"."rm_profiles" OWNER TO "postgres";


COMMENT ON TABLE "public"."rm_profiles" IS 'Relationship Manager specific data. User data (name, email, phone) stored in profiles table.';



COMMENT ON COLUMN "public"."rm_profiles"."total_salons_added" IS 'Cached count of ALL vendor requests submitted by the RM (denominator for approval rate)';



COMMENT ON COLUMN "public"."rm_profiles"."total_approved_salons" IS 'Cached count of approved vendor requests (numerator for approval rate)';



COMMENT ON COLUMN "public"."rm_profiles"."total_requests_count" IS 'Cached count of all vendor requests (auto-updated by trigger)';



COMMENT ON COLUMN "public"."rm_profiles"."pending_requests_count" IS 'Cached count of pending requests (auto-updated by trigger)';



COMMENT ON COLUMN "public"."rm_profiles"."approved_requests_count" IS 'Cached count of approved requests (auto-updated by trigger)';



COMMENT ON COLUMN "public"."rm_profiles"."rejected_requests_count" IS 'Cached count of rejected requests (auto-updated by trigger)';



CREATE OR REPLACE VIEW "public"."rm_profiles_with_user_data" AS
 SELECT "rm"."id",
    "rm"."employee_id",
    "rm"."assigned_territories",
    "rm"."performance_score",
    "rm"."total_salons_added",
    "rm"."total_approved_salons",
    "rm"."joining_date",
    "rm"."manager_notes",
    "rm"."created_at",
    "rm"."updated_at",
    "p"."full_name",
    "p"."email",
    "p"."phone",
    "p"."is_active",
    "p"."user_role",
    "p"."avatar_url",
    "p"."phone_verified"
   FROM ("public"."rm_profiles" "rm"
     JOIN "public"."profiles" "p" ON (("rm"."id" = "p"."id")));


ALTER VIEW "public"."rm_profiles_with_user_data" OWNER TO "postgres";


COMMENT ON VIEW "public"."rm_profiles_with_user_data" IS 'Convenience view combining RM-specific data with user profile data';



CREATE TABLE IF NOT EXISTS "public"."rm_score_history" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "rm_id" "uuid" NOT NULL,
    "action" character varying(100) NOT NULL,
    "points" integer NOT NULL,
    "description" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."rm_score_history" OWNER TO "postgres";


COMMENT ON TABLE "public"."rm_score_history" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."salon_discount_promotions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "salon_id" "uuid" NOT NULL,
    "title" character varying(255) NOT NULL,
    "discount_type" character varying(20) NOT NULL,
    "discount_value" numeric(10,2) NOT NULL,
    "min_booking_amount" numeric(10,2),
    "max_discount_limit" numeric(10,2),
    "start_date" "date" NOT NULL,
    "end_date" "date",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    CONSTRAINT "salon_discount_promotions_discount_type_check" CHECK ((("discount_type")::"text" = ANY ((ARRAY['percentage'::character varying, 'flat_amount'::character varying])::"text"[]))),
    CONSTRAINT "salon_discount_promotions_discount_value_check" CHECK (("discount_value" > (0)::numeric)),
    CONSTRAINT "salon_discount_promotions_max_discount_limit_check" CHECK ((("max_discount_limit" IS NULL) OR ("max_discount_limit" >= (0)::numeric))),
    CONSTRAINT "salon_discount_promotions_min_booking_amount_check" CHECK ((("min_booking_amount" IS NULL) OR ("min_booking_amount" >= (0)::numeric))),
    CONSTRAINT "salon_promo_percentage_cap" CHECK (((("discount_type")::"text" <> 'percentage'::"text") OR (("discount_value" > (0)::numeric) AND ("discount_value" <= (100)::numeric)))),
    CONSTRAINT "salon_promo_valid_date_range" CHECK ((("end_date" IS NULL) OR ("end_date" >= "start_date")))
);


ALTER TABLE "public"."salon_discount_promotions" OWNER TO "postgres";


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
    CONSTRAINT "salon_subscriptions_status_check" CHECK ((("status")::"text" = ANY (ARRAY[('active'::character varying)::"text", ('expired'::character varying)::"text", ('cancelled'::character varying)::"text", ('suspended'::character varying)::"text"])))
);


ALTER TABLE "public"."salon_subscriptions" OWNER TO "postgres";


COMMENT ON TABLE "public"."salon_subscriptions" IS 'RLS disabled - backend uses service_role with FastAPI auth';



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


COMMENT ON TABLE "public"."service_categories" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."service_subcategories" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "parent_category_id" "uuid" NOT NULL,
    "name" character varying(255) NOT NULL,
    "description" "text",
    "icon_url" "text",
    "display_order" integer DEFAULT 0,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "parent_subcategory_id" "uuid",
    CONSTRAINT "service_subcategories_no_self_parent" CHECK ((("parent_subcategory_id" IS NULL) OR ("parent_subcategory_id" <> "id")))
);


ALTER TABLE "public"."service_subcategories" OWNER TO "postgres";


COMMENT ON COLUMN "public"."service_subcategories"."parent_subcategory_id" IS 'Optional parent subcategory. NULL = level-2 (under parent_category_id); set = level-3 sub-subcategory.';



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
    "discount_percentage" numeric(5,2),
    "gender_category" character varying(10) DEFAULT 'both'::character varying,
    "subcategory_id" "uuid",
    CONSTRAINT "services_discount_fields_consistency_check" CHECK (((("discount_percentage" IS NULL) AND ("discounted_price" IS NULL)) OR (("discount_percentage" IS NOT NULL) AND ("discounted_price" IS NOT NULL)))),
    CONSTRAINT "services_discount_percentage_check" CHECK ((("discount_percentage" IS NULL) OR (("discount_percentage" >= (0)::numeric) AND ("discount_percentage" <= (100)::numeric)))),
    CONSTRAINT "services_discounted_price_check" CHECK ((("discounted_price" IS NULL) OR ("discounted_price" >= (0)::numeric))),
    CONSTRAINT "services_duration_minutes_check" CHECK (("duration_minutes" > 0)),
    CONSTRAINT "services_gender_category_check" CHECK ((("gender_category")::"text" = ANY ((ARRAY['male'::character varying, 'female'::character varying, 'both'::character varying])::"text"[]))),
    CONSTRAINT "services_price_check" CHECK (("price" >= (0)::numeric)),
    CONSTRAINT "valid_discount" CHECK ((("discounted_price" IS NULL) OR ("discounted_price" < "price")))
);


ALTER TABLE "public"."services" OWNER TO "postgres";


COMMENT ON TABLE "public"."services" IS 'RLS disabled - backend uses service_role with FastAPI auth';



COMMENT ON COLUMN "public"."services"."price" IS 'Regular price (paid at salon)';



COMMENT ON COLUMN "public"."services"."discounted_price" IS 'Discounted price (if any). Must be less than regular price';



COMMENT ON COLUMN "public"."services"."duration_minutes" IS 'Estimated service duration in minutes';



COMMENT ON COLUMN "public"."services"."deleted_at" IS 'Soft delete timestamp (NULL = active)';



COMMENT ON COLUMN "public"."services"."discount_percentage" IS 'Optional percentage discount for this service. Range: 0 to 100.';



COMMENT ON COLUMN "public"."services"."gender_category" IS 'Designates the target gender for the service: male, female, or both (unisex).';



CREATE TABLE IF NOT EXISTS "public"."system_config" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "config_key" character varying(255) NOT NULL,
    "config_value" "text" NOT NULL,
    "config_type" character varying(50) NOT NULL,
    "description" "text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_by" "uuid"
);


ALTER TABLE "public"."system_config" OWNER TO "postgres";


COMMENT ON TABLE "public"."system_config" IS 'System-wide configuration for fees, limits, and scoring (managed by admins)';



COMMENT ON COLUMN "public"."system_config"."config_key" IS 'Unique configuration key (e.g., rm_score_per_approval)';



COMMENT ON COLUMN "public"."system_config"."config_value" IS 'Configuration value stored as text (parse based on config_type). Sensitive values are encrypted by backend.';



COMMENT ON COLUMN "public"."system_config"."config_type" IS 'Data type: string, number, boolean, json';



COMMENT ON COLUMN "public"."system_config"."is_active" IS 'Whether this config is currently active';



CREATE TABLE IF NOT EXISTS "public"."token_blacklist" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "token_jti" character varying(255) NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."token_blacklist" OWNER TO "postgres";


COMMENT ON TABLE "public"."token_blacklist" IS 'RLS disabled - backend uses service_role with FastAPI auth';



CREATE TABLE IF NOT EXISTS "public"."vendor_join_requests" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "rm_id" "uuid" NOT NULL,
    "business_name" character varying(255) NOT NULL,
    "business_type" character varying(50) NOT NULL,
    "owner_name" character varying(255) NOT NULL,
    "owner_email" character varying(255) NOT NULL,
    "owner_phone" character varying(20) NOT NULL,
    "business_address" "text" NOT NULL,
    "city" character varying(100) NOT NULL,
    "state" character varying(100) NOT NULL,
    "pincode" character varying(10) NOT NULL,
    "latitude" numeric(10,8),
    "longitude" numeric(11,8),
    "gst_number" character varying(50),
    "pan_number" character varying(10),
    "business_license" "text",
    "registration_certificate" "text",
    "documents" "jsonb",
    "cover_image_url" "text",
    "gallery_images" "text"[],
    "services_offered" "jsonb",
    "opening_time" time without time zone,
    "closing_time" time without time zone,
    "working_days" "text"[],
    "status" "public"."request_status" DEFAULT 'pending'::"public"."request_status" NOT NULL,
    "submitted_at" timestamp with time zone,
    "admin_notes" "text",
    "approval_notes" "text",
    "rejection_reason" "text",
    "reviewed_by" "uuid",
    "reviewed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "outlet" "public"."outlet_type",
    "is_gst" boolean DEFAULT false,
    "facilities" "jsonb" DEFAULT '{}'::"jsonb",
    "request_type" "text" DEFAULT 'salon'::"text",
    CONSTRAINT "valid_coordinates" CHECK (((("latitude" IS NULL) AND ("longitude" IS NULL)) OR (("latitude" IS NOT NULL) AND ("longitude" IS NOT NULL)))),
    CONSTRAINT "valid_gst" CHECK ((("gst_number" IS NULL) OR (("gst_number")::"text" ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'::"text"))),
    CONSTRAINT "valid_pan" CHECK ((("pan_number" IS NULL) OR (("pan_number")::"text" ~ '^[A-Z]{5}[0-9]{4}[A-Z]{1}$'::"text"))),
    CONSTRAINT "valid_pincode" CHECK (((("pincode")::"text" ~ '^\d{6}$'::"text") OR (("pincode")::"text" ~ '^\d{10}$'::"text"))),
    CONSTRAINT "valid_status" CHECK (("status" = ANY (ARRAY['draft'::"public"."request_status", 'pending'::"public"."request_status", 'approved'::"public"."request_status", 'rejected'::"public"."request_status"]))),
    CONSTRAINT "vendor_join_requests_request_type_check" CHECK (("request_type" = ANY (ARRAY['salon'::"text", 'regular_buyer'::"text"])))
);


ALTER TABLE "public"."vendor_join_requests" OWNER TO "postgres";


COMMENT ON TABLE "public"."vendor_join_requests" IS 'RLS disabled - backend uses service_role with FastAPI auth. Staff management removed as of 2026-01-11.';



COMMENT ON COLUMN "public"."vendor_join_requests"."rm_id" IS 'Relationship Manager who submitted this request';



COMMENT ON COLUMN "public"."vendor_join_requests"."documents" IS 'Additional documents as JSONB: {doc_type: storage_url, ...}';



COMMENT ON COLUMN "public"."vendor_join_requests"."services_offered" IS 'Services as JSONB: {category_id: [service_names], ...}';



COMMENT ON COLUMN "public"."vendor_join_requests"."submitted_at" IS 'When request was submitted (NULL for drafts)';



COMMENT ON COLUMN "public"."vendor_join_requests"."outlet" IS 'Type of outlet: franchisee or Company owned';



COMMENT ON COLUMN "public"."vendor_join_requests"."is_gst" IS 'Whether the business has GST registration';



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
    "salon_id" "uuid",
    "vendor_request_id" "uuid",
    CONSTRAINT "valid_vendor_payment_status" CHECK (((("status" = 'pending'::"public"."payment_status") AND ("payment_completed_at" IS NULL) AND ("payment_failed_at" IS NULL)) OR (("status" = 'success'::"public"."payment_status") AND ("payment_completed_at" IS NOT NULL)) OR (("status" = 'failed'::"public"."payment_status") AND ("payment_failed_at" IS NOT NULL)))),
    CONSTRAINT "vendor_registration_payments_amount_check" CHECK (("amount" >= (0)::numeric))
);


ALTER TABLE "public"."vendor_registration_payments" OWNER TO "postgres";


COMMENT ON TABLE "public"."vendor_registration_payments" IS 'One-time registration fee payments for vendor salon accounts. Separate from bookings-based payments table for cleaner architecture and audit trail.';



COMMENT ON COLUMN "public"."vendor_registration_payments"."salon_id" IS 'Salon ID (linked after payment verification and salon activation)';



COMMENT ON COLUMN "public"."vendor_registration_payments"."vendor_request_id" IS 'Original vendor join request that led to this payment';



CREATE OR REPLACE VIEW "public"."vendor_revenue" AS
 SELECT "b"."salon_id",
    "s"."business_name" AS "salon_name",
    "date"("p"."paid_at") AS "date",
    "count"(*) AS "transaction_count",
    "sum"("p"."amount") AS "total_revenue",
    "avg"("p"."amount") AS "avg_transaction",
    "p"."currency"
   FROM (("public"."payments" "p"
     JOIN "public"."bookings" "b" ON (("b"."id" = "p"."booking_id")))
     JOIN "public"."salons" "s" ON (("s"."id" = "b"."salon_id")))
  WHERE ((("p"."payment_type")::"text" = 'service_payment'::"text") AND (("p"."status")::"text" = 'success'::"text") AND ("p"."deleted_at" IS NULL) AND ("b"."deleted_at" IS NULL))
  GROUP BY "b"."salon_id", "s"."business_name", ("date"("p"."paid_at")), "p"."currency"
  ORDER BY ("date"("p"."paid_at")) DESC, "s"."business_name";


ALTER VIEW "public"."vendor_revenue" OWNER TO "postgres";


ALTER TABLE ONLY "public"."activity_logs"
    ADD CONSTRAINT "activity_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."banners"
    ADD CONSTRAINT "banners_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."blog_posts"
    ADD CONSTRAINT "blog_posts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."blog_posts"
    ADD CONSTRAINT "blog_posts_slug_key" UNIQUE ("slug");



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



ALTER TABLE ONLY "public"."career_applications"
    ADD CONSTRAINT "career_applications_application_number_key" UNIQUE ("application_number");



ALTER TABLE ONLY "public"."career_applications"
    ADD CONSTRAINT "career_applications_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_user_id_service_id_key" UNIQUE ("user_id", "service_id");



ALTER TABLE ONLY "public"."coupon_redemptions"
    ADD CONSTRAINT "coupon_redemptions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."coupon_redemptions"
    ADD CONSTRAINT "coupon_redemptions_unique_booking" UNIQUE ("coupon_id", "booking_id");



ALTER TABLE ONLY "public"."coupons"
    ADD CONSTRAINT "coupons_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."email_logs"
    ADD CONSTRAINT "email_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_user_id_salon_id_key" UNIQUE ("user_id", "salon_id");



ALTER TABLE ONLY "public"."feature_flags"
    ADD CONSTRAINT "feature_flags_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "one_review_per_booking" UNIQUE ("booking_id");



COMMENT ON CONSTRAINT "one_review_per_booking" ON "public"."reviews" IS 'One review per booking (prevents spam)';



ALTER TABLE ONLY "public"."otp_attempts"
    ADD CONSTRAINT "otp_attempts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."partner_requests"
    ADD CONSTRAINT "partner_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."phone_verification_codes"
    ADD CONSTRAINT "phone_verification_codes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."product_cart_items"
    ADD CONSTRAINT "product_cart_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."product_cart_items"
    ADD CONSTRAINT "product_cart_items_user_id_product_id_key" UNIQUE ("user_id", "product_id");



ALTER TABLE ONLY "public"."product_favorites"
    ADD CONSTRAINT "product_favorites_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."product_favorites"
    ADD CONSTRAINT "product_favorites_user_id_product_id_key" UNIQUE ("user_id", "product_id");



ALTER TABLE ONLY "public"."product_order_items"
    ADD CONSTRAINT "product_order_items_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."product_orders"
    ADD CONSTRAINT "product_orders_order_number_key" UNIQUE ("order_number");



ALTER TABLE ONLY "public"."product_orders"
    ADD CONSTRAINT "product_orders_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."products"
    ADD CONSTRAINT "products_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."products"
    ADD CONSTRAINT "products_sku_key" UNIQUE ("sku");



ALTER TABLE ONLY "public"."products"
    ADD CONSTRAINT "products_slug_key" UNIQUE ("slug");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_email_key" UNIQUE ("email");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."reviews"
    ADD CONSTRAINT "reviews_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rm_profiles"
    ADD CONSTRAINT "rm_profiles_employee_id_key" UNIQUE ("employee_id");



ALTER TABLE ONLY "public"."rm_profiles"
    ADD CONSTRAINT "rm_profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rm_score_history"
    ADD CONSTRAINT "rm_score_history_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."salon_discount_promotions"
    ADD CONSTRAINT "salon_discount_promotions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."salon_subscriptions"
    ADD CONSTRAINT "salon_subscriptions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."service_categories"
    ADD CONSTRAINT "service_categories_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."service_categories"
    ADD CONSTRAINT "service_categories_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."service_subcategories"
    ADD CONSTRAINT "service_subcategories_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."system_config"
    ADD CONSTRAINT "system_config_config_key_key" UNIQUE ("config_key");



ALTER TABLE ONLY "public"."system_config"
    ADD CONSTRAINT "system_config_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."token_blacklist"
    ADD CONSTRAINT "token_blacklist_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."token_blacklist"
    ADD CONSTRAINT "token_blacklist_token_jti_key" UNIQUE ("token_jti");



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "unique_booking_payment_type" UNIQUE ("booking_id", "payment_type");



COMMENT ON CONSTRAINT "unique_booking_payment_type" ON "public"."payments" IS 'Ensures each booking has only one payment record per payment_type (e.g., one convenience_fee, one service_payment). Prevents duplicate payment records.';



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "unique_razorpay_payment" UNIQUE ("razorpay_payment_id");



COMMENT ON CONSTRAINT "unique_razorpay_payment" ON "public"."bookings" IS 'Enforces idempotency: prevents duplicate bookings from the same Razorpay payment. Protects against network retries and double-clicks.';



ALTER TABLE ONLY "public"."vendor_join_requests"
    ADD CONSTRAINT "vendor_join_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_razorpay_order_id_key" UNIQUE ("razorpay_order_id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_razorpay_payment_id_key" UNIQUE ("razorpay_payment_id");



CREATE INDEX "idx_activity_logs_action" ON "public"."activity_logs" USING "btree" ("action");



CREATE INDEX "idx_activity_logs_created_at" ON "public"."activity_logs" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_activity_logs_entity" ON "public"."activity_logs" USING "btree" ("entity_type", "entity_id");



CREATE INDEX "idx_activity_logs_user_id" ON "public"."activity_logs" USING "btree" ("user_id");



CREATE INDEX "idx_audit_logs_action" ON "public"."audit_logs" USING "btree" ("action");



CREATE INDEX "idx_audit_logs_created_at" ON "public"."audit_logs" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_audit_logs_table_record" ON "public"."audit_logs" USING "btree" ("table_name", "record_id");



CREATE INDEX "idx_audit_logs_user_id" ON "public"."audit_logs" USING "btree" ("user_id");



CREATE INDEX "idx_banners_created_at" ON "public"."banners" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_banners_is_active" ON "public"."banners" USING "btree" ("is_active");



CREATE INDEX "idx_banners_sort_order" ON "public"."banners" USING "btree" ("sort_order");



CREATE INDEX "idx_blog_posts_created_at" ON "public"."blog_posts" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_blog_posts_slug" ON "public"."blog_posts" USING "btree" ("slug");



CREATE INDEX "idx_blog_posts_status_published_at" ON "public"."blog_posts" USING "btree" ("status", "published_at" DESC);



CREATE INDEX "idx_blog_posts_tags" ON "public"."blog_posts" USING "gin" ("tags");



CREATE INDEX "idx_booking_payments_booking_id" ON "public"."booking_payments" USING "btree" ("booking_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_booking_payments_customer_id" ON "public"."booking_payments" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_booking_payments_deleted_at" ON "public"."booking_payments" USING "btree" ("deleted_at");



CREATE INDEX "idx_booking_payments_payment_type" ON "public"."booking_payments" USING "btree" ("payment_type") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_booking_payments_razorpay_order" ON "public"."booking_payments" USING "btree" ("razorpay_order_id");



CREATE INDEX "idx_booking_payments_razorpay_payment" ON "public"."booking_payments" USING "btree" ("razorpay_payment_id");



CREATE INDEX "idx_booking_payments_refund" ON "public"."booking_payments" USING "btree" ("refund_initiated", "refund_completed") WHERE ("refund_initiated" = true);



CREATE INDEX "idx_booking_payments_status" ON "public"."booking_payments" USING "btree" ("status") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_booking_number" ON "public"."bookings" USING "btree" ("booking_number");



CREATE INDEX "idx_bookings_coupon_id" ON "public"."bookings" USING "btree" ("coupon_id") WHERE ("coupon_id" IS NOT NULL);



CREATE INDEX "idx_bookings_customer_date" ON "public"."bookings" USING "btree" ("customer_id", "booking_date" DESC);



CREATE INDEX "idx_bookings_customer_id" ON "public"."bookings" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_date" ON "public"."bookings" USING "btree" ("booking_date") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_deleted_at" ON "public"."bookings" USING "btree" ("deleted_at");



CREATE INDEX "idx_bookings_number" ON "public"."bookings" USING "btree" ("booking_number");



CREATE INDEX "idx_bookings_razorpay_payment_id" ON "public"."bookings" USING "btree" ("razorpay_payment_id") WHERE ("razorpay_payment_id" IS NOT NULL);



CREATE INDEX "idx_bookings_salon_date" ON "public"."bookings" USING "btree" ("salon_id", "booking_date" DESC);



CREATE INDEX "idx_bookings_salon_id" ON "public"."bookings" USING "btree" ("salon_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_status" ON "public"."bookings" USING "btree" ("status") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_bookings_time_slots" ON "public"."bookings" USING "gin" ("time_slots");



COMMENT ON INDEX "public"."idx_bookings_time_slots" IS 'GIN index for efficient time slot queries';



CREATE INDEX "idx_career_applications_application_number" ON "public"."career_applications" USING "btree" ("application_number");



CREATE INDEX "idx_career_applications_created_at" ON "public"."career_applications" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_career_applications_email" ON "public"."career_applications" USING "btree" ("email");



CREATE INDEX "idx_career_applications_position" ON "public"."career_applications" USING "btree" ("position");



CREATE INDEX "idx_career_applications_status" ON "public"."career_applications" USING "btree" ("status");



CREATE INDEX "idx_cart_items_salon_id" ON "public"."cart_items" USING "btree" ("salon_id");



CREATE INDEX "idx_cart_items_user_id" ON "public"."cart_items" USING "btree" ("user_id");



CREATE INDEX "idx_coupon_redemptions_coupon_user" ON "public"."coupon_redemptions" USING "btree" ("coupon_id", "user_id");



CREATE INDEX "idx_coupon_redemptions_salon" ON "public"."coupon_redemptions" USING "btree" ("salon_id");



CREATE UNIQUE INDEX "idx_coupons_active_code" ON "public"."coupons" USING "btree" ("upper"("code")) WHERE "is_active";



CREATE INDEX "idx_coupons_scope_salon_active" ON "public"."coupons" USING "btree" ("scope", "salon_id", "is_active", "valid_until");



CREATE INDEX "idx_email_logs_created_at" ON "public"."email_logs" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_email_logs_failed_retry" ON "public"."email_logs" USING "btree" ("status", "next_retry_at") WHERE ("status" = 'failed'::"text");



CREATE INDEX "idx_email_logs_recipient" ON "public"."email_logs" USING "btree" ("recipient_email");



CREATE INDEX "idx_email_logs_related_entity" ON "public"."email_logs" USING "btree" ("related_entity_type", "related_entity_id");



CREATE INDEX "idx_email_logs_status" ON "public"."email_logs" USING "btree" ("status");



CREATE INDEX "idx_email_logs_type" ON "public"."email_logs" USING "btree" ("email_type");



CREATE INDEX "idx_favorites_created_at" ON "public"."favorites" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_favorites_salon_id" ON "public"."favorites" USING "btree" ("salon_id");



CREATE INDEX "idx_favorites_user_id" ON "public"."favorites" USING "btree" ("user_id");



CREATE INDEX "idx_otp_attempts_created_at" ON "public"."otp_attempts" USING "btree" ("created_at");



CREATE INDEX "idx_otp_attempts_phone" ON "public"."otp_attempts" USING "btree" ("phone");



CREATE INDEX "idx_otp_attempts_phone_blocked" ON "public"."otp_attempts" USING "btree" ("phone", "blocked_until");



CREATE INDEX "idx_otp_attempts_verification_id" ON "public"."otp_attempts" USING "btree" ("verification_id") WHERE ("verification_id" IS NOT NULL);



CREATE INDEX "idx_partner_requests_created_at" ON "public"."partner_requests" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_partner_requests_email" ON "public"."partner_requests" USING "btree" ("email");



CREATE INDEX "idx_partner_requests_status" ON "public"."partner_requests" USING "btree" ("status");



CREATE INDEX "idx_payments_booking_id" ON "public"."payments" USING "btree" ("booking_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_payments_customer_id" ON "public"."payments" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_payments_paid_at" ON "public"."payments" USING "btree" ("paid_at") WHERE (("status")::"text" = 'success'::"text");



CREATE INDEX "idx_payments_razorpay_order" ON "public"."payments" USING "btree" ("razorpay_order_id") WHERE ("razorpay_order_id" IS NOT NULL);



CREATE INDEX "idx_payments_razorpay_payment" ON "public"."payments" USING "btree" ("razorpay_payment_id") WHERE ("razorpay_payment_id" IS NOT NULL);



CREATE INDEX "idx_payments_status" ON "public"."payments" USING "btree" ("status") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_payments_type" ON "public"."payments" USING "btree" ("payment_type") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_payments_type_status" ON "public"."payments" USING "btree" ("payment_type", "status") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_phone_otp_created" ON "public"."phone_verification_codes" USING "btree" ("created_at");



CREATE INDEX "idx_phone_otp_expires" ON "public"."phone_verification_codes" USING "btree" ("expires_at") WHERE ("verified" = false);



CREATE INDEX "idx_phone_otp_phone" ON "public"."phone_verification_codes" USING "btree" ("phone") WHERE ("verified" = false);



CREATE INDEX "idx_product_cart_user_id" ON "public"."product_cart_items" USING "btree" ("user_id");



CREATE INDEX "idx_product_favorites_created_at" ON "public"."product_favorites" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_product_favorites_product_id" ON "public"."product_favorites" USING "btree" ("product_id");



CREATE INDEX "idx_product_favorites_user_id" ON "public"."product_favorites" USING "btree" ("user_id");



CREATE INDEX "idx_products_category" ON "public"."products" USING "btree" ("category");



CREATE INDEX "idx_products_created_at" ON "public"."products" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_products_is_active" ON "public"."products" USING "btree" ("is_active");



CREATE INDEX "idx_products_is_featured" ON "public"."products" USING "btree" ("is_featured");



CREATE INDEX "idx_products_slug" ON "public"."products" USING "btree" ("slug");



CREATE INDEX "idx_profiles_city_state" ON "public"."profiles" USING "btree" ("city", "state") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_profiles_deleted_at" ON "public"."profiles" USING "btree" ("deleted_at");



CREATE INDEX "idx_profiles_email" ON "public"."profiles" USING "btree" ("email") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_profiles_gender" ON "public"."profiles" USING "btree" ("gender") WHERE (("gender" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_profiles_is_internal" ON "public"."profiles" USING "btree" ("is_internal") WHERE ("is_internal" = true);



CREATE INDEX "idx_profiles_phone" ON "public"."profiles" USING "btree" ("phone") WHERE (("phone" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE UNIQUE INDEX "idx_profiles_phone_unique" ON "public"."profiles" USING "btree" ("phone") WHERE (("phone_verified" = true) AND ("phone" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_profiles_token_valid_after" ON "public"."profiles" USING "btree" ("id", "token_valid_after") WHERE ("token_valid_after" IS NOT NULL);



CREATE INDEX "idx_profiles_user_role" ON "public"."profiles" USING "btree" ("user_role");



CREATE INDEX "idx_reviews_customer_id" ON "public"."reviews" USING "btree" ("customer_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_reviews_deleted_at" ON "public"."reviews" USING "btree" ("deleted_at");



CREATE INDEX "idx_reviews_featured" ON "public"."reviews" USING "btree" ("is_featured") WHERE (("is_featured" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_reviews_hidden" ON "public"."reviews" USING "btree" ("is_hidden") WHERE ("is_hidden" = true);



CREATE INDEX "idx_reviews_rating" ON "public"."reviews" USING "btree" ("rating") WHERE (("deleted_at" IS NULL) AND ("is_hidden" = false));



CREATE INDEX "idx_reviews_salon_id" ON "public"."reviews" USING "btree" ("salon_id") WHERE (("deleted_at" IS NULL) AND ("is_hidden" = false));



CREATE INDEX "idx_reviews_service_id" ON "public"."reviews" USING "btree" ("service_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_reviews_verified" ON "public"."reviews" USING "btree" ("is_verified") WHERE (("is_verified" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_rm_score_history_created_at" ON "public"."rm_score_history" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_rm_score_history_rm_id" ON "public"."rm_score_history" USING "btree" ("rm_id");



CREATE INDEX "idx_salon_discount_promotions_salon_active" ON "public"."salon_discount_promotions" USING "btree" ("salon_id", "is_active", "start_date", "end_date");



CREATE INDEX "idx_salon_subscriptions_end_date" ON "public"."salon_subscriptions" USING "btree" ("end_date") WHERE (("status")::"text" = 'active'::"text");



CREATE INDEX "idx_salon_subscriptions_salon_id" ON "public"."salon_subscriptions" USING "btree" ("salon_id");



CREATE INDEX "idx_salon_subscriptions_status" ON "public"."salon_subscriptions" USING "btree" ("status");



CREATE INDEX "idx_salons_accepting_bookings" ON "public"."salons" USING "btree" ("accepting_bookings") WHERE (("accepting_bookings" = true) AND ("is_active" = true));



COMMENT ON INDEX "public"."idx_salons_accepting_bookings" IS 'Optimize queries for active salons accepting bookings';



CREATE INDEX "idx_salons_active_verified" ON "public"."salons" USING "btree" ("is_active", "is_verified", "registration_fee_paid") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_assigned_rm" ON "public"."salons" USING "btree" ("assigned_rm") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_city_lower" ON "public"."salons" USING "btree" ("lower"(TRIM(BOTH FROM "city"))) WHERE (("is_active" = true) AND ("is_verified" = true) AND ("registration_fee_paid" = true));



CREATE INDEX "idx_salons_city_state" ON "public"."salons" USING "btree" ("city", "state") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_deleted_at" ON "public"."salons" USING "btree" ("deleted_at");



CREATE UNIQUE INDEX "idx_salons_gst_unique" ON "public"."salons" USING "btree" ("gst_number") WHERE (("gst_number" IS NOT NULL) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_salons_join_request" ON "public"."salons" USING "btree" ("join_request_id");



CREATE INDEX "idx_salons_location" ON "public"."salons" USING "gist" ("location") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_salons_rating" ON "public"."salons" USING "btree" ("average_rating" DESC) WHERE (("is_active" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_salons_vendor_id" ON "public"."salons" USING "btree" ("vendor_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_service_categories_active" ON "public"."service_categories" USING "btree" ("is_active", "display_order");



CREATE INDEX "idx_service_subcategories_active_order" ON "public"."service_subcategories" USING "btree" ("is_active", "display_order");



CREATE INDEX "idx_service_subcategories_parent_category_id" ON "public"."service_subcategories" USING "btree" ("parent_category_id");



CREATE INDEX "idx_service_subcategories_parent_subcategory_id" ON "public"."service_subcategories" USING "btree" ("parent_subcategory_id");



CREATE INDEX "idx_services_active" ON "public"."services" USING "btree" ("is_active") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_services_category_id" ON "public"."services" USING "btree" ("category_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_services_deleted_at" ON "public"."services" USING "btree" ("deleted_at");



CREATE INDEX "idx_services_featured" ON "public"."services" USING "btree" ("is_featured") WHERE (("is_featured" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_services_price" ON "public"."services" USING "btree" ("price") WHERE (("is_active" = true) AND ("deleted_at" IS NULL));



CREATE INDEX "idx_services_salon_id" ON "public"."services" USING "btree" ("salon_id") WHERE ("deleted_at" IS NULL);



CREATE INDEX "idx_services_subcategory_id" ON "public"."services" USING "btree" ("subcategory_id");



CREATE INDEX "idx_system_config_active" ON "public"."system_config" USING "btree" ("is_active");



CREATE INDEX "idx_system_config_key" ON "public"."system_config" USING "btree" ("config_key") WHERE ("is_active" = true);



CREATE INDEX "idx_token_blacklist_expires" ON "public"."token_blacklist" USING "btree" ("expires_at");



CREATE INDEX "idx_token_blacklist_jti" ON "public"."token_blacklist" USING "btree" ("token_jti");



CREATE INDEX "idx_token_blacklist_user_id" ON "public"."token_blacklist" USING "btree" ("user_id");



CREATE INDEX "idx_vendor_join_requests_rm_created" ON "public"."vendor_join_requests" USING "btree" ("rm_id", "created_at" DESC);



COMMENT ON INDEX "public"."idx_vendor_join_requests_rm_created" IS 'Optimizes recent requests queries for RM dashboard';



CREATE INDEX "idx_vendor_join_requests_rm_id" ON "public"."vendor_join_requests" USING "btree" ("rm_id");



COMMENT ON INDEX "public"."idx_vendor_join_requests_rm_id" IS 'Optimizes COUNT queries for total RM requests';



CREATE INDEX "idx_vendor_join_requests_rm_status" ON "public"."vendor_join_requests" USING "btree" ("rm_id", "status");



COMMENT ON INDEX "public"."idx_vendor_join_requests_rm_status" IS 'Optimizes COUNT queries for RM statistics by status';



CREATE INDEX "idx_vendor_registration_payments_razorpay_order" ON "public"."vendor_registration_payments" USING "btree" ("razorpay_order_id");



CREATE INDEX "idx_vendor_registration_payments_razorpay_payment" ON "public"."vendor_registration_payments" USING "btree" ("razorpay_payment_id");



CREATE INDEX "idx_vendor_registration_payments_salon_id" ON "public"."vendor_registration_payments" USING "btree" ("salon_id") WHERE ("salon_id" IS NOT NULL);



CREATE INDEX "idx_vendor_registration_payments_status" ON "public"."vendor_registration_payments" USING "btree" ("status");



CREATE INDEX "idx_vendor_registration_payments_vendor" ON "public"."vendor_registration_payments" USING "btree" ("vendor_id");



CREATE INDEX "idx_vendor_registration_payments_vendor_id" ON "public"."vendor_registration_payments" USING "btree" ("vendor_id");



CREATE INDEX "idx_vendor_registration_payments_vendor_request_id" ON "public"."vendor_registration_payments" USING "btree" ("vendor_request_id") WHERE ("vendor_request_id" IS NOT NULL);



CREATE INDEX "idx_vendor_requests_location" ON "public"."vendor_join_requests" USING "btree" ("city", "state") WHERE ("status" = 'approved'::"public"."request_status");



CREATE INDEX "idx_vendor_requests_reviewed_by" ON "public"."vendor_join_requests" USING "btree" ("reviewed_by");



CREATE INDEX "idx_vendor_requests_rm_id" ON "public"."vendor_join_requests" USING "btree" ("rm_id");



CREATE INDEX "idx_vendor_requests_status" ON "public"."vendor_join_requests" USING "btree" ("status");



CREATE INDEX "idx_vendor_requests_status_draft" ON "public"."vendor_join_requests" USING "btree" ("status") WHERE ("status" = 'draft'::"public"."request_status");



CREATE INDEX "idx_vendor_requests_submitted" ON "public"."vendor_join_requests" USING "btree" ("submitted_at" DESC) WHERE ("submitted_at" IS NOT NULL);



CREATE OR REPLACE TRIGGER "email_logs_updated_at" BEFORE UPDATE ON "public"."email_logs" FOR EACH ROW EXECUTE FUNCTION "public"."update_email_logs_updated_at"();



CREATE OR REPLACE TRIGGER "set_booking_number" BEFORE INSERT ON "public"."bookings" FOR EACH ROW WHEN ((("new"."booking_number" IS NULL) OR (("new"."booking_number")::"text" = ''::"text"))) EXECUTE FUNCTION "public"."generate_booking_number"();



CREATE OR REPLACE TRIGGER "set_payments_updated_at" BEFORE UPDATE ON "public"."payments" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_salon_location" BEFORE INSERT OR UPDATE OF "latitude", "longitude" ON "public"."salons" FOR EACH ROW EXECUTE FUNCTION "public"."update_salon_location"();



CREATE OR REPLACE TRIGGER "set_system_config_updated_at" BEFORE UPDATE ON "public"."system_config" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."booking_payments" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."bookings" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."profiles" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."reviews" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."salons" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."service_categories" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."services" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."vendor_registration_payments" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "set_vendor_requests_updated_at" BEFORE UPDATE ON "public"."vendor_join_requests" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "trigger_banners_updated_at" BEFORE UPDATE ON "public"."banners" FOR EACH ROW EXECUTE FUNCTION "public"."update_banners_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_blog_posts_updated_at" BEFORE UPDATE ON "public"."blog_posts" FOR EACH ROW EXECUTE FUNCTION "public"."update_blog_posts_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_feature_flags_updated_at" BEFORE UPDATE ON "public"."feature_flags" FOR EACH ROW EXECUTE FUNCTION "public"."update_feature_flags_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_products_updated_at" BEFORE UPDATE ON "public"."products" FOR EACH ROW EXECUTE FUNCTION "public"."update_products_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_career_applications_updated_at" BEFORE UPDATE ON "public"."career_applications" FOR EACH ROW EXECUTE FUNCTION "public"."update_career_applications_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_coupons_updated_at" BEFORE UPDATE ON "public"."coupons" FOR EACH ROW EXECUTE FUNCTION "public"."update_coupons_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_partner_requests_updated_at" BEFORE UPDATE ON "public"."partner_requests" FOR EACH ROW EXECUTE FUNCTION "public"."update_partner_requests_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_rm_stats" AFTER INSERT OR DELETE OR UPDATE OF "status" ON "public"."vendor_join_requests" FOR EACH ROW EXECUTE FUNCTION "public"."update_rm_stats_counters"();



COMMENT ON TRIGGER "trigger_update_rm_stats" ON "public"."vendor_join_requests" IS 'Maintains real-time RM statistics counters';



CREATE OR REPLACE TRIGGER "trigger_update_salon_discount_promotions_updated_at" BEFORE UPDATE ON "public"."salon_discount_promotions" FOR EACH ROW EXECUTE FUNCTION "public"."update_salon_discount_promotions_updated_at"();



CREATE OR REPLACE TRIGGER "trigger_update_service_subcategories_updated_at" BEFORE UPDATE ON "public"."service_subcategories" FOR EACH ROW EXECUTE FUNCTION "public"."update_service_subcategories_updated_at"();



CREATE OR REPLACE TRIGGER "update_salon_rating_on_review_delete" AFTER UPDATE ON "public"."reviews" FOR EACH ROW WHEN ((("old"."deleted_at" IS NULL) AND ("new"."deleted_at" IS NOT NULL))) EXECUTE FUNCTION "public"."update_salon_rating"();



CREATE OR REPLACE TRIGGER "update_salon_rating_on_review_insert" AFTER INSERT ON "public"."reviews" FOR EACH ROW EXECUTE FUNCTION "public"."update_salon_rating"();



CREATE OR REPLACE TRIGGER "update_salon_rating_on_review_update" AFTER UPDATE ON "public"."reviews" FOR EACH ROW WHEN ((("old"."rating" IS DISTINCT FROM "new"."rating") OR ("old"."is_hidden" IS DISTINCT FROM "new"."is_hidden") OR ("old"."deleted_at" IS DISTINCT FROM "new"."deleted_at"))) EXECUTE FUNCTION "public"."update_salon_rating"();



ALTER TABLE ONLY "public"."activity_logs"
    ADD CONSTRAINT "activity_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."audit_logs"
    ADD CONSTRAINT "audit_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."blog_posts"
    ADD CONSTRAINT "blog_posts_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."profiles"("id") ON DELETE SET NULL;



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
    ADD CONSTRAINT "bookings_coupon_id_fkey" FOREIGN KEY ("coupon_id") REFERENCES "public"."coupons"("id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."bookings"
    ADD CONSTRAINT "bookings_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_service_id_fkey" FOREIGN KEY ("service_id") REFERENCES "public"."services"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."cart_items"
    ADD CONSTRAINT "cart_items_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."coupon_redemptions"
    ADD CONSTRAINT "coupon_redemptions_booking_id_fkey" FOREIGN KEY ("booking_id") REFERENCES "public"."bookings"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."coupon_redemptions"
    ADD CONSTRAINT "coupon_redemptions_coupon_id_fkey" FOREIGN KEY ("coupon_id") REFERENCES "public"."coupons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."coupons"
    ADD CONSTRAINT "coupons_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."favorites"
    ADD CONSTRAINT "favorites_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."feature_flags"
    ADD CONSTRAINT "feature_flags_enabled_by_fkey" FOREIGN KEY ("enabled_by") REFERENCES "public"."profiles"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_booking_id_fkey" FOREIGN KEY ("booking_id") REFERENCES "public"."bookings"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_customer_id_fkey" FOREIGN KEY ("customer_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."payments"
    ADD CONSTRAINT "payments_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."product_cart_items"
    ADD CONSTRAINT "product_cart_items_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."product_cart_items"
    ADD CONSTRAINT "product_cart_items_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."product_favorites"
    ADD CONSTRAINT "product_favorites_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."product_favorites"
    ADD CONSTRAINT "product_favorites_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."product_order_items"
    ADD CONSTRAINT "product_order_items_order_id_fkey" FOREIGN KEY ("order_id") REFERENCES "public"."product_orders"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."product_order_items"
    ADD CONSTRAINT "product_order_items_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id");



ALTER TABLE ONLY "public"."product_orders"
    ADD CONSTRAINT "product_orders_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id");



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



ALTER TABLE ONLY "public"."rm_profiles"
    ADD CONSTRAINT "rm_profiles_id_profiles_fkey" FOREIGN KEY ("id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."rm_score_history"
    ADD CONSTRAINT "rm_score_history_rm_id_fkey" FOREIGN KEY ("rm_id") REFERENCES "public"."rm_profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."salon_discount_promotions"
    ADD CONSTRAINT "salon_discount_promotions_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



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
    ADD CONSTRAINT "salons_join_request_id_fkey" FOREIGN KEY ("join_request_id") REFERENCES "public"."vendor_join_requests"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "auth"."users"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."salons"
    ADD CONSTRAINT "salons_verified_by_fkey" FOREIGN KEY ("verified_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."service_subcategories"
    ADD CONSTRAINT "service_subcategories_parent_category_id_fkey" FOREIGN KEY ("parent_category_id") REFERENCES "public"."service_categories"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."service_subcategories"
    ADD CONSTRAINT "service_subcategories_parent_subcategory_id_fkey" FOREIGN KEY ("parent_subcategory_id") REFERENCES "public"."service_subcategories"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_category_id_fkey" FOREIGN KEY ("category_id") REFERENCES "public"."service_categories"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_deleted_by_fkey" FOREIGN KEY ("deleted_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_subcategory_id_fkey" FOREIGN KEY ("subcategory_id") REFERENCES "public"."service_subcategories"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."services"
    ADD CONSTRAINT "services_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."system_config"
    ADD CONSTRAINT "system_config_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."token_blacklist"
    ADD CONSTRAINT "token_blacklist_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."vendor_join_requests"
    ADD CONSTRAINT "vendor_join_requests_reviewed_by_fkey" FOREIGN KEY ("reviewed_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."vendor_join_requests"
    ADD CONSTRAINT "vendor_join_requests_rm_id_fkey" FOREIGN KEY ("rm_id") REFERENCES "public"."rm_profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_salon_id_fkey" FOREIGN KEY ("salon_id") REFERENCES "public"."salons"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_vendor_id_fkey" FOREIGN KEY ("vendor_id") REFERENCES "public"."profiles"("id") ON DELETE RESTRICT;



ALTER TABLE ONLY "public"."vendor_registration_payments"
    ADD CONSTRAINT "vendor_registration_payments_vendor_request_id_fkey" FOREIGN KEY ("vendor_request_id") REFERENCES "public"."vendor_join_requests"("id") ON DELETE SET NULL;



CREATE POLICY "Admins can delete career applications" ON "public"."career_applications" FOR DELETE TO "authenticated" USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Admins can delete partner requests" ON "public"."partner_requests" FOR DELETE TO "authenticated" USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Admins can manage configs" ON "public"."system_config" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can update career applications" ON "public"."career_applications" FOR UPDATE TO "authenticated" USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Admins can update partner requests" ON "public"."partner_requests" FOR UPDATE TO "authenticated" USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Admins can update requests" ON "public"."vendor_join_requests" FOR UPDATE USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can view all activity logs" ON "public"."activity_logs" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Admins can view all career applications" ON "public"."career_applications" FOR SELECT TO "authenticated" USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Admins can view all partner requests" ON "public"."partner_requests" FOR SELECT TO "authenticated" USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Admins can view all requests" ON "public"."vendor_join_requests" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "Anyone can submit career applications" ON "public"."career_applications" FOR INSERT WITH CHECK (true);



CREATE POLICY "Anyone can submit partner requests" ON "public"."partner_requests" FOR INSERT WITH CHECK (true);



CREATE POLICY "Public can read active configs" ON "public"."system_config" FOR SELECT USING (("is_active" = true));



CREATE POLICY "RMs can create vendor requests" ON "public"."vendor_join_requests" FOR INSERT WITH CHECK (("rm_id" IN ( SELECT "rm_profiles"."id"
   FROM "public"."rm_profiles"
  WHERE ("rm_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "RMs can delete own draft requests" ON "public"."vendor_join_requests" FOR DELETE USING ((("rm_id" IN ( SELECT "rm_profiles"."id"
   FROM "public"."rm_profiles"
  WHERE ("rm_profiles"."id" = "auth"."uid"()))) AND ("status" = 'draft'::"public"."request_status")));



CREATE POLICY "RMs can update own draft requests" ON "public"."vendor_join_requests" FOR UPDATE USING ((("rm_id" IN ( SELECT "rm_profiles"."id"
   FROM "public"."rm_profiles"
  WHERE ("rm_profiles"."id" = "auth"."uid"()))) AND ("status" = 'draft'::"public"."request_status")));



CREATE POLICY "RMs can view own requests" ON "public"."vendor_join_requests" FOR SELECT USING (("rm_id" IN ( SELECT "rm_profiles"."id"
   FROM "public"."rm_profiles"
  WHERE ("rm_profiles"."id" = "auth"."uid"()))));



CREATE POLICY "Service role can insert activity logs" ON "public"."activity_logs" FOR INSERT WITH CHECK (true);



COMMENT ON POLICY "Service role can insert activity logs" ON "public"."activity_logs" IS 'Allows backend service (using service role key) to insert activity logs for audit trail';



CREATE POLICY "Service role can manage otp_attempts" ON "public"."otp_attempts" USING ((("auth"."jwt"() ->> 'role'::"text") = 'service_role'::"text"));



CREATE POLICY "Service role has full access to banners" ON "public"."banners" USING (true) WITH CHECK (true);



CREATE POLICY "Service role has full access to blog_posts" ON "public"."blog_posts" USING (true) WITH CHECK (true);



CREATE POLICY "Service role has full access to feature_flags" ON "public"."feature_flags" USING (true) WITH CHECK (true);



CREATE POLICY "Service role has full access to products" ON "public"."products" USING (true) WITH CHECK (true);



CREATE POLICY "Users can insert their own order items" ON "public"."product_order_items" FOR INSERT WITH CHECK ((EXISTS ( SELECT 1
   FROM "public"."product_orders"
  WHERE (("product_orders"."id" = "product_order_items"."order_id") AND ("product_orders"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can insert their own orders" ON "public"."product_orders" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can manage their own product cart items" ON "public"."product_cart_items" USING (("auth"."uid"() = "user_id")) WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own orders" ON "public"."product_orders" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own order items" ON "public"."product_order_items" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."product_orders"
  WHERE (("product_orders"."id" = "product_order_items"."order_id") AND ("product_orders"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view their own orders" ON "public"."product_orders" FOR SELECT USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."banners" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."blog_posts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."feature_flags" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."otp_attempts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."partner_requests" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "payments_delete_admin" ON "public"."payments" FOR UPDATE TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role"))))) WITH CHECK (("deleted_at" IS NOT NULL));



CREATE POLICY "payments_select_admin" ON "public"."payments" FOR SELECT TO "authenticated" USING (((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))) AND ("deleted_at" IS NULL)));



CREATE POLICY "payments_update_admin" ON "public"."payments" FOR UPDATE TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role"))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM "public"."profiles"
  WHERE (("profiles"."id" = "auth"."uid"()) AND ("profiles"."user_role" = 'admin'::"public"."user_role")))));



CREATE POLICY "payments_update_vendor" ON "public"."payments" FOR UPDATE TO "authenticated" USING (((("payment_type")::"text" = 'service_payment'::"text") AND (EXISTS ( SELECT 1
   FROM ("public"."bookings" "b"
     JOIN "public"."salons" "s" ON (("b"."salon_id" = "s"."id")))
  WHERE (("b"."id" = "payments"."booking_id") AND ("s"."vendor_id" = "auth"."uid"())))) AND ("deleted_at" IS NULL))) WITH CHECK (((("payment_type")::"text" = 'service_payment'::"text") AND (EXISTS ( SELECT 1
   FROM ("public"."bookings" "b"
     JOIN "public"."salons" "s" ON (("b"."salon_id" = "s"."id")))
  WHERE (("b"."id" = "payments"."booking_id") AND ("s"."vendor_id" = "auth"."uid"())))) AND ("deleted_at" IS NULL)));



ALTER TABLE "public"."product_cart_items" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."product_order_items" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."product_orders" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."products" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."system_config" ENABLE ROW LEVEL SECURITY;


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON FUNCTION "public"."cleanup_old_otp_attempts"() TO "anon";
GRANT ALL ON FUNCTION "public"."cleanup_old_otp_attempts"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."cleanup_old_otp_attempts"() TO "service_role";



GRANT ALL ON FUNCTION "public"."generate_booking_number"() TO "anon";
GRANT ALL ON FUNCTION "public"."generate_booking_number"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."generate_booking_number"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_booking_payment_status"("p_booking_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_booking_payment_status"("p_booking_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_booking_payment_status"("p_booking_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_nearby_salons"("user_lat" double precision, "user_lon" double precision, "radius_km" double precision, "max_results" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_nearby_salons"("user_lat" double precision, "user_lon" double precision, "radius_km" double precision, "max_results" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_nearby_salons"("user_lat" double precision, "user_lon" double precision, "radius_km" double precision, "max_results" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_popular_cities"("result_limit" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_popular_cities"("result_limit" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_popular_cities"("result_limit" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."record_service_payment"("p_booking_id" "uuid", "p_amount" numeric, "p_payment_method" character varying, "p_recorded_by" "uuid", "p_notes" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."record_service_payment"("p_booking_id" "uuid", "p_amount" numeric, "p_payment_method" character varying, "p_recorded_by" "uuid", "p_notes" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."record_service_payment"("p_booking_id" "uuid", "p_amount" numeric, "p_payment_method" character varying, "p_recorded_by" "uuid", "p_notes" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."redeem_coupon"("p_coupon_id" "uuid", "p_user_id" "uuid", "p_booking_id" "uuid", "p_discount_amount" numeric, "p_gross_discount" numeric) TO "anon";
GRANT ALL ON FUNCTION "public"."redeem_coupon"("p_coupon_id" "uuid", "p_user_id" "uuid", "p_booking_id" "uuid", "p_discount_amount" numeric, "p_gross_discount" numeric) TO "authenticated";
GRANT ALL ON FUNCTION "public"."redeem_coupon"("p_coupon_id" "uuid", "p_user_id" "uuid", "p_booking_id" "uuid", "p_discount_amount" numeric, "p_gross_discount" numeric) TO "service_role";



GRANT ALL ON FUNCTION "public"."update_banners_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_banners_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_banners_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_blog_posts_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_blog_posts_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_blog_posts_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_career_applications_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_career_applications_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_career_applications_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_coupons_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_coupons_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_coupons_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_email_logs_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_email_logs_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_email_logs_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_feature_flags_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_feature_flags_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_feature_flags_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_partner_requests_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_partner_requests_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_partner_requests_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_products_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_products_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_products_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_rm_stats_counters"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_rm_stats_counters"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_rm_stats_counters"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_salon_discount_promotions_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_salon_discount_promotions_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_salon_discount_promotions_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_salon_location"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_salon_location"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_salon_location"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_salon_rating"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_salon_rating"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_salon_rating"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_service_subcategories_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_service_subcategories_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_service_subcategories_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";



GRANT ALL ON FUNCTION "public"."validate_rm_stats_counters"("p_rm_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."validate_rm_stats_counters"("p_rm_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."validate_rm_stats_counters"("p_rm_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."verify_payment_and_confirm_booking"("p_razorpay_order_id" character varying, "p_razorpay_payment_id" character varying, "p_razorpay_signature" character varying) TO "anon";
GRANT ALL ON FUNCTION "public"."verify_payment_and_confirm_booking"("p_razorpay_order_id" character varying, "p_razorpay_payment_id" character varying, "p_razorpay_signature" character varying) TO "authenticated";
GRANT ALL ON FUNCTION "public"."verify_payment_and_confirm_booking"("p_razorpay_order_id" character varying, "p_razorpay_payment_id" character varying, "p_razorpay_signature" character varying) TO "service_role";



GRANT ALL ON TABLE "public"."activity_logs" TO "anon";
GRANT ALL ON TABLE "public"."activity_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."activity_logs" TO "service_role";



GRANT ALL ON TABLE "public"."audit_logs" TO "anon";
GRANT ALL ON TABLE "public"."audit_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."audit_logs" TO "service_role";



GRANT ALL ON TABLE "public"."banners" TO "anon";
GRANT ALL ON TABLE "public"."banners" TO "authenticated";
GRANT ALL ON TABLE "public"."banners" TO "service_role";



GRANT ALL ON TABLE "public"."blog_posts" TO "anon";
GRANT ALL ON TABLE "public"."blog_posts" TO "authenticated";
GRANT ALL ON TABLE "public"."blog_posts" TO "service_role";



GRANT ALL ON TABLE "public"."booking_payments" TO "anon";
GRANT ALL ON TABLE "public"."booking_payments" TO "authenticated";
GRANT ALL ON TABLE "public"."booking_payments" TO "service_role";



GRANT ALL ON TABLE "public"."bookings" TO "anon";
GRANT ALL ON TABLE "public"."bookings" TO "authenticated";
GRANT ALL ON TABLE "public"."bookings" TO "service_role";



GRANT ALL ON TABLE "public"."payments" TO "anon";
GRANT ALL ON TABLE "public"."payments" TO "authenticated";
GRANT ALL ON TABLE "public"."payments" TO "service_role";



GRANT ALL ON TABLE "public"."profiles" TO "anon";
GRANT ALL ON TABLE "public"."profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."profiles" TO "service_role";



GRANT ALL ON TABLE "public"."bookings_with_payments" TO "anon";
GRANT ALL ON TABLE "public"."bookings_with_payments" TO "authenticated";
GRANT ALL ON TABLE "public"."bookings_with_payments" TO "service_role";



GRANT ALL ON TABLE "public"."career_applications" TO "anon";
GRANT ALL ON TABLE "public"."career_applications" TO "authenticated";
GRANT ALL ON TABLE "public"."career_applications" TO "service_role";



GRANT ALL ON TABLE "public"."cart_items" TO "anon";
GRANT ALL ON TABLE "public"."cart_items" TO "authenticated";
GRANT ALL ON TABLE "public"."cart_items" TO "service_role";



GRANT ALL ON TABLE "public"."coupon_redemptions" TO "anon";
GRANT ALL ON TABLE "public"."coupon_redemptions" TO "authenticated";
GRANT ALL ON TABLE "public"."coupon_redemptions" TO "service_role";



GRANT ALL ON TABLE "public"."coupons" TO "anon";
GRANT ALL ON TABLE "public"."coupons" TO "authenticated";
GRANT ALL ON TABLE "public"."coupons" TO "service_role";



GRANT ALL ON TABLE "public"."salons" TO "anon";
GRANT ALL ON TABLE "public"."salons" TO "authenticated";
GRANT ALL ON TABLE "public"."salons" TO "service_role";



GRANT ALL ON TABLE "public"."coupon_redemption_report" TO "anon";
GRANT ALL ON TABLE "public"."coupon_redemption_report" TO "authenticated";
GRANT ALL ON TABLE "public"."coupon_redemption_report" TO "service_role";



GRANT ALL ON TABLE "public"."email_logs" TO "anon";
GRANT ALL ON TABLE "public"."email_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."email_logs" TO "service_role";



GRANT ALL ON TABLE "public"."favorites" TO "anon";
GRANT ALL ON TABLE "public"."favorites" TO "authenticated";
GRANT ALL ON TABLE "public"."favorites" TO "service_role";



GRANT ALL ON TABLE "public"."feature_flags" TO "anon";
GRANT ALL ON TABLE "public"."feature_flags" TO "authenticated";
GRANT ALL ON TABLE "public"."feature_flags" TO "service_role";



GRANT ALL ON TABLE "public"."otp_attempts" TO "anon";
GRANT ALL ON TABLE "public"."otp_attempts" TO "authenticated";
GRANT ALL ON TABLE "public"."otp_attempts" TO "service_role";



GRANT ALL ON TABLE "public"."partner_requests" TO "anon";
GRANT ALL ON TABLE "public"."partner_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."partner_requests" TO "service_role";



GRANT ALL ON TABLE "public"."pending_payments" TO "anon";
GRANT ALL ON TABLE "public"."pending_payments" TO "authenticated";
GRANT ALL ON TABLE "public"."pending_payments" TO "service_role";



GRANT ALL ON TABLE "public"."phone_verification_codes" TO "anon";
GRANT ALL ON TABLE "public"."phone_verification_codes" TO "authenticated";
GRANT ALL ON TABLE "public"."phone_verification_codes" TO "service_role";



GRANT ALL ON TABLE "public"."platform_revenue" TO "anon";
GRANT ALL ON TABLE "public"."platform_revenue" TO "authenticated";
GRANT ALL ON TABLE "public"."platform_revenue" TO "service_role";



GRANT ALL ON TABLE "public"."product_cart_items" TO "anon";
GRANT ALL ON TABLE "public"."product_cart_items" TO "authenticated";
GRANT ALL ON TABLE "public"."product_cart_items" TO "service_role";



GRANT ALL ON TABLE "public"."product_favorites" TO "anon";
GRANT ALL ON TABLE "public"."product_favorites" TO "authenticated";
GRANT ALL ON TABLE "public"."product_favorites" TO "service_role";



GRANT ALL ON TABLE "public"."product_order_items" TO "anon";
GRANT ALL ON TABLE "public"."product_order_items" TO "authenticated";
GRANT ALL ON TABLE "public"."product_order_items" TO "service_role";



GRANT ALL ON TABLE "public"."product_orders" TO "anon";
GRANT ALL ON TABLE "public"."product_orders" TO "authenticated";
GRANT ALL ON TABLE "public"."product_orders" TO "service_role";



GRANT ALL ON TABLE "public"."products" TO "anon";
GRANT ALL ON TABLE "public"."products" TO "authenticated";
GRANT ALL ON TABLE "public"."products" TO "service_role";



GRANT ALL ON TABLE "public"."reviews" TO "anon";
GRANT ALL ON TABLE "public"."reviews" TO "authenticated";
GRANT ALL ON TABLE "public"."reviews" TO "service_role";



GRANT ALL ON TABLE "public"."rm_profiles" TO "anon";
GRANT ALL ON TABLE "public"."rm_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."rm_profiles" TO "service_role";



GRANT ALL ON TABLE "public"."rm_profiles_with_user_data" TO "anon";
GRANT ALL ON TABLE "public"."rm_profiles_with_user_data" TO "authenticated";
GRANT ALL ON TABLE "public"."rm_profiles_with_user_data" TO "service_role";



GRANT ALL ON TABLE "public"."rm_score_history" TO "anon";
GRANT ALL ON TABLE "public"."rm_score_history" TO "authenticated";
GRANT ALL ON TABLE "public"."rm_score_history" TO "service_role";



GRANT ALL ON TABLE "public"."salon_discount_promotions" TO "anon";
GRANT ALL ON TABLE "public"."salon_discount_promotions" TO "authenticated";
GRANT ALL ON TABLE "public"."salon_discount_promotions" TO "service_role";



GRANT ALL ON TABLE "public"."salon_subscriptions" TO "anon";
GRANT ALL ON TABLE "public"."salon_subscriptions" TO "authenticated";
GRANT ALL ON TABLE "public"."salon_subscriptions" TO "service_role";



GRANT ALL ON TABLE "public"."service_categories" TO "anon";
GRANT ALL ON TABLE "public"."service_categories" TO "authenticated";
GRANT ALL ON TABLE "public"."service_categories" TO "service_role";



GRANT ALL ON TABLE "public"."service_subcategories" TO "anon";
GRANT ALL ON TABLE "public"."service_subcategories" TO "authenticated";
GRANT ALL ON TABLE "public"."service_subcategories" TO "service_role";



GRANT ALL ON TABLE "public"."services" TO "anon";
GRANT ALL ON TABLE "public"."services" TO "authenticated";
GRANT ALL ON TABLE "public"."services" TO "service_role";



GRANT ALL ON TABLE "public"."system_config" TO "anon";
GRANT ALL ON TABLE "public"."system_config" TO "authenticated";
GRANT ALL ON TABLE "public"."system_config" TO "service_role";



GRANT ALL ON TABLE "public"."token_blacklist" TO "anon";
GRANT ALL ON TABLE "public"."token_blacklist" TO "authenticated";
GRANT ALL ON TABLE "public"."token_blacklist" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_join_requests" TO "anon";
GRANT ALL ON TABLE "public"."vendor_join_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_join_requests" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_registration_payments" TO "anon";
GRANT ALL ON TABLE "public"."vendor_registration_payments" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_registration_payments" TO "service_role";



GRANT ALL ON TABLE "public"."vendor_revenue" TO "anon";
GRANT ALL ON TABLE "public"."vendor_revenue" TO "authenticated";
GRANT ALL ON TABLE "public"."vendor_revenue" TO "service_role";



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







