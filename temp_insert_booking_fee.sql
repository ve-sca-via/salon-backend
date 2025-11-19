-- Insert booking_fee_percentage config
INSERT INTO system_config (config_key, config_value, config_type, description, is_active) 
VALUES ('booking_fee_percentage', '10', 'number', 'Booking convenience fee percentage (default 10%)', true) 
ON CONFLICT (config_key) DO UPDATE 
SET config_value = '10', config_type = 'number', description = 'Booking convenience fee percentage (default 10%)', is_active = true;

-- Verify
SELECT config_key, config_value, config_type FROM system_config WHERE config_key = 'booking_fee_percentage';
