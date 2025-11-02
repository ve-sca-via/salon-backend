"""
Quick Email Configuration Check
"""
import os
from pathlib import Path

print("\n" + "="*60)
print("  EMAIL CONFIGURATION STATUS")
print("="*60 + "\n")

# Check .env file
env_path = Path(".env")
if not env_path.exists():
    print("❌ .env file not found!")
    exit(1)

with open(env_path, 'r') as f:
    content = f.read()

# Parse SMTP settings
smtp_settings = {}
for line in content.split('\n'):
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"')
        
        if key.startswith('SMTP_') or key == 'EMAIL_FROM':
            smtp_settings[key] = value

# Display settings
print("Current SMTP Settings:")
print("-" * 60)

for key, value in smtp_settings.items():
    if 'PASSWORD' in key:
        if value and value != "your-app-password":
            print(f"✓ {key:<20} : {'*' * 16} (SET)")
        else:
            print(f"✗ {key:<20} : NOT CONFIGURED")
    else:
        if value and not value.startswith('your-'):
            print(f"✓ {key:<20} : {value}")
        else:
            print(f"✗ {key:<20} : {value} (DEFAULT/NOT SET)")

print("\n" + "="*60)

# Check if configured
is_configured = (
    smtp_settings.get('SMTP_USER', '').strip() not in ['', 'your-email@gmail.com'] and
    smtp_settings.get('SMTP_PASSWORD', '').strip() not in ['', 'your-app-password']
)

if is_configured:
    print("✅ EMAIL IS CONFIGURED - Emails will be sent")
else:
    print("❌ EMAIL IS NOT CONFIGURED - Emails will FAIL")
    print("\n📝 To Configure Email:")
    print("\n1. For Gmail (Recommended for testing):")
    print("   a) Go to: https://myaccount.google.com/apppasswords")
    print("   b) Generate App Password for 'Mail'")
    print("   c) Update .env:")
    print('      SMTP_USER="your-gmail@gmail.com"')
    print('      SMTP_PASSWORD="your-16-char-app-password"')
    
    print("\n2. For SendGrid (Production):")
    print("   a) Sign up at: https://sendgrid.com")
    print("   b) Get API key")
    print("   c) Update .env:")
    print('      SMTP_HOST="smtp.sendgrid.net"')
    print('      SMTP_PORT=587')
    print('      SMTP_USER="apikey"')
    print('      SMTP_PASSWORD="your-sendgrid-api-key"')
    
    print("\n3. For AWS SES (Production):")
    print("   a) Configure AWS SES")
    print("   b) Get SMTP credentials")
    print("   c) Update .env with SES settings")

print("\n" + "="*60 + "\n")
