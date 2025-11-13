drop extension if exists "pg_net";

create extension if not exists "cube" with schema "public";

create extension if not exists "earthdistance" with schema "public";

create extension if not exists "postgis" with schema "public";

create type "public"."booking_status" as enum ('pending', 'confirmed', 'cancelled', 'completed', 'no_show');

create type "public"."payment_status" as enum ('pending', 'success', 'failed', 'refunded');

create type "public"."payment_type" as enum ('registration_fee', 'convenience_fee', 'service_payment');

create type "public"."request_status" as enum ('draft', 'pending', 'approved', 'rejected');

create type "public"."user_role" as enum ('admin', 'relationship_manager', 'vendor', 'customer');

create sequence "public"."booking_number_seq";

create sequence "public"."favorites_id_seq";


  create table "public"."booking_payments" (
    "id" uuid not null default gen_random_uuid(),
    "booking_id" uuid not null,
    "customer_id" uuid not null,
    "amount" numeric(10,2) not null,
    "convenience_fee" numeric(10,2) not null default 0,
    "total_amount" numeric(10,2) not null,
    "status" public.payment_status default 'pending'::public.payment_status,
    "razorpay_order_id" character varying(255),
    "razorpay_payment_id" character varying(255),
    "razorpay_signature" character varying(255),
    "payment_method" character varying(50),
    "failure_reason" text,
    "metadata" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "paid_at" timestamp with time zone
      );



  create table "public"."bookings" (
    "id" uuid not null default gen_random_uuid(),
    "booking_number" character varying(50) not null,
    "customer_id" uuid not null,
    "salon_id" uuid not null,
    "service_id" uuid not null,
    "staff_id" uuid,
    "booking_date" date not null,
    "booking_time" time without time zone not null,
    "duration_minutes" integer not null,
    "status" public.booking_status default 'pending'::public.booking_status,
    "service_price" numeric(10,2) not null,
    "convenience_fee" numeric(10,2) not null default 0,
    "total_amount" numeric(10,2) not null,
    "customer_name" character varying(255) not null,
    "customer_phone" character varying(20) not null,
    "customer_email" character varying(255),
    "special_requests" text,
    "confirmed_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "cancelled_at" timestamp with time zone,
    "cancellation_reason" text,
    "cancelled_by" uuid,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );



  create table "public"."cart_items" (
    "id" uuid not null default gen_random_uuid(),
    "customer_id" uuid not null,
    "salon_id" uuid not null,
    "service_id" uuid not null,
    "salon_name" text not null,
    "service_name" text not null,
    "plan_name" text not null,
    "category" text not null,
    "description" text,
    "duration" integer not null,
    "price" numeric(10,2) not null,
    "quantity" integer not null default 1,
    "created_at" timestamp with time zone not null default now(),
    "updated_at" timestamp with time zone not null default now()
      );


alter table "public"."cart_items" enable row level security;


  create table "public"."favorites" (
    "id" bigint not null default nextval('public.favorites_id_seq'::regclass),
    "user_id" uuid not null,
    "salon_id" uuid not null,
    "created_at" timestamp with time zone default now()
      );


alter table "public"."favorites" enable row level security;


  create table "public"."profiles" (
    "id" uuid not null,
    "email" character varying(255) not null,
    "full_name" character varying(255) not null,
    "phone" character varying(20),
    "role" public.user_role not null default 'customer'::public.user_role,
    "is_active" boolean default true,
    "email_verified" boolean default false,
    "phone_verified" boolean default false,
    "profile_image_url" text,
    "address" text,
    "city" character varying(100),
    "state" character varying(100),
    "pincode" character varying(10),
    "latitude" numeric(10,8),
    "longitude" numeric(11,8),
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "last_login_at" timestamp with time zone
      );



  create table "public"."reviews" (
    "id" uuid not null default gen_random_uuid(),
    "booking_id" uuid not null,
    "customer_id" uuid not null,
    "salon_id" uuid not null,
    "staff_id" uuid,
    "rating" integer not null,
    "review_text" text,
    "images" jsonb,
    "is_verified" boolean default false,
    "is_visible" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );


alter table "public"."reviews" enable row level security;


  create table "public"."rm_profiles" (
    "id" uuid not null,
    "employee_id" character varying(50) not null,
    "total_score" integer default 0,
    "total_salons_added" integer default 0,
    "total_approved_salons" integer default 0,
    "joining_date" date default CURRENT_DATE,
    "is_active" boolean default true,
    "manager_notes" text,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );



  create table "public"."rm_score_history" (
    "id" uuid not null default gen_random_uuid(),
    "rm_id" uuid not null,
    "salon_id" uuid,
    "score_change" integer not null,
    "reason" text not null,
    "created_by" uuid,
    "created_at" timestamp with time zone default now()
      );



  create table "public"."salon_staff" (
    "id" uuid not null default gen_random_uuid(),
    "salon_id" uuid not null,
    "user_id" uuid,
    "full_name" character varying(255) not null,
    "email" character varying(255),
    "phone" character varying(20) not null,
    "designation" character varying(100),
    "joining_date" date default CURRENT_DATE,
    "is_active" boolean default true,
    "specializations" jsonb,
    "profile_image_url" text,
    "bio" text,
    "average_rating" numeric(3,2) default 0.0,
    "total_reviews" integer default 0,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );


alter table "public"."salon_staff" enable row level security;


  create table "public"."salons" (
    "id" uuid not null default gen_random_uuid(),
    "vendor_id" uuid,
    "rm_id" uuid,
    "join_request_id" uuid,
    "business_name" character varying(255) not null,
    "business_type" character varying(50) not null,
    "description" text,
    "phone" character varying(20) not null,
    "email" character varying(255),
    "website" character varying(255),
    "address" text not null,
    "city" character varying(100) not null,
    "state" character varying(100) not null,
    "pincode" character varying(10) not null,
    "latitude" numeric(10,8) not null,
    "longitude" numeric(11,8) not null,
    "gst_number" character varying(50),
    "business_license" text,
    "logo_url" text,
    "cover_image_url" text,
    "images" jsonb,
    "business_hours" jsonb,
    "is_active" boolean default true,
    "is_verified" boolean default false,
    "average_rating" numeric(3,2) default 0.0,
    "total_reviews" integer default 0,
    "registration_fee_paid" boolean default false,
    "registration_fee_amount" numeric(10,2),
    "registration_paid_at" timestamp with time zone,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "approved_at" timestamp with time zone,
    "subscription_status" text default 'pending'::text,
    "subscription_start_date" timestamp with time zone,
    "subscription_end_date" timestamp with time zone,
    "payment_amount" numeric(10,2),
    "payment_date" timestamp with time zone
      );


alter table "public"."salons" enable row level security;


  create table "public"."service_categories" (
    "id" uuid not null default gen_random_uuid(),
    "name" character varying(100) not null,
    "description" text,
    "icon_url" text,
    "display_order" integer default 0,
    "is_active" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );



  create table "public"."services" (
    "id" uuid not null default gen_random_uuid(),
    "salon_id" uuid not null,
    "category_id" uuid,
    "name" character varying(255) not null,
    "description" text,
    "duration_minutes" integer not null,
    "price" numeric(10,2) not null default 0,
    "is_active" boolean default true,
    "available_for_booking" boolean default true,
    "image_url" text,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );


alter table "public"."services" enable row level security;


  create table "public"."staff_availability" (
    "id" uuid not null default gen_random_uuid(),
    "staff_id" uuid not null,
    "day_of_week" integer not null,
    "start_time" time without time zone not null,
    "end_time" time without time zone not null,
    "is_available" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );



  create table "public"."system_config" (
    "id" uuid not null default gen_random_uuid(),
    "config_key" character varying(100) not null,
    "config_value" text not null,
    "config_type" character varying(50) not null,
    "description" text,
    "is_active" boolean default true,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "updated_by" uuid
      );


alter table "public"."system_config" enable row level security;


  create table "public"."token_blacklist" (
    "id" uuid not null default gen_random_uuid(),
    "token_jti" character varying(255) not null,
    "user_id" uuid not null,
    "token_type" character varying(20) not null,
    "blacklisted_at" timestamp with time zone default now(),
    "expires_at" timestamp with time zone not null,
    "reason" character varying(100) default 'logout'::character varying
      );



  create table "public"."user_carts" (
    "id" uuid not null default gen_random_uuid(),
    "user_id" uuid not null,
    "salon_id" uuid,
    "items" jsonb not null default '[]'::jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "total_amount" numeric(10,2) default 0,
    "item_count" integer default 0,
    "salon_name" text
      );


