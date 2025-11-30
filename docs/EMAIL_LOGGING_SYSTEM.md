# Email Logging System

## Overview
The email logging system tracks all emails sent by the application, providing an audit trail, retry mechanism, and debugging capabilities.

## Database Schema

### `email_logs` Table
```sql
CREATE TABLE email_logs (
    id UUID PRIMARY KEY,
    recipient_email TEXT NOT NULL,
    email_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'pending')),
    error_message TEXT,
    related_entity_type TEXT,
    related_entity_id UUID,
    email_data JSONB,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Email Types

| Type | Description | Related Entity |
|------|-------------|----------------|
| `vendor_approval` | Vendor approval email with registration link | salon |
| `vendor_rejection` | Vendor rejection notification to RM | vendor_request |
| `rm_notification` | RM notification about salon approval | salon |
| `booking_confirmation` | Booking confirmation to customer | booking |
| `booking_confirmation_customer` | Customer booking confirmation | booking |
| `booking_notification_vendor` | Vendor booking notification | booking |
| `booking_cancellation` | Booking cancellation email | booking |
| `payment_receipt` | Payment receipt email | payment |
| `welcome_vendor` | Welcome email to new vendor | salon |
| `career_application_confirmation` | Career application confirmation | career_application |

## Usage

### 1. Email Service Integration

The `EmailService` class automatically logs all email attempts:

```python
from app.services.email import email_service

# Send email (logging happens automatically)
success = await email_service.send_vendor_approval_email(
    to_email="vendor@example.com",
    owner_name="John Doe",
    salon_name="Beauty Salon",
    registration_token="token123",
    registration_fee=5000.0,
    salon_id="salon-uuid-123"  # For logging
)
```

### 2. Email Logger Service

Direct access to email logging:

```python
from app.services.email_logger import EmailLogger
from app.core.database import get_db

db = get_db()
email_logger = EmailLogger(db)

# Log email attempt
log_id = await email_logger.log_email_attempt(
    recipient_email="user@example.com",
    email_type="booking_confirmation",
    subject="Booking Confirmed",
    status="sent",
    related_entity_type="booking",
    related_entity_id="booking-uuid-123",
    email_data={
        "customer_name": "Jane Doe",
        "salon_name": "Beauty Salon",
        "booking_date": "2025-12-01"
    }
)

# Update email status
await email_logger.update_email_status(
    log_id=log_id,
    status="failed",
    error_message="SMTP connection timeout"
)

# Get failed emails for retry
failed_emails = await email_logger.get_failed_emails_for_retry()

# Get email logs for a specific entity
logs = await email_logger.get_email_logs_by_entity(
    entity_type="booking",
    entity_id="booking-uuid-123"
)
```

## Email Status Lifecycle

1. **pending** - Email queued for sending
2. **sent** - Email successfully delivered
3. **failed** - Email delivery failed (will retry if retry_count < max_retries)

## Retry Mechanism

Failed emails are automatically retried with exponential backoff:

- **1st retry**: After 5 minutes
- **2nd retry**: After 15 minutes
- **3rd retry**: After 60 minutes
- **Max retries**: 3 attempts

### Retry Process

```python
# Get emails ready for retry
failed_emails = await email_logger.get_failed_emails_for_retry()

for email in failed_emails:
    # Attempt to resend
    success = await resend_email(email)
    
    if success:
        await email_logger.update_email_status(email['id'], 'sent')
    else:
        await email_logger.increment_retry_count(email['id'])
```

## Database Queries

### Get all emails for a booking
```sql
SELECT * FROM email_logs 
WHERE related_entity_type = 'booking' 
  AND related_entity_id = 'booking-uuid-123'
ORDER BY created_at DESC;
```

### Get failed emails
```sql
SELECT * FROM email_logs 
WHERE status = 'failed' 
  AND retry_count < max_retries
  AND next_retry_at <= NOW()
ORDER BY next_retry_at ASC;
```

### Email delivery statistics
```sql
SELECT 
    email_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
FROM email_logs
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY email_type;
```

### Recent email activity
```sql
SELECT 
    recipient_email,
    email_type,
    subject,
    status,
    error_message,
    sent_at,
    created_at
FROM email_logs
ORDER BY created_at DESC
LIMIT 100;
```

## Email Data Storage

The `email_data` JSONB field stores template variables for email recreation:

```json
{
  "customer_name": "Jane Doe",
  "salon_name": "Beauty Salon",
  "booking_date": "2025-12-01",
  "booking_time": "10:00 AM",
  "total_amount": 2000.0
}
```

This allows:
- Email resending with exact same data
- Debugging email content issues
- Audit trail of what was sent

## Monitoring & Alerts

### Check for stuck emails
```sql
SELECT COUNT(*) FROM email_logs 
WHERE status = 'pending' 
  AND created_at < NOW() - INTERVAL '1 hour';
```

### Check email delivery rate
```sql
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE status = 'sent') as sent,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'sent') / COUNT(*), 2) as success_rate
FROM email_logs
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;
```

## Migration

Apply the migration:
```bash
# Using Supabase CLI
supabase db push

# Or manually apply
psql -h your-host -U postgres -d your-db -f supabase/migrations/20251130000000_create_email_logs.sql
```

## Benefits

1. **Audit Trail**: Complete history of all emails sent
2. **Debugging**: See exactly what was sent and when
3. **Retry Mechanism**: Automatic retry for failed emails
4. **Monitoring**: Track email delivery rates and failures
5. **Resend Capability**: Resend emails with stored data
6. **Compliance**: Meet regulatory requirements for communication tracking

## Example API Endpoint (Future)

```python
@router.get("/api/admin/email-logs")
async def get_email_logs(
    email_type: Optional[str] = None,
    status: Optional[str] = None,
    recipient: Optional[str] = None,
    limit: int = 100
):
    """Get email logs with filters"""
    query = db.table("email_logs").select("*")
    
    if email_type:
        query = query.eq("email_type", email_type)
    if status:
        query = query.eq("status", status)
    if recipient:
        query = query.eq("recipient_email", recipient)
    
    response = query.order("created_at", desc=True).limit(limit).execute()
    return response.data
```

## Notes

- Email logging happens automatically when using `EmailService`
- All email methods now accept optional entity IDs for logging
- Logs are stored even in dev mode (EMAIL_ENABLED=False)
- Failed emails can be retried manually or automatically
- Email data is stored in JSONB for flexibility
