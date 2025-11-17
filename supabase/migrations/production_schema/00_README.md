# Production Schema Migration Guide

This directory contains production-ready SQL files organized by table/feature.

## Execution Order

Run these files in order:

1. `01_enums.sql` - Create all enum types
2. `02_extensions.sql` - Enable required PostgreSQL extensions
3. `03_profiles.sql` - User profiles table
4. `04_salons.sql` - Salons table with proper constraints
5. `05_services.sql` - Services and categories
6. `06_bookings.sql` - Bookings with payment tracking
7. `07_payments.sql` - Payment tables (booking + vendor registration)
8. `08_reviews.sql` - Reviews table
9. `09_cart.sql` - Shopping cart
10. `10_favorites.sql` - User favorites
11. `11_staff.sql` - Salon staff management
12. `12_rm_system.sql` - Relationship Manager system
13. `13_phone_otp.sql` - Phone OTP authentication
14. `14_audit_logs.sql` - Audit trail system
15. `15_functions.sql` - Helper functions
16. `16_triggers.sql` - Automated triggers
17. `17_rls_policies.sql` - Row Level Security policies
18. `18_indexes.sql` - Performance indexes
19. `19_views.sql` - Helpful views
20. `20_grants.sql` - Permissions

## How to Apply

### Option 1: Via Supabase Dashboard
1. Go to SQL Editor
2. Copy-paste each file in order
3. Execute

### Option 2: Via CLI (All at once)
```bash
cat production_schema/*.sql | supabase db push
```

### Option 3: One by one
```bash
supabase db push production_schema/01_enums.sql
supabase db push production_schema/02_extensions.sql
# ... etc
```

## Features Included

✅ Indian compliance (DPDP Act 2023, IT Act 2000, PCI-DSS)
✅ Security (RLS on all tables, revoked anon access)
✅ Audit logging (track all changes)
✅ Soft deletes (deleted_at pattern)
✅ Phone OTP authentication
✅ Performance indexes (15+ critical indexes)
✅ Data validation (phone, email, GST, pincode)
✅ Payment immutability (Razorpay IDs can't change)
✅ Historical data protection (RESTRICT deletes)