alter table "public"."user_carts" enable row level security;


  create table "public"."vendor_join_requests" (
    "id" uuid not null default gen_random_uuid(),
    "rm_id" uuid not null,
    "business_name" character varying(255) not null,
    "business_type" character varying(50) not null,
    "owner_name" character varying(255) not null,
    "owner_email" character varying(255) not null,
    "owner_phone" character varying(20) not null,
    "business_address" text not null,
    "city" character varying(100) not null,
    "state" character varying(100) not null,
    "pincode" character varying(10) not null,
    "latitude" numeric(10,8),
    "longitude" numeric(11,8),
    "gst_number" character varying(50),
    "business_license" text,
    "documents" jsonb,
    "status" public.request_status default 'pending'::public.request_status,
    "admin_notes" text,
    "reviewed_by" uuid,
    "reviewed_at" timestamp with time zone,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now()
      );


alter table "public"."vendor_join_requests" enable row level security;


  create table "public"."vendor_payments" (
    "id" uuid not null default gen_random_uuid(),
    "vendor_id" uuid not null,
    "salon_id" uuid,
    "payment_type" public.payment_type not null,
    "amount" numeric(10,2) not null,
    "status" public.payment_status default 'pending'::public.payment_status,
    "razorpay_order_id" character varying(255),
    "razorpay_payment_id" character varying(255),
    "razorpay_signature" character varying(255),
    "payment_method" character varying(50),
    "failure_reason" text,
    "metadata" jsonb,
    "created_at" timestamp with time zone default now(),
    "updated_at" timestamp with time zone default now(),
    "paid_at" timestamp with time zone
      );


alter sequence "public"."favorites_id_seq" owned by "public"."favorites"."id";

CREATE UNIQUE INDEX booking_payments_pkey ON public.booking_payments USING btree (id);

CREATE UNIQUE INDEX bookings_booking_number_key ON public.bookings USING btree (booking_number);

CREATE UNIQUE INDEX bookings_pkey ON public.bookings USING btree (id);

CREATE UNIQUE INDEX cart_items_pkey ON public.cart_items USING btree (id);

CREATE UNIQUE INDEX favorites_pkey ON public.favorites USING btree (id);

CREATE UNIQUE INDEX favorites_user_id_salon_id_key ON public.favorites USING btree (user_id, salon_id);

CREATE INDEX idx_bookings_booking_date ON public.bookings USING btree (booking_date);

CREATE INDEX idx_bookings_created_at ON public.bookings USING btree (created_at DESC);

CREATE INDEX idx_bookings_customer_id ON public.bookings USING btree (customer_id);

CREATE INDEX idx_bookings_salon_id ON public.bookings USING btree (salon_id);

CREATE INDEX idx_bookings_status ON public.bookings USING btree (status);

CREATE INDEX idx_cart_items_created_at ON public.cart_items USING btree (customer_id, created_at DESC);

CREATE INDEX idx_cart_items_customer_id ON public.cart_items USING btree (customer_id);

CREATE INDEX idx_cart_items_customer_salon ON public.cart_items USING btree (customer_id, salon_id);

CREATE INDEX idx_cart_items_salon_id ON public.cart_items USING btree (salon_id);

CREATE INDEX idx_cart_items_service_id ON public.cart_items USING btree (service_id);

CREATE INDEX idx_favorites_created_at ON public.favorites USING btree (created_at DESC);

CREATE INDEX idx_favorites_salon_id ON public.favorites USING btree (salon_id);

CREATE INDEX idx_favorites_user_id ON public.favorites USING btree (user_id);

CREATE INDEX idx_profiles_email ON public.profiles USING btree (email);

CREATE INDEX idx_profiles_is_active ON public.profiles USING btree (is_active);

CREATE INDEX idx_profiles_location ON public.profiles USING btree (latitude, longitude);

CREATE INDEX idx_profiles_role ON public.profiles USING btree (role);

CREATE INDEX idx_salon_staff_is_active ON public.salon_staff USING btree (is_active);

CREATE INDEX idx_salon_staff_salon_id ON public.salon_staff USING btree (salon_id);

CREATE INDEX idx_salons_city ON public.salons USING btree (city);

CREATE INDEX idx_salons_is_active ON public.salons USING btree (is_active);

CREATE INDEX idx_salons_location ON public.salons USING btree (latitude, longitude);

CREATE INDEX idx_salons_rm_id ON public.salons USING btree (rm_id);

CREATE INDEX idx_salons_vendor_id ON public.salons USING btree (vendor_id);

CREATE INDEX idx_services_category_id ON public.services USING btree (category_id);

CREATE INDEX idx_services_is_active ON public.services USING btree (is_active);

CREATE INDEX idx_services_salon_id ON public.services USING btree (salon_id);

CREATE INDEX idx_token_blacklist_expires_at ON public.token_blacklist USING btree (expires_at);

CREATE INDEX idx_token_blacklist_jti ON public.token_blacklist USING btree (token_jti);

CREATE INDEX idx_token_blacklist_user_id ON public.token_blacklist USING btree (user_id);

CREATE INDEX idx_user_carts_salon_id ON public.user_carts USING btree (salon_id);

CREATE INDEX idx_user_carts_user_id ON public.user_carts USING btree (user_id);

CREATE INDEX idx_vendor_join_requests_reviewed_by ON public.vendor_join_requests USING btree (reviewed_by);

CREATE INDEX idx_vendor_requests_rm_id ON public.vendor_join_requests USING btree (rm_id);

CREATE INDEX idx_vendor_requests_status ON public.vendor_join_requests USING btree (status);

CREATE INDEX idx_vendor_requests_status_draft ON public.vendor_join_requests USING btree (status) WHERE (status = 'draft'::public.request_status);

CREATE UNIQUE INDEX profiles_email_key ON public.profiles USING btree (email);

CREATE UNIQUE INDEX profiles_pkey ON public.profiles USING btree (id);

CREATE UNIQUE INDEX reviews_pkey ON public.reviews USING btree (id);

CREATE UNIQUE INDEX rm_profiles_employee_id_key ON public.rm_profiles USING btree (employee_id);

CREATE UNIQUE INDEX rm_profiles_pkey ON public.rm_profiles USING btree (id);

CREATE UNIQUE INDEX rm_score_history_pkey ON public.rm_score_history USING btree (id);

CREATE UNIQUE INDEX salon_staff_pkey ON public.salon_staff USING btree (id);

CREATE UNIQUE INDEX salons_pkey ON public.salons USING btree (id);

CREATE UNIQUE INDEX service_categories_pkey ON public.service_categories USING btree (id);

CREATE UNIQUE INDEX services_pkey ON public.services USING btree (id);

CREATE UNIQUE INDEX staff_availability_pkey ON public.staff_availability USING btree (id);

CREATE UNIQUE INDEX system_config_config_key_key ON public.system_config USING btree (config_key);

CREATE UNIQUE INDEX system_config_pkey ON public.system_config USING btree (id);

CREATE UNIQUE INDEX token_blacklist_pkey ON public.token_blacklist USING btree (id);

CREATE UNIQUE INDEX token_blacklist_token_jti_key ON public.token_blacklist USING btree (token_jti);

CREATE UNIQUE INDEX unique_customer_service ON public.cart_items USING btree (customer_id, service_id);

CREATE UNIQUE INDEX unique_review_per_booking ON public.reviews USING btree (booking_id);

CREATE UNIQUE INDEX user_carts_pkey ON public.user_carts USING btree (id);

CREATE UNIQUE INDEX user_carts_user_id_key ON public.user_carts USING btree (user_id);

CREATE UNIQUE INDEX vendor_join_requests_pkey ON public.vendor_join_requests USING btree (id);

CREATE UNIQUE INDEX vendor_payments_pkey ON public.vendor_payments USING btree (id);

alter table "public"."booking_payments" add constraint "booking_payments_pkey" PRIMARY KEY using index "booking_payments_pkey";

alter table "public"."bookings" add constraint "bookings_pkey" PRIMARY KEY using index "bookings_pkey";

alter table "public"."cart_items" add constraint "cart_items_pkey" PRIMARY KEY using index "cart_items_pkey";

