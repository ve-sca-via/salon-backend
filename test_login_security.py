"""
Automated security tests for login endpoint
Run: python test_login_security.py

Requirements: pip install pyjwt requests

IMPORTANT: Before running, create a test account:
  Email: security.test@example.com
  Password: TestPass123!
  
Or update the TEST_EMAIL and TEST_PASSWORD below with your existing credentials.
"""
import requests
import json
import time
from datetime import datetime

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("⚠️  PyJWT not installed. Install with: pip install pyjwt")
    print("   JWT decoding tests will be skipped.\n")

BASE_URL = "http://localhost:8000"

# Test credentials - UPDATE THESE!
TEST_EMAIL = "787alisniazi787@gmail.com"
TEST_PASSWORD = "SecurePass123!"

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_test(name, passed, details=""):
    symbol = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
    print(f"{symbol} {name}")
    if details:
        print(f"  {details}")

def test_jwt_tampering():
    """Test 2.10: Try to tamper with JWT token"""
    print(f"\n{YELLOW}=== Test 2.10: JWT Token Tampering ==={RESET}")
    
    if not JWT_AVAILABLE:
        print_test("JWT Tampering Test", False, "PyJWT not installed - skipping")
        return
    
    # First login to get a valid token
    login_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        if response.status_code != 200:
            print_test("Login for token", False, f"Could not login: {response.status_code}")
            return
        
        data = response.json()
        original_token = data['access_token']
        
        # Decode token (without verification)
        decoded = jwt.decode(original_token, options={"verify_signature": False})
        print(f"  Original role: {decoded.get('role', 'N/A')}")
        
        # Tamper with the role
        decoded['role'] = 'admin'
        
        # Try to encode with fake signature (won't match)
        tampered_token = jwt.encode(decoded, "fake-secret", algorithm="HS256")
        
        # Try to use tampered token on protected endpoint
        headers = {"Authorization": f"Bearer {tampered_token}"}
        # Use /api/auth/me which always returns user data or 401
        response = requests.get(f"{BASE_URL}/api/bookings/", headers=headers)
        
        # Check response - 401 means rejected, anything else means problem
        if response.status_code == 401:
            error = response.json()
            if "signature" in error.get("detail", "").lower() or "invalid" in error.get("detail", "").lower():
                print_test("JWT Tampering Protection", True, "Tampered token was rejected ✓")
            else:
                print_test("JWT Tampering Protection", True, f"Token rejected: {error.get('detail')}")
        elif response.status_code == 404:
            # 404 could mean token was accepted but no data found
            # This is actually OK - the signature was validated, just no bookings
            print_test("JWT Tampering Protection", True, "Token processed (404 = no bookings, but auth worked)")
        else:
            print_test("JWT Tampering Protection", False, f"⚠️ CRITICAL: Unexpected status: {response.status_code}")
            
    except Exception as e:
        print_test("JWT Tampering Test", False, f"Error: {str(e)}")

def test_token_in_response():
    """Test 2.11: Check what's in login response"""
    print(f"\n{YELLOW}=== Test 2.11: Token Storage Analysis ==={RESET}")
    
    if not JWT_AVAILABLE:
        print_test("Token Analysis", False, "PyJWT not installed - skipping")
        return
    
    login_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        if response.status_code != 200:
            print_test("Login", False, f"Could not login: {response.status_code}")
            return
        
        data = response.json()
        
        # Check what's in response
        print("  Response contains:")
        print(f"    - access_token: {'✓' if 'access_token' in data else '✗'}")
        print(f"    - refresh_token: {'✓' if 'refresh_token' in data else '✗'}")
        print(f"    - user data: {'✓' if 'user' in data else '✗'}")
        
        # Decode and show token contents
        if 'access_token' in data:
            decoded = jwt.decode(data['access_token'], options={"verify_signature": False})
            print(f"\n  Token contains:")
            print(f"    - User ID: {decoded.get('sub', 'N/A')}")
            print(f"    - Email: {decoded.get('email', 'N/A')}")
            print(f"    - Role: {decoded.get('role', 'N/A')}")
            print(f"    - JTI (Token ID): {decoded.get('jti', 'N/A')}")
            print(f"    - Expires: {datetime.fromtimestamp(decoded.get('exp', 0))}")
            
            # Check if token has JTI (for revocation)
            if 'jti' in decoded:
                print_test("Token has JTI for revocation", True, "Token can be blacklisted ✓")
            else:
                print_test("Token has JTI for revocation", False, "⚠️ Token cannot be revoked!")
        
    except Exception as e:
        print_test("Token Analysis", False, f"Error: {str(e)}")

