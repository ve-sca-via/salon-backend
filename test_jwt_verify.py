"""
Quick test to verify JWT signature validation is working
"""
from jose import jwt, JWTError
from app.core.config import settings

# Create a valid token
payload = {"sub": "test-user", "email": "test@example.com", "role": "customer"}
valid_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

print("1. Testing VALID token decode:")
try:
    decoded = jwt.decode(valid_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    print(f"   ✓ SUCCESS: {decoded}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")

# Tamper with it
print("\n2. Testing TAMPERED token (changed payload, wrong signature):")
tampered_payload = {"sub": "test-user", "email": "test@example.com", "role": "admin"}  # Changed role!
tampered_token = jwt.encode(tampered_payload, "wrong-secret", algorithm="HS256")  # Wrong secret!

try:
    decoded = jwt.decode(tampered_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    print(f"   ✗ CRITICAL: Tampered token was accepted! {decoded}")
except JWTError as e:
    print(f"   ✓ SUCCESS: Tampered token rejected - {type(e).__name__}: {e}")

print("\n3. Testing if endpoint actually calls verify_token:")
print("   Run the test script to check...")