alter table "public"."favorites" add constraint "favorites_pkey" PRIMARY KEY using index "favorites_pkey";

alter table "public"."profiles" add constraint "profiles_pkey" PRIMARY KEY using index "profiles_pkey";

alter table "public"."reviews" add constraint "reviews_pkey" PRIMARY KEY using index "reviews_pkey";

alter table "public"."rm_profiles" add constraint "rm_profiles_pkey" PRIMARY KEY using index "rm_profiles_pkey";

alter table "public"."rm_score_history" add constraint "rm_score_history_pkey" PRIMARY KEY using index "rm_score_history_pkey";

alter table "public"."salon_staff" add constraint "salon_staff_pkey" PRIMARY KEY using index "salon_staff_pkey";

alter table "public"."salons" add constraint "salons_pkey" PRIMARY KEY using index "salons_pkey";

alter table "public"."service_categories" add constraint "service_categories_pkey" PRIMARY KEY using index "service_categories_pkey";

alter table "public"."services" add constraint "services_pkey" PRIMARY KEY using index "services_pkey";

alter table "public"."staff_availability" add constraint "staff_availability_pkey" PRIMARY KEY using index "staff_availability_pkey";

alter table "public"."system_config" add constraint "system_config_pkey" PRIMARY KEY using index "system_config_pkey";

alter table "public"."token_blacklist" add constraint "token_blacklist_pkey" PRIMARY KEY using index "token_blacklist_pkey";

alter table "public"."user_carts" add constraint "user_carts_pkey" PRIMARY KEY using index "user_carts_pkey";

alter table "public"."vendor_join_requests" add constraint "vendor_join_requests_pkey" PRIMARY KEY using index "vendor_join_requests_pkey";

alter table "public"."vendor_payments" add constraint "vendor_payments_pkey" PRIMARY KEY using index "vendor_payments_pkey";

alter table "public"."booking_payments" add constraint "booking_payments_booking_id_fkey" FOREIGN KEY (booking_id) REFERENCES public.bookings(id) ON DELETE CASCADE not valid;

alter table "public"."booking_payments" validate constraint "booking_payments_booking_id_fkey";

alter table "public"."booking_payments" add constraint "booking_payments_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."booking_payments" validate constraint "booking_payments_customer_id_fkey";

alter table "public"."booking_payments" add constraint "valid_amount" CHECK (((amount >= (0)::numeric) AND (convenience_fee >= (0)::numeric) AND (total_amount >= (0)::numeric))) not valid;

alter table "public"."booking_payments" validate constraint "valid_amount";

alter table "public"."bookings" add constraint "bookings_booking_number_key" UNIQUE using index "bookings_booking_number_key";

alter table "public"."bookings" add constraint "bookings_cancelled_by_fkey" FOREIGN KEY (cancelled_by) REFERENCES auth.users(id) not valid;

alter table "public"."bookings" validate constraint "bookings_cancelled_by_fkey";

alter table "public"."bookings" add constraint "bookings_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."bookings" validate constraint "bookings_customer_id_fkey";

alter table "public"."bookings" add constraint "bookings_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."bookings" validate constraint "bookings_salon_id_fkey";

alter table "public"."bookings" add constraint "bookings_service_id_fkey" FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE not valid;

alter table "public"."bookings" validate constraint "bookings_service_id_fkey";

alter table "public"."bookings" add constraint "bookings_staff_id_fkey" FOREIGN KEY (staff_id) REFERENCES public.salon_staff(id) ON DELETE SET NULL not valid;

alter table "public"."bookings" validate constraint "bookings_staff_id_fkey";

alter table "public"."bookings" add constraint "valid_amounts" CHECK (((service_price >= (0)::numeric) AND (convenience_fee >= (0)::numeric) AND (total_amount >= (0)::numeric))) not valid;

alter table "public"."bookings" validate constraint "valid_amounts";

alter table "public"."bookings" add constraint "valid_status" CHECK ((status = ANY (ARRAY['pending'::public.booking_status, 'confirmed'::public.booking_status, 'cancelled'::public.booking_status, 'completed'::public.booking_status, 'no_show'::public.booking_status]))) not valid;

alter table "public"."bookings" validate constraint "valid_status";

alter table "public"."cart_items" add constraint "cart_items_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."cart_items" validate constraint "cart_items_customer_id_fkey";

alter table "public"."cart_items" add constraint "cart_items_quantity_check" CHECK ((quantity > 0)) not valid;

alter table "public"."cart_items" validate constraint "cart_items_quantity_check";

alter table "public"."cart_items" add constraint "cart_items_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."cart_items" validate constraint "cart_items_salon_id_fkey";

alter table "public"."cart_items" add constraint "cart_items_service_id_fkey" FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE not valid;

alter table "public"."cart_items" validate constraint "cart_items_service_id_fkey";

alter table "public"."cart_items" add constraint "duration_positive" CHECK ((duration > 0)) not valid;

alter table "public"."cart_items" validate constraint "duration_positive";

alter table "public"."cart_items" add constraint "price_positive" CHECK ((price > (0)::numeric)) not valid;

alter table "public"."cart_items" validate constraint "price_positive";

alter table "public"."cart_items" add constraint "quantity_positive" CHECK ((quantity > 0)) not valid;

alter table "public"."cart_items" validate constraint "quantity_positive";

alter table "public"."cart_items" add constraint "unique_customer_service" UNIQUE using index "unique_customer_service";

alter table "public"."favorites" add constraint "favorites_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."favorites" validate constraint "favorites_salon_id_fkey";

alter table "public"."favorites" add constraint "favorites_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE not valid;

alter table "public"."favorites" validate constraint "favorites_user_id_fkey";

alter table "public"."favorites" add constraint "favorites_user_id_salon_id_key" UNIQUE using index "favorites_user_id_salon_id_key";

alter table "public"."profiles" add constraint "profiles_email_key" UNIQUE using index "profiles_email_key";

alter table "public"."profiles" add constraint "profiles_id_fkey" FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE not valid;

alter table "public"."profiles" validate constraint "profiles_id_fkey";

alter table "public"."profiles" add constraint "valid_email" CHECK (((email)::text ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text)) not valid;

alter table "public"."profiles" validate constraint "valid_email";

alter table "public"."profiles" add constraint "valid_role" CHECK ((role = ANY (ARRAY['admin'::public.user_role, 'relationship_manager'::public.user_role, 'vendor'::public.user_role, 'customer'::public.user_role]))) not valid;

alter table "public"."profiles" validate constraint "valid_role";

alter table "public"."reviews" add constraint "reviews_booking_id_fkey" FOREIGN KEY (booking_id) REFERENCES public.bookings(id) ON DELETE CASCADE not valid;

alter table "public"."reviews" validate constraint "reviews_booking_id_fkey";

alter table "public"."reviews" add constraint "reviews_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."reviews" validate constraint "reviews_customer_id_fkey";

alter table "public"."reviews" add constraint "reviews_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."reviews" validate constraint "reviews_salon_id_fkey";

alter table "public"."reviews" add constraint "reviews_staff_id_fkey" FOREIGN KEY (staff_id) REFERENCES public.salon_staff(id) ON DELETE SET NULL not valid;

alter table "public"."reviews" validate constraint "reviews_staff_id_fkey";

alter table "public"."reviews" add constraint "unique_review_per_booking" UNIQUE using index "unique_review_per_booking";

alter table "public"."reviews" add constraint "valid_rating" CHECK (((rating >= 1) AND (rating <= 5))) not valid;

alter table "public"."reviews" validate constraint "valid_rating";

alter table "public"."rm_profiles" add constraint "rm_profiles_employee_id_key" UNIQUE using index "rm_profiles_employee_id_key";

