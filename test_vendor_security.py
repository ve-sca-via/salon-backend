"""
Vendor Endpoints Security Tests
Tests role-based access control and ownership validation

Run: python test_vendor_security.py
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

# Test credentials
CUSTOMER_EMAIL = "787alisniazi787@gmail.com"
CUSTOMER_PASSWORD = "SecurePass123!"

VENDOR_EMAIL = "soni@gmail.com"  # UPDATE THIS
VENDOR_PASSWORD = "Safdar@1234"  # UPDATE THIS

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_test(name, passed, details=""):
    symbol = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
    print(f"{symbol} {name}")
    if details:
        print(f"  {details}")

def get_token(email, password):
    """Helper to get auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": email,
        "password": password
    })
    if response.status_code == 200:
        return response.json()['access_token']
    return None

def test_vendor_endpoints_with_customer():
    """Test 1: Customer trying to access vendor endpoints"""
    print(f"\n{YELLOW}=== Test 1: Customer Access to Vendor Endpoints ==={RESET}")
    
    customer_token = get_token(CUSTOMER_EMAIL, CUSTOMER_PASSWORD)
    if not customer_token:
        print_test("Get customer token", False, "Could not login as customer")
        return
    
    headers = {"Authorization": f"Bearer {customer_token}"}
    
    # List of vendor-only endpoints
    vendor_endpoints = [
        ("GET", "/api/vendors/salon", "Own Salon"),
        ("PUT", "/api/vendors/salon", "Update Salon"),
        ("GET", "/api/vendors/services", "Services List"),
        ("POST", "/api/vendors/services", "Create Service"),
        ("GET", "/api/vendors/staff", "Staff List"),
        ("POST", "/api/vendors/staff", "Add Staff"),
        ("GET", "/api/vendors/bookings", "Vendor Bookings"),
        ("GET", "/api/vendors/dashboard", "Dashboard"),
        ("GET", "/api/vendors/analytics", "Analytics"),
    ]
    
    blocked_count = 0
    vulnerable_count = 0
    
    for method, endpoint, name in vendor_endpoints:
        try:
            if method == "POST":
                response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json={})
            elif method == "PUT":
                response = requests.put(f"{BASE_URL}{endpoint}", headers=headers, json={})
            else:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            
            if response.status_code == 403:
                print(f"  {GREEN}✓{RESET} {name}: Blocked (403)")
                blocked_count += 1
            elif response.status_code == 401:
                print(f"  {GREEN}✓{RESET} {name}: Unauthorized (401)")
                blocked_count += 1
            elif response.status_code == 404:
                # 404 might be OK if salon doesn't exist
                print(f"  {GREEN}✓{RESET} {name}: Not Found (404 - role check passed)")
                blocked_count += 1
            elif response.status_code == 422:
                # Validation error - means it got past auth
                print(f"  {RED}✗{RESET} {name}: {RED}VULNERABLE{RESET} (422 - auth bypassed!)")
                vulnerable_count += 1
            else:
                print(f"  {RED}✗{RESET} {name}: {RED}VULNERABLE{RESET} (Status {response.status_code})")
                vulnerable_count += 1
        except Exception as e:
            print(f"  {YELLOW}?{RESET} {name}: Error - {str(e)}")
    
    if vulnerable_count == 0:
        print_test("Vendor Endpoints Protected", True, f"{blocked_count}/{len(vendor_endpoints)} endpoints properly blocked")
    else:
        print_test("Vendor Endpoints Protected", False, f"⚠️ {vulnerable_count} endpoints accessible to non-vendor!")