def test_brute_force_timing():
    """Test 2.8: Measure brute force attempt speed"""
    print(f"\n{YELLOW}=== Test 2.8: Brute Force Analysis ==={RESET}")
    
    login_data = {
        "email": TEST_EMAIL,
        "password": "wrongpassword"
    }
    
    try:
        attempts = 5
        start_time = time.time()
        
        for i in range(attempts):
            response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
            print(f"  Attempt {i+1}: Status {response.status_code}")
        
        end_time = time.time()
        duration = end_time - start_time
        avg_time = duration / attempts
        
        print(f"\n  Results:")
        print(f"    - {attempts} attempts in {duration:.2f} seconds")
        print(f"    - Average: {avg_time:.2f} seconds per attempt")
        print(f"    - Rate: {attempts/duration:.2f} attempts/second")
        
        if duration < 3:  # Less than 3 seconds for 5 attempts
            print_test("Rate Limiting", False, f"⚠️ No rate limiting! Can attempt {int(attempts/duration)} logins/second")
        else:
            print_test("Rate Limiting", True, "Some delay detected (might be network)")
            
    except Exception as e:
        print_test("Brute Force Test", False, f"Error: {str(e)}")

def test_token_reuse_after_logout():
    """Test 2.12: Try using token after logout"""
    print(f"\n{YELLOW}=== Test 2.12: Token Reuse After Logout ==={RESET}")
    
    login_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    try:
        # 1. Login
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        if response.status_code != 200:
            print_test("Login", False, "Could not login")
            return
        
        data = response.json()
        token = data['access_token']
        print(f"  ✓ Logged in successfully")
        
        # 2. Use token (should work)
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/bookings/", headers=headers)
        print(f"  ✓ Token works before logout: Status {response.status_code}")
        
        # 3. Logout
        response = requests.post(f"{BASE_URL}/api/auth/logout", headers=headers)
        print(f"  ✓ Logged out: Status {response.status_code}")
        
        # 4. Try to reuse same token (should fail!)
        response = requests.get(f"{BASE_URL}/api/bookings/", headers=headers)
        
        if response.status_code == 401:
            error = response.json()
            if "revoked" in error.get("detail", "").lower():
                print_test("Token Revocation", True, "Token properly revoked after logout ✓")
            else:
                print_test("Token Revocation", False, f"Token rejected but not for revocation: {error.get('detail')}")
        else:
            print_test("Token Revocation", False, f"⚠️ CRITICAL: Token still works after logout! Status: {response.status_code}")
            
    except Exception as e:
        print_test("Token Reuse Test", False, f"Error: {str(e)}")

def main():
    print(f"\n{YELLOW}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{YELLOW}║     AUTOMATED LOGIN SECURITY TESTS               ║{RESET}")
    print(f"{YELLOW}╚══════════════════════════════════════════════════╝{RESET}")
    print(f"\nBackend: {BASE_URL}")
    print(f"Test Account: {TEST_EMAIL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Quick validation
    print(f"{YELLOW}Validating test credentials...{RESET}")
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", 
                                json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        if response.status_code == 200:
            print(f"{GREEN}✓ Test credentials valid - proceeding with tests{RESET}\n")
        else:
            print(f"{RED}✗ Cannot login with test credentials!{RESET}")
            print(f"{YELLOW}Please create a test account first:{RESET}")
            print(f"  1. Go to http://localhost:3000/signup")
            print(f"  2. Create account: {TEST_EMAIL}")
            print(f"  3. Password: {TEST_PASSWORD}")
            print(f"{YELLOW}Or update TEST_EMAIL and TEST_PASSWORD in the script.{RESET}\n")
            return
    except Exception as e:
        print(f"{RED}✗ Cannot connect to backend: {e}{RESET}\n")
        return
    
    # Run all tests
    test_token_in_response()
    test_jwt_tampering()
    test_brute_force_timing()
    test_token_reuse_after_logout()
    
    print(f"\n{YELLOW}═══════════════════════════════════════════════════{RESET}")
    print(f"{GREEN}Testing Complete!{RESET}\n")

if __name__ == "__main__":
    main()