alter table "public"."rm_profiles" add constraint "rm_profiles_id_fkey" FOREIGN KEY (id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."rm_profiles" validate constraint "rm_profiles_id_fkey";

alter table "public"."rm_score_history" add constraint "rm_score_history_created_by_fkey" FOREIGN KEY (created_by) REFERENCES auth.users(id) not valid;

alter table "public"."rm_score_history" validate constraint "rm_score_history_created_by_fkey";

alter table "public"."rm_score_history" add constraint "rm_score_history_rm_id_fkey" FOREIGN KEY (rm_id) REFERENCES public.rm_profiles(id) ON DELETE CASCADE not valid;

alter table "public"."rm_score_history" validate constraint "rm_score_history_rm_id_fkey";

alter table "public"."salon_staff" add constraint "salon_staff_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."salon_staff" validate constraint "salon_staff_salon_id_fkey";

alter table "public"."salon_staff" add constraint "salon_staff_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE SET NULL not valid;

alter table "public"."salon_staff" validate constraint "salon_staff_user_id_fkey";

alter table "public"."salon_staff" add constraint "valid_rating" CHECK (((average_rating >= (0)::numeric) AND (average_rating <= (5)::numeric))) not valid;

alter table "public"."salon_staff" validate constraint "valid_rating";

alter table "public"."salons" add constraint "salons_join_request_id_fkey" FOREIGN KEY (join_request_id) REFERENCES public.vendor_join_requests(id) not valid;

alter table "public"."salons" validate constraint "salons_join_request_id_fkey";

alter table "public"."salons" add constraint "salons_rm_id_fkey" FOREIGN KEY (rm_id) REFERENCES public.rm_profiles(id) not valid;

alter table "public"."salons" validate constraint "salons_rm_id_fkey";

alter table "public"."salons" add constraint "salons_subscription_status_check" CHECK ((subscription_status = ANY (ARRAY['pending'::text, 'active'::text, 'expired'::text, 'cancelled'::text]))) not valid;

alter table "public"."salons" validate constraint "salons_subscription_status_check";

alter table "public"."salons" add constraint "salons_vendor_id_fkey" FOREIGN KEY (vendor_id) REFERENCES public.profiles(id) ON DELETE SET NULL not valid;

alter table "public"."salons" validate constraint "salons_vendor_id_fkey";

alter table "public"."salons" add constraint "valid_rating" CHECK (((average_rating >= (0)::numeric) AND (average_rating <= (5)::numeric))) not valid;

alter table "public"."salons" validate constraint "valid_rating";

alter table "public"."services" add constraint "services_category_id_fkey" FOREIGN KEY (category_id) REFERENCES public.service_categories(id) ON DELETE SET NULL not valid;

alter table "public"."services" validate constraint "services_category_id_fkey";

alter table "public"."services" add constraint "services_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."services" validate constraint "services_salon_id_fkey";

alter table "public"."services" add constraint "valid_duration" CHECK ((duration_minutes > 0)) not valid;

alter table "public"."services" validate constraint "valid_duration";

alter table "public"."services" add constraint "valid_price" CHECK ((price >= (0)::numeric)) not valid;

alter table "public"."services" validate constraint "valid_price";

alter table "public"."staff_availability" add constraint "staff_availability_staff_id_fkey" FOREIGN KEY (staff_id) REFERENCES public.salon_staff(id) ON DELETE CASCADE not valid;

alter table "public"."staff_availability" validate constraint "staff_availability_staff_id_fkey";

alter table "public"."staff_availability" add constraint "valid_day" CHECK (((day_of_week >= 0) AND (day_of_week <= 6))) not valid;

alter table "public"."staff_availability" validate constraint "valid_day";

alter table "public"."staff_availability" add constraint "valid_time_range" CHECK ((end_time > start_time)) not valid;

alter table "public"."staff_availability" validate constraint "valid_time_range";

alter table "public"."system_config" add constraint "system_config_config_key_key" UNIQUE using index "system_config_config_key_key";

alter table "public"."system_config" add constraint "system_config_updated_by_fkey" FOREIGN KEY (updated_by) REFERENCES auth.users(id) not valid;

alter table "public"."system_config" validate constraint "system_config_updated_by_fkey";

alter table "public"."token_blacklist" add constraint "token_blacklist_token_jti_key" UNIQUE using index "token_blacklist_token_jti_key";

alter table "public"."token_blacklist" add constraint "token_blacklist_user_id_fkey" FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."token_blacklist" validate constraint "token_blacklist_user_id_fkey";

alter table "public"."token_blacklist" add constraint "valid_token_type" CHECK (((token_type)::text = ANY ((ARRAY['access'::character varying, 'refresh'::character varying])::text[]))) not valid;

alter table "public"."token_blacklist" validate constraint "valid_token_type";

alter table "public"."user_carts" add constraint "user_carts_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE not valid;

alter table "public"."user_carts" validate constraint "user_carts_user_id_fkey";

alter table "public"."user_carts" add constraint "user_carts_user_id_key" UNIQUE using index "user_carts_user_id_key";

alter table "public"."vendor_join_requests" add constraint "valid_status" CHECK ((status = ANY (ARRAY['draft'::public.request_status, 'pending'::public.request_status, 'approved'::public.request_status, 'rejected'::public.request_status]))) not valid;

alter table "public"."vendor_join_requests" validate constraint "valid_status";

alter table "public"."vendor_join_requests" add constraint "vendor_join_requests_reviewed_by_fkey" FOREIGN KEY (reviewed_by) REFERENCES auth.users(id) not valid;

alter table "public"."vendor_join_requests" validate constraint "vendor_join_requests_reviewed_by_fkey";

alter table "public"."vendor_join_requests" add constraint "vendor_join_requests_rm_id_fkey" FOREIGN KEY (rm_id) REFERENCES public.rm_profiles(id) not valid;

alter table "public"."vendor_join_requests" validate constraint "vendor_join_requests_rm_id_fkey";

alter table "public"."vendor_payments" add constraint "valid_amount" CHECK ((amount >= (0)::numeric)) not valid;

alter table "public"."vendor_payments" validate constraint "valid_amount";

alter table "public"."vendor_payments" add constraint "valid_payment_type" CHECK ((payment_type = ANY (ARRAY['registration_fee'::public.payment_type, 'convenience_fee'::public.payment_type, 'service_payment'::public.payment_type]))) not valid;

alter table "public"."vendor_payments" validate constraint "valid_payment_type";

alter table "public"."vendor_payments" add constraint "vendor_payments_salon_id_fkey" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE SET NULL not valid;

alter table "public"."vendor_payments" validate constraint "vendor_payments_salon_id_fkey";

alter table "public"."vendor_payments" add constraint "vendor_payments_vendor_id_fkey" FOREIGN KEY (vendor_id) REFERENCES public.profiles(id) ON DELETE CASCADE not valid;

alter table "public"."vendor_payments" validate constraint "vendor_payments_vendor_id_fkey";

set check_function_bodies = off;

CREATE OR REPLACE FUNCTION public.generate_booking_number()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.booking_number := 'BK-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || 
                          LPAD(NEXTVAL('booking_number_seq')::TEXT, 4, '0');
    RETURN NEW;
END;
$function$
;



CREATE OR REPLACE FUNCTION public.get_nearby_salons(user_lat double precision, user_lon double precision, radius_km double precision DEFAULT 10.0, max_results integer DEFAULT 50)
 RETURNS TABLE(id uuid, business_name character varying, description text, phone character varying, email character varying, website character varying, address text, city character varying, state character varying, pincode character varying, latitude numeric, longitude numeric, logo_url text, cover_image_url text, images jsonb, average_rating numeric, total_reviews integer, business_hours jsonb, is_active boolean, is_verified boolean, registration_fee_paid boolean, created_at timestamp with time zone, updated_at timestamp with time zone, distance_km double precision)
 LANGUAGE plpgsql
 STABLE
AS $function$
BEGIN
  RETURN QUERY
  SELECT 
    s.id,
    s.business_name,
    s.description,
    s.phone,
    s.email,
    s.website,
    s.address,
    s.city,
    s.state,
    s.pincode,
    s.latitude,
    s.longitude,
    s.logo_url,
    s.cover_image_url,
    s.images,
    s.average_rating,
    s.total_reviews,
    s.business_hours,
    s.is_active,
    s.is_verified,
    s.registration_fee_paid,
    s.created_at,
    s.updated_at,
    -- Calculate distance in kilometers using PostGIS earthdistance
    -- earth_distance returns meters, divide by 1000 for kilometers
    (earth_distance(
      ll_to_earth(user_lat, user_lon),
      ll_to_earth(s.latitude::float8, s.longitude::float8)
    ) / 1000.0)::FLOAT AS distance_km
  FROM salons s
  WHERE 
    -- Filter 1: Only show active, verified, and paid salons
    s.is_active = true
    AND s.is_verified = true
    AND s.registration_fee_paid = true
    -- Filter 2: Bounding box optimization (faster than full distance calc)
    -- earth_box creates a bounding box around the user location
    -- This eliminates most salons before doing expensive distance calculations
    AND earth_box(ll_to_earth(user_lat, user_lon), radius_km * 1000.0) 
        @> ll_to_earth(s.latitude::float8, s.longitude::float8)
    -- Filter 3: Ensure coordinates are valid (not null)
    AND s.latitude IS NOT NULL 
    AND s.longitude IS NOT NULL
  -- Sort by distance (closest first)
  ORDER BY distance_km ASC
  -- Limit results
  LIMIT LEAST(max_results, 100); -- Max 100 results for performance
END;
$function$
;

CREATE OR REPLACE FUNCTION public.sync_email_verification()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
BEGIN
  -- Update profile email_verified when email_confirmed_at changes
  IF NEW.email_confirmed_at IS NOT NULL AND OLD.email_confirmed_at IS NULL THEN
    UPDATE public.profiles
    SET 
      email_verified = true,
      updated_at = NOW()
    WHERE id = NEW.id;
    
    RAISE NOTICE 'Email verified for user %', NEW.id;
  END IF;
  
  RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_cart_items_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_rm_score_on_approval()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    score_to_add INTEGER;
BEGIN
    -- Only when status changes from 'pending' to 'approved'
    IF OLD.status = 'pending' AND NEW.status = 'approved' THEN
        -- Get current RM score configuration
        SELECT config_value::INTEGER INTO score_to_add
        FROM public.system_config
        WHERE config_key = 'rm_score_per_approval' AND is_active = true;
        
        -- Update RM profile
        UPDATE public.rm_profiles
        SET 
            total_score = total_score + COALESCE(score_to_add, 10),
            total_approved_salons = total_approved_salons + 1
        WHERE id = NEW.rm_id;
        
        -- Add score history entry
        INSERT INTO public.rm_score_history (rm_id, salon_id, score_change, reason)
        VALUES (NEW.rm_id, NEW.id, COALESCE(score_to_add, 10), 'Salon approved: ' || NEW.business_name);
    END IF;
    
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_salon_rating()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    UPDATE public.salons
    SET 
        average_rating = (
            SELECT COALESCE(AVG(rating), 0)
            FROM public.reviews
            WHERE salon_id = NEW.salon_id AND is_visible = true
        ),
        total_reviews = (
            SELECT COUNT(*)
            FROM public.reviews
            WHERE salon_id = NEW.salon_id AND is_visible = true
        )
    WHERE id = NEW.salon_id;
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$
;

CREATE OR REPLACE FUNCTION public.update_user_carts_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$function$
;

grant delete on table "public"."booking_payments" to "anon";

grant insert on table "public"."booking_payments" to "anon";

grant references on table "public"."booking_payments" to "anon";

grant select on table "public"."booking_payments" to "anon";

grant trigger on table "public"."booking_payments" to "anon";

grant truncate on table "public"."booking_payments" to "anon";

grant update on table "public"."booking_payments" to "anon";

grant delete on table "public"."booking_payments" to "authenticated";

grant insert on table "public"."booking_payments" to "authenticated";

grant references on table "public"."booking_payments" to "authenticated";

grant select on table "public"."booking_payments" to "authenticated";

grant trigger on table "public"."booking_payments" to "authenticated";

grant truncate on table "public"."booking_payments" to "authenticated";

grant update on table "public"."booking_payments" to "authenticated";

grant delete on table "public"."booking_payments" to "service_role";

grant insert on table "public"."booking_payments" to "service_role";

grant references on table "public"."booking_payments" to "service_role";

grant select on table "public"."booking_payments" to "service_role";

grant trigger on table "public"."booking_payments" to "service_role";

grant truncate on table "public"."booking_payments" to "service_role";

grant update on table "public"."booking_payments" to "service_role";

grant delete on table "public"."bookings" to "anon";

grant insert on table "public"."bookings" to "anon";

grant references on table "public"."bookings" to "anon";

grant select on table "public"."bookings" to "anon";

grant trigger on table "public"."bookings" to "anon";

grant truncate on table "public"."bookings" to "anon";

grant update on table "public"."bookings" to "anon";

grant delete on table "public"."bookings" to "authenticated";

grant insert on table "public"."bookings" to "authenticated";

grant references on table "public"."bookings" to "authenticated";

grant select on table "public"."bookings" to "authenticated";

grant trigger on table "public"."bookings" to "authenticated";

grant truncate on table "public"."bookings" to "authenticated";

grant update on table "public"."bookings" to "authenticated";

grant delete on table "public"."bookings" to "service_role";

grant insert on table "public"."bookings" to "service_role";

grant references on table "public"."bookings" to "service_role";

grant select on table "public"."bookings" to "service_role";

grant trigger on table "public"."bookings" to "service_role";

grant truncate on table "public"."bookings" to "service_role";

grant update on table "public"."bookings" to "service_role";

grant delete on table "public"."cart_items" to "anon";

grant insert on table "public"."cart_items" to "anon";

grant references on table "public"."cart_items" to "anon";

grant select on table "public"."cart_items" to "anon";

grant trigger on table "public"."cart_items" to "anon";

grant truncate on table "public"."cart_items" to "anon";

grant update on table "public"."cart_items" to "anon";

grant delete on table "public"."cart_items" to "authenticated";

grant insert on table "public"."cart_items" to "authenticated";

grant references on table "public"."cart_items" to "authenticated";

grant select on table "public"."cart_items" to "authenticated";

grant trigger on table "public"."cart_items" to "authenticated";

grant truncate on table "public"."cart_items" to "authenticated";

grant update on table "public"."cart_items" to "authenticated";

grant delete on table "public"."cart_items" to "service_role";

grant insert on table "public"."cart_items" to "service_role";

grant references on table "public"."cart_items" to "service_role";

grant select on table "public"."cart_items" to "service_role";

grant trigger on table "public"."cart_items" to "service_role";

grant truncate on table "public"."cart_items" to "service_role";

grant update on table "public"."cart_items" to "service_role";

grant delete on table "public"."favorites" to "anon";

grant insert on table "public"."favorites" to "anon";

grant references on table "public"."favorites" to "anon";

grant select on table "public"."favorites" to "anon";

grant trigger on table "public"."favorites" to "anon";

grant truncate on table "public"."favorites" to "anon";

grant update on table "public"."favorites" to "anon";

grant delete on table "public"."favorites" to "authenticated";

grant insert on table "public"."favorites" to "authenticated";

grant references on table "public"."favorites" to "authenticated";

grant select on table "public"."favorites" to "authenticated";

grant trigger on table "public"."favorites" to "authenticated";

grant truncate on table "public"."favorites" to "authenticated";

grant update on table "public"."favorites" to "authenticated";

grant delete on table "public"."favorites" to "service_role";

grant insert on table "public"."favorites" to "service_role";

grant references on table "public"."favorites" to "service_role";

grant select on table "public"."favorites" to "service_role";

grant trigger on table "public"."favorites" to "service_role";

grant truncate on table "public"."favorites" to "service_role";

grant update on table "public"."favorites" to "service_role";

grant delete on table "public"."profiles" to "anon";

grant insert on table "public"."profiles" to "anon";

grant references on table "public"."profiles" to "anon";

grant select on table "public"."profiles" to "anon";

grant trigger on table "public"."profiles" to "anon";

grant truncate on table "public"."profiles" to "anon";

grant update on table "public"."profiles" to "anon";

grant delete on table "public"."profiles" to "authenticated";

grant insert on table "public"."profiles" to "authenticated";

grant references on table "public"."profiles" to "authenticated";

grant select on table "public"."profiles" to "authenticated";

grant trigger on table "public"."profiles" to "authenticated";

grant truncate on table "public"."profiles" to "authenticated";

grant update on table "public"."profiles" to "authenticated";

grant delete on table "public"."profiles" to "service_role";

grant insert on table "public"."profiles" to "service_role";

grant references on table "public"."profiles" to "service_role";

grant select on table "public"."profiles" to "service_role";

grant trigger on table "public"."profiles" to "service_role";

grant truncate on table "public"."profiles" to "service_role";

grant update on table "public"."profiles" to "service_role";

grant delete on table "public"."reviews" to "anon";

grant insert on table "public"."reviews" to "anon";

grant references on table "public"."reviews" to "anon";

grant select on table "public"."reviews" to "anon";

grant trigger on table "public"."reviews" to "anon";

grant truncate on table "public"."reviews" to "anon";

grant update on table "public"."reviews" to "anon";

grant delete on table "public"."reviews" to "authenticated";

grant insert on table "public"."reviews" to "authenticated";

grant references on table "public"."reviews" to "authenticated";

grant select on table "public"."reviews" to "authenticated";

grant trigger on table "public"."reviews" to "authenticated";

grant truncate on table "public"."reviews" to "authenticated";

grant update on table "public"."reviews" to "authenticated";

grant delete on table "public"."reviews" to "service_role";

grant insert on table "public"."reviews" to "service_role";

grant references on table "public"."reviews" to "service_role";

grant select on table "public"."reviews" to "service_role";

grant trigger on table "public"."reviews" to "service_role";

grant truncate on table "public"."reviews" to "service_role";

grant update on table "public"."reviews" to "service_role";

grant delete on table "public"."rm_profiles" to "anon";

grant insert on table "public"."rm_profiles" to "anon";

grant references on table "public"."rm_profiles" to "anon";

grant select on table "public"."rm_profiles" to "anon";

grant trigger on table "public"."rm_profiles" to "anon";

grant truncate on table "public"."rm_profiles" to "anon";

grant update on table "public"."rm_profiles" to "anon";

grant delete on table "public"."rm_profiles" to "authenticated";

grant insert on table "public"."rm_profiles" to "authenticated";

grant references on table "public"."rm_profiles" to "authenticated";

grant select on table "public"."rm_profiles" to "authenticated";

grant trigger on table "public"."rm_profiles" to "authenticated";

grant truncate on table "public"."rm_profiles" to "authenticated";

grant update on table "public"."rm_profiles" to "authenticated";

grant delete on table "public"."rm_profiles" to "service_role";

grant insert on table "public"."rm_profiles" to "service_role";

grant references on table "public"."rm_profiles" to "service_role";

grant select on table "public"."rm_profiles" to "service_role";

grant trigger on table "public"."rm_profiles" to "service_role";

grant truncate on table "public"."rm_profiles" to "service_role";

grant update on table "public"."rm_profiles" to "service_role";

grant delete on table "public"."rm_score_history" to "anon";

grant insert on table "public"."rm_score_history" to "anon";

grant references on table "public"."rm_score_history" to "anon";

grant select on table "public"."rm_score_history" to "anon";

grant trigger on table "public"."rm_score_history" to "anon";

grant truncate on table "public"."rm_score_history" to "anon";

grant update on table "public"."rm_score_history" to "anon";

grant delete on table "public"."rm_score_history" to "authenticated";

grant insert on table "public"."rm_score_history" to "authenticated";

grant references on table "public"."rm_score_history" to "authenticated";

grant select on table "public"."rm_score_history" to "authenticated";

grant trigger on table "public"."rm_score_history" to "authenticated";

grant truncate on table "public"."rm_score_history" to "authenticated";

grant update on table "public"."rm_score_history" to "authenticated";

grant delete on table "public"."rm_score_history" to "service_role";

grant insert on table "public"."rm_score_history" to "service_role";

grant references on table "public"."rm_score_history" to "service_role";

grant select on table "public"."rm_score_history" to "service_role";

grant trigger on table "public"."rm_score_history" to "service_role";

grant truncate on table "public"."rm_score_history" to "service_role";

grant update on table "public"."rm_score_history" to "service_role";

grant delete on table "public"."salon_staff" to "anon";

grant insert on table "public"."salon_staff" to "anon";

grant references on table "public"."salon_staff" to "anon";

grant select on table "public"."salon_staff" to "anon";

grant trigger on table "public"."salon_staff" to "anon";

grant truncate on table "public"."salon_staff" to "anon";

grant update on table "public"."salon_staff" to "anon";

grant delete on table "public"."salon_staff" to "authenticated";

grant insert on table "public"."salon_staff" to "authenticated";

grant references on table "public"."salon_staff" to "authenticated";

grant select on table "public"."salon_staff" to "authenticated";

grant trigger on table "public"."salon_staff" to "authenticated";

grant truncate on table "public"."salon_staff" to "authenticated";

grant update on table "public"."salon_staff" to "authenticated";

grant delete on table "public"."salon_staff" to "service_role";

grant insert on table "public"."salon_staff" to "service_role";

grant references on table "public"."salon_staff" to "service_role";

grant select on table "public"."salon_staff" to "service_role";

grant trigger on table "public"."salon_staff" to "service_role";

grant truncate on table "public"."salon_staff" to "service_role";

grant update on table "public"."salon_staff" to "service_role";

grant delete on table "public"."salons" to "anon";

grant insert on table "public"."salons" to "anon";

grant references on table "public"."salons" to "anon";

grant select on table "public"."salons" to "anon";

grant trigger on table "public"."salons" to "anon";

grant truncate on table "public"."salons" to "anon";

grant update on table "public"."salons" to "anon";

grant delete on table "public"."salons" to "authenticated";

grant insert on table "public"."salons" to "authenticated";

grant references on table "public"."salons" to "authenticated";

grant select on table "public"."salons" to "authenticated";

grant trigger on table "public"."salons" to "authenticated";

grant truncate on table "public"."salons" to "authenticated";

grant update on table "public"."salons" to "authenticated";

grant delete on table "public"."salons" to "service_role";

grant insert on table "public"."salons" to "service_role";

grant references on table "public"."salons" to "service_role";

grant select on table "public"."salons" to "service_role";

grant trigger on table "public"."salons" to "service_role";

grant truncate on table "public"."salons" to "service_role";

grant update on table "public"."salons" to "service_role";

grant delete on table "public"."service_categories" to "anon";

grant insert on table "public"."service_categories" to "anon";

grant references on table "public"."service_categories" to "anon";

grant select on table "public"."service_categories" to "anon";

grant trigger on table "public"."service_categories" to "anon";

grant truncate on table "public"."service_categories" to "anon";

grant update on table "public"."service_categories" to "anon";

grant delete on table "public"."service_categories" to "authenticated";

grant insert on table "public"."service_categories" to "authenticated";

grant references on table "public"."service_categories" to "authenticated";

grant select on table "public"."service_categories" to "authenticated";

grant trigger on table "public"."service_categories" to "authenticated";

grant truncate on table "public"."service_categories" to "authenticated";

grant update on table "public"."service_categories" to "authenticated";

grant delete on table "public"."service_categories" to "service_role";

grant insert on table "public"."service_categories" to "service_role";

grant references on table "public"."service_categories" to "service_role";

grant select on table "public"."service_categories" to "service_role";

grant trigger on table "public"."service_categories" to "service_role";

grant truncate on table "public"."service_categories" to "service_role";

grant update on table "public"."service_categories" to "service_role";

grant delete on table "public"."services" to "anon";

grant insert on table "public"."services" to "anon";

grant references on table "public"."services" to "anon";

grant select on table "public"."services" to "anon";

grant trigger on table "public"."services" to "anon";

grant truncate on table "public"."services" to "anon";

grant update on table "public"."services" to "anon";

grant delete on table "public"."services" to "authenticated";

grant insert on table "public"."services" to "authenticated";

grant references on table "public"."services" to "authenticated";

grant select on table "public"."services" to "authenticated";

grant trigger on table "public"."services" to "authenticated";

grant truncate on table "public"."services" to "authenticated";

grant update on table "public"."services" to "authenticated";

grant delete on table "public"."services" to "service_role";

grant insert on table "public"."services" to "service_role";

grant references on table "public"."services" to "service_role";

grant select on table "public"."services" to "service_role";

grant trigger on table "public"."services" to "service_role";

grant truncate on table "public"."services" to "service_role";

grant update on table "public"."services" to "service_role";

grant delete on table "public"."spatial_ref_sys" to "anon";

grant insert on table "public"."spatial_ref_sys" to "anon";

grant references on table "public"."spatial_ref_sys" to "anon";

grant select on table "public"."spatial_ref_sys" to "anon";

grant trigger on table "public"."spatial_ref_sys" to "anon";

grant truncate on table "public"."spatial_ref_sys" to "anon";

grant update on table "public"."spatial_ref_sys" to "anon";

grant delete on table "public"."spatial_ref_sys" to "authenticated";

grant insert on table "public"."spatial_ref_sys" to "authenticated";

grant references on table "public"."spatial_ref_sys" to "authenticated";

grant select on table "public"."spatial_ref_sys" to "authenticated";

grant trigger on table "public"."spatial_ref_sys" to "authenticated";

grant truncate on table "public"."spatial_ref_sys" to "authenticated";

grant update on table "public"."spatial_ref_sys" to "authenticated";

grant delete on table "public"."spatial_ref_sys" to "postgres";

grant insert on table "public"."spatial_ref_sys" to "postgres";

grant references on table "public"."spatial_ref_sys" to "postgres";

grant select on table "public"."spatial_ref_sys" to "postgres";

grant trigger on table "public"."spatial_ref_sys" to "postgres";

grant truncate on table "public"."spatial_ref_sys" to "postgres";

grant update on table "public"."spatial_ref_sys" to "postgres";

grant delete on table "public"."spatial_ref_sys" to "service_role";

grant insert on table "public"."spatial_ref_sys" to "service_role";

grant references on table "public"."spatial_ref_sys" to "service_role";

grant select on table "public"."spatial_ref_sys" to "service_role";

grant trigger on table "public"."spatial_ref_sys" to "service_role";

grant truncate on table "public"."spatial_ref_sys" to "service_role";

grant update on table "public"."spatial_ref_sys" to "service_role";

grant delete on table "public"."staff_availability" to "anon";

grant insert on table "public"."staff_availability" to "anon";

grant references on table "public"."staff_availability" to "anon";

grant select on table "public"."staff_availability" to "anon";

grant trigger on table "public"."staff_availability" to "anon";

grant truncate on table "public"."staff_availability" to "anon";

grant update on table "public"."staff_availability" to "anon";

grant delete on table "public"."staff_availability" to "authenticated";

grant insert on table "public"."staff_availability" to "authenticated";

grant references on table "public"."staff_availability" to "authenticated";

grant select on table "public"."staff_availability" to "authenticated";

grant trigger on table "public"."staff_availability" to "authenticated";

grant truncate on table "public"."staff_availability" to "authenticated";

grant update on table "public"."staff_availability" to "authenticated";

grant delete on table "public"."staff_availability" to "service_role";

grant insert on table "public"."staff_availability" to "service_role";

grant references on table "public"."staff_availability" to "service_role";

grant select on table "public"."staff_availability" to "service_role";

grant trigger on table "public"."staff_availability" to "service_role";

grant truncate on table "public"."staff_availability" to "service_role";

grant update on table "public"."staff_availability" to "service_role";

grant delete on table "public"."system_config" to "anon";

grant insert on table "public"."system_config" to "anon";

grant references on table "public"."system_config" to "anon";

grant select on table "public"."system_config" to "anon";

grant trigger on table "public"."system_config" to "anon";

grant truncate on table "public"."system_config" to "anon";

grant update on table "public"."system_config" to "anon";

grant delete on table "public"."system_config" to "authenticated";

grant insert on table "public"."system_config" to "authenticated";

grant references on table "public"."system_config" to "authenticated";

grant select on table "public"."system_config" to "authenticated";

grant trigger on table "public"."system_config" to "authenticated";

grant truncate on table "public"."system_config" to "authenticated";

grant update on table "public"."system_config" to "authenticated";

grant delete on table "public"."system_config" to "service_role";

grant insert on table "public"."system_config" to "service_role";

grant references on table "public"."system_config" to "service_role";

grant select on table "public"."system_config" to "service_role";

grant trigger on table "public"."system_config" to "service_role";

grant truncate on table "public"."system_config" to "service_role";

grant update on table "public"."system_config" to "service_role";

grant delete on table "public"."token_blacklist" to "anon";

grant insert on table "public"."token_blacklist" to "anon";

grant references on table "public"."token_blacklist" to "anon";

grant select on table "public"."token_blacklist" to "anon";

grant trigger on table "public"."token_blacklist" to "anon";

grant truncate on table "public"."token_blacklist" to "anon";

grant update on table "public"."token_blacklist" to "anon";

grant delete on table "public"."token_blacklist" to "authenticated";

grant insert on table "public"."token_blacklist" to "authenticated";

grant references on table "public"."token_blacklist" to "authenticated";

grant select on table "public"."token_blacklist" to "authenticated";

grant trigger on table "public"."token_blacklist" to "authenticated";

grant truncate on table "public"."token_blacklist" to "authenticated";

grant update on table "public"."token_blacklist" to "authenticated";

grant delete on table "public"."token_blacklist" to "service_role";

grant insert on table "public"."token_blacklist" to "service_role";

grant references on table "public"."token_blacklist" to "service_role";

grant select on table "public"."token_blacklist" to "service_role";

grant trigger on table "public"."token_blacklist" to "service_role";

grant truncate on table "public"."token_blacklist" to "service_role";

grant update on table "public"."token_blacklist" to "service_role";

grant delete on table "public"."user_carts" to "anon";

grant insert on table "public"."user_carts" to "anon";

grant references on table "public"."user_carts" to "anon";

grant select on table "public"."user_carts" to "anon";

grant trigger on table "public"."user_carts" to "anon";

grant truncate on table "public"."user_carts" to "anon";

grant update on table "public"."user_carts" to "anon";

grant delete on table "public"."user_carts" to "authenticated";

grant insert on table "public"."user_carts" to "authenticated";

grant references on table "public"."user_carts" to "authenticated";

grant select on table "public"."user_carts" to "authenticated";

grant trigger on table "public"."user_carts" to "authenticated";

grant truncate on table "public"."user_carts" to "authenticated";

grant update on table "public"."user_carts" to "authenticated";

grant delete on table "public"."user_carts" to "service_role";

grant insert on table "public"."user_carts" to "service_role";

grant references on table "public"."user_carts" to "service_role";

grant select on table "public"."user_carts" to "service_role";

grant trigger on table "public"."user_carts" to "service_role";

grant truncate on table "public"."user_carts" to "service_role";

grant update on table "public"."user_carts" to "service_role";

grant delete on table "public"."vendor_join_requests" to "anon";

grant insert on table "public"."vendor_join_requests" to "anon";

grant references on table "public"."vendor_join_requests" to "anon";

grant select on table "public"."vendor_join_requests" to "anon";

grant trigger on table "public"."vendor_join_requests" to "anon";

grant truncate on table "public"."vendor_join_requests" to "anon";

grant update on table "public"."vendor_join_requests" to "anon";

grant delete on table "public"."vendor_join_requests" to "authenticated";

grant insert on table "public"."vendor_join_requests" to "authenticated";

grant references on table "public"."vendor_join_requests" to "authenticated";

grant select on table "public"."vendor_join_requests" to "authenticated";

grant trigger on table "public"."vendor_join_requests" to "authenticated";

grant truncate on table "public"."vendor_join_requests" to "authenticated";

grant update on table "public"."vendor_join_requests" to "authenticated";

grant delete on table "public"."vendor_join_requests" to "service_role";

grant insert on table "public"."vendor_join_requests" to "service_role";

grant references on table "public"."vendor_join_requests" to "service_role";

grant select on table "public"."vendor_join_requests" to "service_role";

grant trigger on table "public"."vendor_join_requests" to "service_role";

grant truncate on table "public"."vendor_join_requests" to "service_role";

grant update on table "public"."vendor_join_requests" to "service_role";

grant delete on table "public"."vendor_payments" to "anon";

grant insert on table "public"."vendor_payments" to "anon";

grant references on table "public"."vendor_payments" to "anon";

grant select on table "public"."vendor_payments" to "anon";

grant trigger on table "public"."vendor_payments" to "anon";

grant truncate on table "public"."vendor_payments" to "anon";

grant update on table "public"."vendor_payments" to "anon";

grant delete on table "public"."vendor_payments" to "authenticated";

grant insert on table "public"."vendor_payments" to "authenticated";

grant references on table "public"."vendor_payments" to "authenticated";

grant select on table "public"."vendor_payments" to "authenticated";

grant trigger on table "public"."vendor_payments" to "authenticated";

grant truncate on table "public"."vendor_payments" to "authenticated";

grant update on table "public"."vendor_payments" to "authenticated";

grant delete on table "public"."vendor_payments" to "service_role";

grant insert on table "public"."vendor_payments" to "service_role";

grant references on table "public"."vendor_payments" to "service_role";

grant select on table "public"."vendor_payments" to "service_role";

grant trigger on table "public"."vendor_payments" to "service_role";

grant truncate on table "public"."vendor_payments" to "service_role";

grant update on table "public"."vendor_payments" to "service_role";


  create policy "Customers can cancel own bookings"
  on "public"."bookings"
  as permissive
  for update
  to public
using ((customer_id = auth.uid()));



  create policy "Customers can create bookings"
  on "public"."bookings"
  as permissive
  for insert
  to public
with check ((customer_id = auth.uid()));



  create policy "Customers can view own bookings"
  on "public"."bookings"
  as permissive
  for select
  to public
using ((customer_id = auth.uid()));



  create policy "Vendors can update salon bookings"
  on "public"."bookings"
  as permissive
  for update
  to public
using ((EXISTS ( SELECT 1
   FROM public.salons
  WHERE ((salons.id = bookings.salon_id) AND (salons.vendor_id = auth.uid())))));



  create policy "Vendors can view salon bookings"
  on "public"."bookings"
  as permissive
  for select
  to public
using ((EXISTS ( SELECT 1
   FROM public.salons
  WHERE ((salons.id = bookings.salon_id) AND (salons.vendor_id = auth.uid())))));



  create policy "Users can delete own cart items"
  on "public"."cart_items"
  as permissive
  for delete
  to public
using ((auth.uid() = customer_id));



  create policy "Users can insert own cart items"
  on "public"."cart_items"
  as permissive
  for insert
  to public
with check ((auth.uid() = customer_id));



  create policy "Users can update own cart items"
  on "public"."cart_items"
  as permissive
  for update
  to public
using ((auth.uid() = customer_id))
with check ((auth.uid() = customer_id));



  create policy "Users can view own cart items"
  on "public"."cart_items"
  as permissive
  for select
  to public
using ((auth.uid() = customer_id));



  create policy "Users can create own favorites"
  on "public"."favorites"
  as permissive
  for insert
  to public
with check ((auth.uid() = user_id));



  create policy "Users can delete own favorites"
  on "public"."favorites"
  as permissive
  for delete
  to public
using ((auth.uid() = user_id));



  create policy "Users can view own favorites"
  on "public"."favorites"
  as permissive
  for select
  to public
using ((auth.uid() = user_id));



  create policy "Admins can view all profiles"
  on "public"."profiles"
  as permissive
  for all
  to public
using ((EXISTS ( SELECT 1
   FROM public.profiles profiles_1
  WHERE ((profiles_1.id = auth.uid()) AND (profiles_1.role = 'admin'::public.user_role)))));



  create policy "Admins can manage all salons"
  on "public"."salons"
  as permissive
  for all
  to public
using ((EXISTS ( SELECT 1
   FROM public.profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::public.user_role)))));



  create policy "Public can view active salons"
  on "public"."salons"
  as permissive
  for select
  to public