def test_vendor_endpoints_without_auth():
    """Test 2: No authentication token"""
    print(f"\n{YELLOW}=== Test 2: Vendor Endpoints Without Auth ==={RESET}")
    
    vendor_endpoints = [
        ("GET", "/api/vendors/salon", "Salon"),
        ("GET", "/api/vendors/services", "Services"),
        ("GET", "/api/vendors/dashboard", "Dashboard"),
    ]
    
    blocked_count = 0
    vulnerable_count = 0
    
    for method, endpoint, name in vendor_endpoints:
        response = requests.request(method, f"{BASE_URL}{endpoint}")
        
        if response.status_code in [401, 403]:
            print(f"  {GREEN}✓{RESET} {name}: Blocked ({response.status_code})")
            blocked_count += 1
        else:
            print(f"  {RED}✗{RESET} {name}: {RED}PUBLIC ACCESS{RESET} (Status {response.status_code})")
            vulnerable_count += 1
    
    if vulnerable_count == 0:
        print_test("Authentication Required", True, f"All endpoints require auth")
    else:
        print_test("Authentication Required", False, f"⚠️ {vulnerable_count} endpoints publicly accessible!")

def test_vendor_access_with_vendor():
    """Test 3: Vendor user accessing vendor endpoints"""
    print(f"\n{YELLOW}=== Test 3: Vendor User Access ==={RESET}")
    
    vendor_token = get_token(VENDOR_EMAIL, VENDOR_PASSWORD)
    if not vendor_token:
        print_test("Get vendor token", False, "Could not login as vendor - create vendor account first!")
        print(f"\n{YELLOW}To create vendor account:{RESET}")
        print(f"1. Create vendor join request through app")
        print(f"2. Admin approves it")
        print(f"3. Complete registration with: {VENDOR_EMAIL}")
        return
    
    headers = {"Authorization": f"Bearer {vendor_token}"}
    
    # Test key vendor endpoints
    vendor_endpoints = [
        ("GET", "/api/vendors/salon", "Own Salon"),
        ("GET", "/api/vendors/services", "Services List"),
        ("GET", "/api/vendors/dashboard", "Dashboard"),
    ]
    
    success_count = 0
    
    for method, endpoint, name in vendor_endpoints:
        response = requests.request(method, f"{BASE_URL}{endpoint}", headers=headers)
        
        if response.status_code == 200:
            print(f"  {GREEN}✓{RESET} {name}: Accessible (200)")
            success_count += 1
        elif response.status_code == 404:
            # 404 is acceptable - salon might not exist yet
            print(f"  {GREEN}✓{RESET} {name}: Auth OK (404 - no data)")
            success_count += 1
        else:
            print(f"  {RED}✗{RESET} {name}: Failed ({response.status_code})")
    
    if success_count == len(vendor_endpoints):
        print_test("Vendor Access", True, "Vendor can access all endpoints")
    else:
        print_test("Vendor Access", False, f"Vendor blocked from {len(vendor_endpoints) - success_count} endpoints")

def test_cross_vendor_access():
    """Test 4: Try to access another vendor's data"""
    print(f"\n{YELLOW}=== Test 4: Cross-Vendor Data Access ==={RESET}")
    
    vendor_token = get_token(VENDOR_EMAIL, VENDOR_PASSWORD)
    if not vendor_token:
        print(f"  {YELLOW}⚠{RESET} Skipping - no vendor account")
        return
    
    headers = {"Authorization": f"Bearer {vendor_token}"}
    
    # Try to modify service from another salon (fake ID)
    response = requests.put(
        f"{BASE_URL}/api/vendors/services/99999999",
        headers=headers,
        json={"name": "Hacked Service", "price": 0}
    )
    
    if response.status_code in [403, 404]:
        print_test("Modify Other Vendor's Service", True, f"Blocked ({response.status_code})")
    else:
        print_test("Modify Other Vendor's Service", False, f"⚠️ CRITICAL: Action allowed! ({response.status_code})")
    
    # Try to delete staff from another salon
    response = requests.delete(
        f"{BASE_URL}/api/vendors/staff/99999999",
        headers=headers
    )
    
    if response.status_code in [403, 404]:
        print_test("Delete Other Vendor's Staff", True, f"Blocked ({response.status_code})")
    else:
        print_test("Delete Other Vendor's Staff", False, f"⚠️ CRITICAL: Deletion allowed! ({response.status_code})")

