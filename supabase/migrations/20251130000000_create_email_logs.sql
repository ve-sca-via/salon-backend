-- Create email_logs table for tracking all email sending
-- Migration: 20251130000000_create_email_logs.sql

-- Create email_logs table
CREATE TABLE IF NOT EXISTS email_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Email details
    recipient_email TEXT NOT NULL,
    email_type TEXT NOT NULL, -- vendor_approval, booking_confirmation, payment_receipt, etc.
    subject TEXT NOT NULL,
    
    -- Status tracking
    status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'pending')),
    error_message TEXT,
    
    -- Metadata
    related_entity_type TEXT, -- booking, salon, payment, career_application
    related_entity_id UUID, -- ID of the related booking/salon/payment
    
    -- Context data (for resending if needed)
    email_data JSONB, -- Store template variables used
    
    -- Retry tracking
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMPTZ,
    
    -- Timestamps
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX idx_email_logs_recipient ON email_logs(recipient_email);
CREATE INDEX idx_email_logs_type ON email_logs(email_type);
CREATE INDEX idx_email_logs_status ON email_logs(status);
CREATE INDEX idx_email_logs_created_at ON email_logs(created_at DESC);
CREATE INDEX idx_email_logs_related_entity ON email_logs(related_entity_type, related_entity_id);
CREATE INDEX idx_email_logs_failed_retry ON email_logs(status, next_retry_at) WHERE status = 'failed';

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_email_logs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER email_logs_updated_at
    BEFORE UPDATE ON email_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_email_logs_updated_at();

-- Add comment on table
COMMENT ON TABLE email_logs IS 'Tracks all emails sent by the system for audit trail and retry mechanism';
COMMENT ON COLUMN email_logs.email_type IS 'Type of email: vendor_approval, vendor_rejection, booking_confirmation, booking_cancellation, payment_receipt, welcome_vendor, career_application, rm_notification';
COMMENT ON COLUMN email_logs.status IS 'Current status: sent (successfully sent), failed (delivery failed), pending (queued for sending)';
COMMENT ON COLUMN email_logs.email_data IS 'JSON blob containing template variables for email recreation/resending';
COMMENT ON COLUMN email_logs.retry_count IS 'Number of retry attempts made';
COMMENT ON COLUMN email_logs.next_retry_at IS 'Timestamp for next retry attempt (for failed emails)';