using ((is_active = true));



  create policy "RMs can view salons they added"
  on "public"."salons"
  as permissive
  for select
  to public
using ((rm_id = auth.uid()));



  create policy "Vendors can manage own salons"
  on "public"."salons"
  as permissive
  for all
  to public
using ((vendor_id = auth.uid()));



  create policy "Public can view active services"
  on "public"."services"
  as permissive
  for select
  to public
using (((is_active = true) AND (EXISTS ( SELECT 1
   FROM public.salons
  WHERE ((salons.id = services.salon_id) AND (salons.is_active = true))))));



  create policy "Service role can manage all services"
  on "public"."services"
  as permissive
  for all
  to service_role
using (true)
with check (true);



  create policy "Vendors can manage own salon services"
  on "public"."services"
  as permissive
  for all
  to public
using ((EXISTS ( SELECT 1
   FROM public.salons
  WHERE ((salons.id = services.salon_id) AND (salons.vendor_id = auth.uid())))));



  create policy "Admins can manage config"
  on "public"."system_config"
  as permissive
  for all
  to public
using ((EXISTS ( SELECT 1
   FROM public.profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::public.user_role)))));



  create policy "Public can view active config"
  on "public"."system_config"
  as permissive
  for select
  to public
using ((is_active = true));



  create policy "Users can delete their own cart"
  on "public"."user_carts"
  as permissive
  for delete
  to public
