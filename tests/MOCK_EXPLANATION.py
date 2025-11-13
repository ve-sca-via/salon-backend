"""
SIMPLE DEMONSTRATION: How Mock Services Work

This shows you the CONCEPT without needing to install dependencies.
"""

print("=" * 80)
print("MOCK SERVICES EXPLANATION")
print("=" * 80)

# ==========================================
# BEFORE: Your services were HARDCODED
# ==========================================

print("\n❌ BEFORE (Hardcoded - Can't Mock):")
print("-" * 80)
print("""
# email.py
class EmailService:
    def send_email(...):
        smtp.send(...)  # ❌ Always sends real email!

# At bottom of file
email_service = EmailService()  # ❌ Always real service!

# In your booking_service.py
from app.services.email import email_service

email_service.send_confirmation(...)  # ❌ ALWAYS sends real email!
                                      # ❌ Can't test without SMTP server!
""")

# ==========================================
# AFTER: Factory Pattern (Like Database!)
# ==========================================

print("\n✅ AFTER (Factory Pattern - Mockable!):")
print("-" * 80)
print("""
# email.py

class MockEmailService:
    def __init__(self):
        self.sent_emails = []  # Store emails here!
    
    def send_email(...):
        self.sent_emails.append({...})  # ❌ Just store, don't send!
        return True  # ✅ Pretend it worked!

class EmailService:
    def send_email(...):
        smtp.send(...)  # Real email sending

def get_email_service():  # ← FACTORY FUNCTION (like get_db()!)
    if ENVIRONMENT == "test":
        return MockEmailService()  # ✅ Return mock in tests!
    return EmailService()  # Real service in production

# At bottom
email_service = get_email_service()  # ← Uses factory!

# In booking_service.py
from app.services.email import email_service  # ← Same import!

# But NOW...
# - In production: email_service = EmailService() (real)
# - In tests: email_service = MockEmailService() (fake)
""")

# ==========================================
# HOW TO USE IN TESTS
# ==========================================

print("\n🧪 HOW TO USE IN TESTS:")
print("-" * 80)
print("""
# test_booking.py
import os
os.environ["ENVIRONMENT"] = "test"  # ← Set BEFORE importing!

from app.services.email import email_service  # ← Gets MockEmailService!
from app.services.booking_service import BookingService

def test_create_booking():
    # Clear previous emails
    email_service.sent_emails = []
    
    # Create booking (which sends email internally)
    service = BookingService()
    booking = await service.create_booking(...)
    
    # ✅ Check email was "sent" (actually just stored!)
    assert len(email_service.sent_emails) == 1
    assert email_service.sent_emails[0]["to_email"] == "customer@example.com"
    assert "confirmation" in email_service.sent_emails[0]["subject"].lower()
    
    # ✅ No real email was sent!
    # ✅ No SMTP server needed!
    # ✅ Test runs in milliseconds!
""")

# ==========================================
# WHAT YOU DID
# ==========================================

print("\n📦 WHAT WE JUST DID:")
print("-" * 80)
print("""
1. ✅ Created MockEmailService class
   - Has same methods as EmailService
   - But stores emails instead of sending
   - Has .sent_emails list for verification

2. ✅ Created get_email_service() factory function
   - Returns MockEmailService if ENVIRONMENT=test
   - Returns real EmailService otherwise

3. ✅ Changed: email_service = EmailService()
   To:       email_service = get_email_service()

4. ✅ Did SAME for geocoding:
   - MockGeocodingService (returns fake coordinates)
   - get_geocoding_service() factory
   - geocoding_service = get_geocoding_service()

NO NEW LIBRARIES INSTALLED!
Just reorganized existing code!
""")

# ==========================================
# COMPARISON TO DATABASE
# ==========================================

print("\n🔍 IT'S THE SAME AS DATABASE!")
print("-" * 80)
print("""
DATABASE:                          EMAIL:
---------                          ------
MockSupabaseClient                 MockEmailService
  .table() -> fake data              .send_email() -> store, don't send

get_db()                           get_email_service()
  if test: return Mock               if test: return Mock
  else: return Real                  else: return Real

db = get_db()                      email_service = get_email_service()

YOU ALREADY UNDERSTAND THIS FROM DATABASE!
IT'S THE EXACT SAME PATTERN! 🎯
""")

# ==========================================
# FINAL SUMMARY
# ==========================================

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
✅ What Changed: 
   - email.py: Added MockEmailService + get_email_service()
   - geocoding.py: Added MockGeocodingService + get_geocoding_service()
   - Changed singletons to use factory functions

✅ What Stayed Same:
   - All your business logic code
   - All imports still work
   - No breaking changes

✅ What You Can Do Now:
   1. Set ENVIRONMENT=test before importing
   2. All email/geocoding calls use mocks
   3. Test without real SMTP or geocoding API
   4. Verify emails in mock.sent_emails list
   5. Check fake coordinates returned

✅ New Libraries Needed: ZERO! 
   We just reorganized your existing code!

✅ Pattern Used: Factory Pattern (same as database!)
""")

print("=" * 80)
print("YOU NOW HAVE FULL MOCKING CAPABILITY! 🎉")
print("=" * 80)
