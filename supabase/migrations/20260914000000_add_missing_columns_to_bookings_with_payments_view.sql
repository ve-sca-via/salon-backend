-- Migration: Add missing bookings columns to bookings_with_payments view
--
-- Description: The view never selected b.duration_minutes, b.notes,
-- b.cancelled_at, b.cancellation_reason, b.created_by, b.updated_by,
-- b.deleted_by, or b.razorpay_payment_id, even though BookingResponse (the
-- response_model on GET /vendors/bookings and every other endpoint reading
-- this view) declares all of them. Pydantic silently filled the missing
-- ones with their schema defaults (duration_minutes always came back 60
-- regardless of the real booking; notes/cancellation_reason always null),
-- discovered while building the vendor bookings management page and
-- verifying a seeded booking's real duration (90) and notes against what
-- the API actually returned.

DROP VIEW IF EXISTS public.bookings_with_payments CASCADE;

CREATE VIEW public.bookings_with_payments AS
 SELECT b.id,
    b.booking_number,
    b.customer_id,
    b.salon_id,
    b.services,
    b.booking_date,
    b.time_slots,
    b.duration_minutes,
    b.notes,
    b.service_price,
    b.subtotal_service_price,
    b.discount_amount,
    b.convenience_fee,
    b.convenience_fee_discount,
    b.total_amount,
    b.coupon_id,
    b.coupon_code,
    b.status,
    b.cancelled_at,
    b.cancellation_reason,
    b.razorpay_payment_id,
    b.created_by,
    b.updated_by,
    b.created_at,
    b.updated_at,
    b.deleted_at,
    b.deleted_by,
    p.full_name AS customer_name,
    p.phone AS customer_phone,
    p.email AS customer_email,
    cf.id AS convenience_fee_payment_id,
    cf.amount AS convenience_fee_amount,
    cf.status AS convenience_fee_status,
    cf.paid_at AS convenience_fee_paid_at,
    cf.razorpay_payment_id AS convenience_fee_razorpay_payment_id,
    sp.id AS service_payment_id,
    sp.amount AS service_payment_amount,
    sp.status AS service_payment_status,
    sp.paid_at AS service_payment_paid_at,
    sp.payment_method AS service_payment_method,
    (cf.status::text = 'success'::text) AS is_convenience_fee_paid,
    (sp.status::text = 'success'::text) AS is_service_paid,
    ((cf.status::text = 'success'::text) AND (sp.status::text = 'success'::text)) AS is_fully_paid
   FROM ((public.bookings b
     LEFT JOIN public.profiles p ON (p.id = b.customer_id))
     LEFT JOIN public.payments cf ON ((cf.booking_id = b.id AND cf.payment_type::text = 'convenience_fee'::text AND cf.deleted_at IS NULL)))
     LEFT JOIN public.payments sp ON ((sp.booking_id = b.id AND sp.payment_type::text = 'service_payment'::text AND sp.deleted_at IS NULL))
  WHERE (b.deleted_at IS NULL);

COMMENT ON VIEW bookings_with_payments IS 'Bookings with payment summary and customer data. Customer information (name, phone, email) is fetched from profiles table via JOIN for data consistency. Selects every bookings column so response_model fields never silently fall back to their schema default.';