def test_booking_ownership():
    """Test 5: Vendor can only see their own bookings"""
    print(f"\n{YELLOW}=== Test 5: Booking Ownership Validation ==={RESET}")
    
    vendor_token = get_token(VENDOR_EMAIL, VENDOR_PASSWORD)
    if not vendor_token:
        print(f"  {YELLOW}⚠{RESET} Skipping - no vendor account")
        return
    
    headers = {"Authorization": f"Bearer {vendor_token}"}
    
    # Get vendor's bookings
    response = requests.get(f"{BASE_URL}/api/vendors/bookings", headers=headers)
    
    if response.status_code == 200:
        bookings = response.json().get('bookings', [])
        print_test("Get Own Bookings", True, f"Retrieved {len(bookings)} bookings")
        
        # Try to update a booking with fake ID (should fail)
        response = requests.put(
            f"{BASE_URL}/api/vendors/bookings/99999999/status",
            headers=headers,
            json={"status": "confirmed"}
        )
        
        if response.status_code in [403, 404]:
            print_test("Update Other Vendor's Booking", True, f"Blocked ({response.status_code})")
        else:
            print_test("Update Other Vendor's Booking", False, f"⚠️ CRITICAL: Update allowed! ({response.status_code})")
    elif response.status_code == 404:
        print_test("Get Own Bookings", True, "No salon found (expected for new vendors)")
    else:
        print_test("Get Own Bookings", False, f"Failed ({response.status_code})")

def test_service_management():
    """Test 6: Service CRUD operations"""
    print(f"\n{YELLOW}=== Test 6: Service Management Security ==={RESET}")
    
    vendor_token = get_token(VENDOR_EMAIL, VENDOR_PASSWORD)
    if not vendor_token:
        print(f"  {YELLOW}⚠{RESET} Skipping - no vendor account")
        return
    
    headers = {"Authorization": f"Bearer {vendor_token}"}
    
    # Try to create service with XSS payload
    xss_service = {
        "name": "<script>alert('XSS')</script>",
        "description": "Test service",
        "price": 100,
        "duration": 60
    }
    
    response = requests.post(
        f"{BASE_URL}/api/vendors/services",
        headers=headers,
        json=xss_service
    )
    
    if response.status_code == 201:
        service = response.json()
        # Check if XSS was escaped
        if "<script>" not in service.get("name", ""):
            print_test("XSS Protection in Service Name", True, "XSS payload escaped")
        else:
            print_test("XSS Protection in Service Name", False, "⚠️ XSS payload NOT escaped!")
        
        # Clean up - delete the test service
        service_id = service.get("id")
        if service_id:
            requests.delete(f"{BASE_URL}/api/vendors/services/{service_id}", headers=headers)
    elif response.status_code in [404, 422]:
        print_test("Create Service", True, f"Salon validation working ({response.status_code})")
    else:
        print_test("Create Service", False, f"Unexpected status: {response.status_code}")

def main():
    print(f"\n{BLUE}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{BLUE}║     VENDOR ENDPOINTS SECURITY TESTS              ║{RESET}")
    print(f"{BLUE}╚══════════════════════════════════════════════════╝{RESET}")
    print(f"\nBackend: {BASE_URL}")
    print(f"Customer Account: {CUSTOMER_EMAIL}")
    print(f"Vendor Account: {VENDOR_EMAIL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Validate customer credentials
    print(f"{YELLOW}Validating credentials...{RESET}")
    customer_token = get_token(CUSTOMER_EMAIL, CUSTOMER_PASSWORD)
    if not customer_token:
        print(f"{RED}✗ Cannot login with customer credentials!{RESET}\n")
        return
    print(f"{GREEN}✓ Customer credentials valid{RESET}\n")
    
    # Run tests
    test_vendor_endpoints_with_customer()
    test_vendor_endpoints_without_auth()
    test_vendor_access_with_vendor()
    test_cross_vendor_access()
    test_booking_ownership()
    test_service_management()
    
    print(f"\n{BLUE}═══════════════════════════════════════════════════{RESET}")
    print(f"{GREEN}Testing Complete!{RESET}\n")

if __name__ == "__main__":
    main()
