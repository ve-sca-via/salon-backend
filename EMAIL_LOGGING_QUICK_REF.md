# Email Logging - Quick Reference

## Overview
All emails sent by the system are now automatically logged to the `email_logs` database table.

## What's Logged Automatically

Every time an email is sent, the following information is recorded:
- ✅ Recipient email address
- ✅ Email type (vendor_approval, booking_confirmation, etc.)
- ✅ Subject line
- ✅ Status (sent/failed/pending)
- ✅ Related entity (booking_id, salon_id, payment_id, etc.)
- ✅ Email data (template variables for resending)
- ✅ Timestamp

## Quick Queries

### View recent emails
```sql
SELECT 
    recipient_email,
    email_type,
    subject,
    status,
    sent_at
FROM email_logs
ORDER BY created_at DESC
LIMIT 50;
```

### Check failed emails
```sql
SELECT * FROM email_logs 
WHERE status = 'failed'
ORDER BY created_at DESC;
```

### Get emails for a specific booking
```sql
SELECT * FROM email_logs 
WHERE related_entity_type = 'booking' 
  AND related_entity_id = 'your-booking-id';
```

### Email delivery statistics (last 7 days)
```sql
SELECT 
    email_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM email_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY email_type;
```

## Email Types

| Type | When Sent |
|------|-----------|
| `vendor_approval` | Admin approves salon registration |
| `vendor_rejection` | Admin rejects salon (sent to RM) |
| `rm_notification` | RM notified about approved salon |
| `booking_confirmation` | Customer books appointment |
| `booking_cancellation` | Booking is cancelled |
| `payment_receipt` | Payment processed |
| `welcome_vendor` | Vendor completes registration |
| `career_application_confirmation` | Job application received |

## Retry Mechanism

Failed emails automatically retry with exponential backoff:
- **1st retry**: After 5 minutes
- **2nd retry**: After 15 minutes  
- **3rd retry**: After 60 minutes
- **Max**: 3 attempts total

## Usage in Code

No changes needed! Logging happens automatically:

```python
# This already logs the email automatically
await email_service.send_booking_confirmation_email(
    to_email="customer@example.com",
    customer_name="John Doe",
    salon_name="Beauty Salon",
    services=[...],
    booking_date="2025-12-01",
    booking_time="10:00 AM",
    staff_name="Jane Stylist",
    total_amount=2000.0,
    booking_id="booking-123"  # Gets logged
)
```

## Troubleshooting

### Customer didn't receive email?
```sql
SELECT * FROM email_logs 
WHERE recipient_email = 'customer@example.com'
ORDER BY created_at DESC
LIMIT 10;
```

### Why did an email fail?
```sql
SELECT 
    email_type,
    error_message,
    retry_count,
    next_retry_at
FROM email_logs 
WHERE id = 'email-log-id';
```

### Resend a failed email?
```sql
-- Get the email data
SELECT email_data FROM email_logs WHERE id = 'email-log-id';

-- Use the data to call the appropriate email service method
```

## Files

- **Migration**: `supabase/migrations/20251130000000_create_email_logs.sql`
- **Logger Service**: `app/services/email_logger.py`
- **Email Service**: `app/services/email.py`
- **Documentation**: `docs/EMAIL_LOGGING_SYSTEM.md`

## Benefits

✅ **Track all emails** - Never lose track of what was sent  
✅ **Debug issues** - See exactly what happened  
✅ **Retry failures** - Automatic retry with backoff  
✅ **Audit trail** - Complete history for compliance  
✅ **Resend emails** - All data stored for resending  
✅ **Monitor health** - Track delivery rates and failures  

## Next Steps

1. **Apply migration**: Run the SQL migration to create the table
2. **Test**: Send a test email and verify it appears in `email_logs`
3. **Monitor**: Check the table regularly for failed emails
4. **Optional**: Build admin UI to view logs

---

**No code changes required!** All your existing email sending code now automatically logs to the database. 🎉