using ((auth.uid() = user_id));



  create policy "Users can insert their own cart"
  on "public"."user_carts"
  as permissive
  for insert
  to public
with check ((auth.uid() = user_id));



  create policy "Users can update their own cart"
  on "public"."user_carts"
  as permissive
  for update
  to public
using ((auth.uid() = user_id));



  create policy "Users can view their own cart"
  on "public"."user_carts"
  as permissive
  for select
  to public
using ((auth.uid() = user_id));



  create policy "Admins can update requests"
  on "public"."vendor_join_requests"
  as permissive
  for update
  to authenticated
using ((EXISTS ( SELECT 1
   FROM public.profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::public.user_role)))))
with check ((EXISTS ( SELECT 1
   FROM public.profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::public.user_role)))));



  create policy "Admins can view all requests"
  on "public"."vendor_join_requests"
  as permissive
  for select
  to authenticated
using ((EXISTS ( SELECT 1
   FROM public.profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::public.user_role)))));



  create policy "Enable realtime for anon"
  on "public"."vendor_join_requests"
  as permissive
  for select
  to anon
using (true);



  create policy "RMs can insert own requests"
  on "public"."vendor_join_requests"
  as permissive
  for insert
  to authenticated
with check (((auth.uid() IS NOT NULL) AND (EXISTS ( SELECT 1
   FROM public.rm_profiles
  WHERE ((rm_profiles.id = auth.uid()) AND (rm_profiles.is_active = true)))) AND (rm_id = auth.uid())));



  create policy "RMs can view own requests"
  on "public"."vendor_join_requests"
  as permissive
  for select
  to authenticated
