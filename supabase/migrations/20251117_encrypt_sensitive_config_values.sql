-- Migration scaffold: Add support for encrypting sensitive configuration values
-- This migration demonstrates adding a flag to indicate encrypted values and
-- a placeholder for performing in-place encryption. Actual encryption must be
-- performed by an offline script or application that has access to the
-- `DB_ENCRYPTION_KEY` (the application should not store the key in the DB).

-- NOTE: Do NOT store encryption keys in the database. Use a secrets manager.

ALTER TABLE IF EXISTS system_config
  ADD COLUMN IF NOT EXISTS is_encrypted boolean DEFAULT false;

-- Example: after running the above migration, run a script that reads rows
-- where config_key IN ('razorpay_key_secret','smtp_password',...) and
-- replaces `config_value` with the encrypted value using your encryption key
-- and then sets is_encrypted=true for those rows.

-- The actual encryption must be done outside SQL since Fernet keys and
-- encryption logic live in application code. This file is a scaffold to
-- help coordinate the change and ensure the `is_encrypted` marker exists.
