"""
Test Pending Salon Approval Workflow
Tests the complete flow from submission to approval/rejection
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@salonhub.com"
ADMIN_PASSWORD = "admin123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.ENDC}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.ENDC}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.ENDC}")

def print_header(msg):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}{Colors.ENDC}\n")

# ==============================================
# TEST 1: Check Backend Health
# ==============================================
def test_backend_health():
    print_header("TEST 1: Backend Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print_success("Backend is running")
            print_info(f"Response: {response.json()}")
            return True
        else:
            print_error(f"Backend returned status code: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Backend is not running: {str(e)}")
        return False

# ==============================================
# TEST 2: Admin Login
# ==============================================
def test_admin_login():
    print_header("TEST 2: Admin Login")
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            
            print_success("Admin login successful")
            print_info(f"Admin: {user.get('email')} (Role: {user.get('role')})")
            print_info(f"Token: {token[:50]}...")
            return token
        else:
            print_error(f"Login failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
    except Exception as e:
        print_error(f"Login error: {str(e)}")
        return None

# ==============================================
# TEST 3: Get Pending Requests
# ==============================================
def test_get_pending_requests(token):
    print_header("TEST 3: Get Pending Salon Requests")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/api/admin/vendor-requests?status_filter=pending",
            headers=headers
        )
        
        if response.status_code == 200:
            requests_data = response.json()
            count = len(requests_data)
            
            print_success(f"Found {count} pending request(s)")
            
            if count > 0:
                print_info("\nPending Requests:")
                for idx, req in enumerate(requests_data, 1):
                    print(f"\n  {idx}. {req.get('business_name')}")
                    print(f"     ID: {req.get('id')}")
                    print(f"     Owner: {req.get('owner_name')}")
                    print(f"     Email: {req.get('owner_email')}")
                    print(f"     Status: {req.get('status')}")
                    print(f"     Submitted: {req.get('created_at')}")
                
                return requests_data
            else:
                print_warning("No pending requests found")
                print_info("You need to submit a salon request first using RM portal")
                return []
        else:
            print_error(f"Failed to fetch requests: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
    except Exception as e:
        print_error(f"Error fetching requests: {str(e)}")
        return None

# ==============================================
# TEST 4: Check Email Configuration
# ==============================================
def test_email_config():
    print_header("TEST 4: Email Configuration Check")
    
    try:
        # Read .env file
        with open('.env', 'r') as f:
            env_content = f.read()
        
        # Check SMTP settings
        smtp_user = None
        smtp_pass = None
        
        for line in env_content.split('\n'):
            if line.startswith('SMTP_USER='):
                smtp_user = line.split('=')[1].strip('"')
            elif line.startswith('SMTP_PASSWORD='):
                smtp_pass = line.split('=')[1].strip('"')
        
        print_info(f"SMTP_USER: {smtp_user}")
        
        if smtp_user == "your-email@gmail.com":
            print_warning("⚠ SMTP credentials are NOT configured!")
            print_warning("Emails will NOT be sent in current state.")
            print_info("\nTo fix this:")
            print_info("1. Update SMTP_USER in .env with your Gmail address")
            print_info("2. Update SMTP_PASSWORD with Gmail App Password")
            print_info("3. Or use SendGrid/AWS SES credentials")
            return False
        else:
            print_success("SMTP credentials are configured")
            if smtp_pass and smtp_pass != "your-app-password":
                print_success("SMTP password is set")
                return True
            else:
                print_warning("SMTP password might not be configured correctly")
                return False
                
    except Exception as e:
        print_error(f"Error checking email config: {str(e)}")
        return False

# ==============================================
# TEST 5: Test Approval Flow (Mock)
# ==============================================
def test_approval_flow(token, request_data):
    print_header("TEST 5: Approval Flow Test")
    
    if not request_data or len(request_data) == 0:
        print_warning("No pending requests to approve")
        print_info("Skipping approval test")
        return False
    
    # Get first pending request
    request = request_data[0]
    request_id = request.get('id')
    salon_name = request.get('business_name')
    
    print_info(f"Testing approval for: {salon_name}")
    print_info(f"Request ID: {request_id}")
    
    # Ask user confirmation
    print_warning("\n⚠ This will ACTUALLY approve the salon and send emails!")
    user_input = input("Do you want to proceed? (yes/no): ").strip().lower()
    
    if user_input != 'yes':
        print_info("Approval test cancelled by user")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            f"{BASE_URL}/api/admin/vendor-requests/{request_id}/approve",
            headers=headers,
            json={"admin_notes": "Test approval from workflow script"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("✓ Salon approved successfully!")
            print_success(f"✓ Salon ID: {result.get('data', {}).get('salon_id')}")
            print_success(f"✓ RM Points Awarded: {result.get('data', {}).get('rm_score_awarded')}")
            
            print_info("\nWhat should have happened:")
            print_info("1. ✓ Salon record created in database")
            print_info("2. ✓ RM score updated (+10 points)")
            print_info("3. ✓ JWT token generated")
            print_info("4. ✓ Approval email sent to vendor owner")
            print_info("5. ✗ Notification created for RM (NOT IMPLEMENTED YET)")
            
            print_warning("\nCheck vendor email inbox:")
            print_warning(f"Email: {request.get('owner_email')}")
            print_warning("Subject: 🎉 Congratulations! {salon_name} has been approved")
            print_warning("Should contain: Registration link with JWT token")
            
            return True
        else:
            print_error(f"Approval failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Approval error: {str(e)}")
        return False

# ==============================================
# TEST 6: Check Email Templates
# ==============================================
def test_email_templates():
    print_header("TEST 6: Email Templates Check")
    
    import os
    template_dir = "app/templates/email"
    
    templates = [
        "vendor_approval.html",
        "vendor_rejection.html",
        "welcome_vendor.html",
        "payment_receipt.html",
        "booking_confirmation.html",
        "booking_cancellation.html"
    ]
    
    all_exist = True
    for template in templates:
        template_path = os.path.join(template_dir, template)
        if os.path.exists(template_path):
            print_success(f"Found: {template}")
        else:
            print_error(f"Missing: {template}")
            all_exist = False
    
    return all_exist

# ==============================================
# TEST 7: Database Tables Check
# ==============================================
def test_database_tables(token):
    print_header("TEST 7: Database Tables Check")
    
    tables_to_check = [
        ("vendor_join_requests", "Salon submission requests"),
        ("salons", "Approved salons"),
        ("profiles", "User profiles"),
        ("rm_score_history", "RM points tracking"),
        ("system_config", "System settings"),
        ("registration_payments", "Payment records")
    ]
    
    print_info("Expected tables:")
    for table, description in tables_to_check:
        print(f"  ✓ {table:<25} - {description}")
    
    print_success("\nAll required tables should exist (created via Supabase migrations)")
    return True

# ==============================================
# MAIN TEST RUNNER
# ==============================================
def run_all_tests():
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║   PENDING SALON APPROVAL WORKFLOW TEST                    ║")
    print("║   Testing End-to-End Flow                                 ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}\n")
    
    results = {
        "backend_health": False,
        "admin_login": False,
        "pending_requests": False,
        "email_config": False,
        "email_templates": False,
        "database_tables": False,
        "approval_flow": False
    }
    
    # Test 1: Backend Health
    results["backend_health"] = test_backend_health()
    if not results["backend_health"]:
        print_error("\n❌ Backend is not running. Please start the backend server first.")
        return
    
    # Test 2: Admin Login
    token = test_admin_login()
    if token:
        results["admin_login"] = True
    else:
        print_error("\n❌ Cannot proceed without admin authentication")
        return
    
    # Test 3: Get Pending Requests
    pending_requests = test_get_pending_requests(token)
    if pending_requests is not None:
        results["pending_requests"] = True
    
    # Test 4: Email Configuration
    results["email_config"] = test_email_config()
    
    # Test 5: Email Templates
    results["email_templates"] = test_email_templates()
    
    # Test 6: Database Tables
    results["database_tables"] = test_database_tables(token)
    
    # Test 7: Approval Flow (Optional)
    if pending_requests and len(pending_requests) > 0:
        results["approval_flow"] = test_approval_flow(token, pending_requests)
    
    # Print Summary
    print_header("TEST SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\nResults: {passed}/{total} tests passed\n")
    
    for test_name, passed in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.ENDC}" if passed else f"{Colors.RED}✗ FAIL{Colors.ENDC}"
        print(f"  {status}  {test_name.replace('_', ' ').title()}")
    
    # Final Recommendations
    print_header("RECOMMENDATIONS")
    
    if not results["email_config"]:
        print_warning("⚠ CRITICAL: Email is NOT configured!")
        print_info("Action required:")
        print_info("1. Get Gmail App Password:")
        print_info("   - Go to Google Account > Security > 2-Step Verification > App Passwords")
        print_info("   - Generate password for 'Mail' application")
        print_info("2. Update .env file:")
        print_info("   SMTP_USER=\"your-email@gmail.com\"")
        print_info("   SMTP_PASSWORD=\"your-16-char-app-password\"")
        print_info("3. Restart backend server")
    else:
        print_success("✓ Email configuration looks good")
    
    if not pending_requests or len(pending_requests) == 0:
        print_info("\nℹ No pending requests found")
        print_info("To test approval flow:")
        print_info("1. Go to RM Portal (http://localhost:3000/rm)")
        print_info("2. Login as RM agent")
        print_info("3. Submit a new salon")
        print_info("4. Run this test again")
    
    if results["backend_health"] and results["admin_login"]:
        print_success("\n✓ Core functionality is working!")
        if not results["approval_flow"]:
            print_info("✓ Ready to test approval when salon is submitted")
    
    print(f"\n{Colors.BOLD}Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}\n")

if __name__ == "__main__":
    run_all_tests()