using (((auth.uid() = rm_id) OR (EXISTS ( SELECT 1
   FROM public.profiles
  WHERE ((profiles.id = auth.uid()) AND (profiles.role = 'admin'::public.user_role))))));



  create policy "Service role can insert vendor requests"
  on "public"."vendor_join_requests"
  as permissive
  for all
  to service_role
using (true)
with check (true);



  create policy "Service role has full access"
  on "public"."vendor_join_requests"
  as permissive
  for all
  to service_role
using (true)
with check (true);


CREATE TRIGGER set_booking_number BEFORE INSERT ON public.bookings FOR EACH ROW EXECUTE FUNCTION public.generate_booking_number();

CREATE TRIGGER update_bookings_updated_at BEFORE UPDATE ON public.bookings FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trigger_cart_items_updated_at BEFORE UPDATE ON public.cart_items FOR EACH ROW EXECUTE FUNCTION public.update_cart_items_updated_at();

CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_salon_rating_trigger AFTER INSERT OR UPDATE ON public.reviews FOR EACH ROW EXECUTE FUNCTION public.update_salon_rating();

CREATE TRIGGER update_salons_updated_at BEFORE UPDATE ON public.salons FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_services_updated_at BEFORE UPDATE ON public.services FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_system_config_updated_at BEFORE UPDATE ON public.system_config FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER trigger_update_user_carts_updated_at BEFORE UPDATE ON public.user_carts FOR EACH ROW EXECUTE FUNCTION public.update_user_carts_updated_at();

CREATE TRIGGER on_auth_user_email_verified AFTER UPDATE ON auth.users FOR EACH ROW WHEN (((old.email_confirmed_at IS NULL) AND (new.email_confirmed_at IS NOT NULL))) EXECUTE FUNCTION public.sync_email_verification();


  create policy "Allow anyone to upload salon images"
  on "storage"."objects"
  as permissive
  for insert
  to public
with check ((bucket_id = 'salon-images'::text));



  create policy "Allow public to view salon images"
  on "storage"."objects"
  as permissive
  for select
  to public
using ((bucket_id = 'salon-images'::text));



  create policy "Allow users to delete their own uploads"
  on "storage"."objects"
  as permissive
  for delete
  to authenticated
using (((bucket_id = 'salon-images'::text) AND (auth.uid() = owner)));



  create policy "Allow users to update their uploads"
  on "storage"."objects"
  as permissive
  for update
  to authenticated
using (((bucket_id = 'salon-images'::text) AND (auth.uid() = owner)));



  create policy "Public salon images"
  on "storage"."objects"
  as permissive
  for select
  to public
using ((bucket_id = 'salon-images'::text));



  create policy "Users upload own receipts"
  on "storage"."objects"
  as permissive
  for insert
  to public
with check (((bucket_id = 'receipts'::text) AND ((auth.uid())::text = (storage.foldername(name))[1])));



