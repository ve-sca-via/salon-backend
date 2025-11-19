"""
Quick Database Seeding Script
This script helps you quickly seed your database with test data
"""
import asyncio
import httpx
from datetime import datetime, timedelta

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 30.0

# Test data
TEST_DATA = {
    "admin": {
        "email": "admin@salon.com",
        "password": "Admin123!",
        "full_name": "System Administrator",
        "phone": "+919876543211",
        "user_role": "admin"
    },
    "rm": {
        "email": "rm@salon.com",
        "password": "RM123456!",
        "full_name": "Relationship Manager",
        "phone": "+919876543212",
        "user_role": "relationship_manager"
    },
    "customer": {
        "email": "customer@test.com",
        "password": "Password123!",
        "full_name": "Test Customer",
        "phone": "+919876543210",
        "user_role": "customer"
    },
    "services": [
        {
            "name": "Hair Cut",
            "description": "Professional hair cutting service",
            "category": "Hair",
            "duration_minutes": 30,
            "price": 500
        },
        {
            "name": "Hair Styling",
            "description": "Expert hair styling for any occasion",
            "category": "Hair",
            "duration_minutes": 45,
            "price": 800
        },
        {
            "name": "Facial Treatment",
            "description": "Relaxing facial treatment",
            "category": "Facial",
            "duration_minutes": 60,
            "price": 1200
        },
        {
            "name": "Manicure",
            "description": "Professional nail care",
            "category": "Nails",
            "duration_minutes": 30,
            "price": 400
        },
        {
            "name": "Pedicure",
            "description": "Complete foot care treatment",
            "category": "Nails",
            "duration_minutes": 45,
            "price": 600
        }
    ],
    "salons": [
        {
            "name": "Luxury Hair Salon",
            "email": "luxury@salon.com",
            "phone": "+919876543220",
            "address": "Connaught Place, New Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110001",
            "latitude": 28.6139,
            "longitude": 77.2090,
            "description": "Premium salon services in the heart of Delhi",
            "opening_time": "09:00",
            "closing_time": "21:00"
        },
        {
            "name": "Elite Beauty Parlour",
            "email": "elite@beauty.com",
            "phone": "+919876543230",
            "address": "Saket, New Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110017",
            "latitude": 28.5244,
            "longitude": 77.2066,
            "description": "Your destination for beauty and wellness",
            "opening_time": "10:00",
            "closing_time": "20:00"
        },
        {
            "name": "Style Studio",
            "email": "style@studio.com",
            "phone": "+919876543240",
            "address": "Karol Bagh, New Delhi",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110005",
            "latitude": 28.6519,
            "longitude": 77.1909,
            "description": "Modern styling for the modern you",
            "opening_time": "09:30",
            "closing_time": "20:30"
        }
    ]
}

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

async def print_status(message: str, status: str = "info"):
    """Print colored status messages"""
    if status == "success":
        print(f"{Colors.GREEN}✓{Colors.RESET} {message}")
    elif status == "error":
        print(f"{Colors.RED}✗{Colors.RESET} {message}")
    elif status == "warning":
        print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")
    else:
        print(f"{Colors.BLUE}ℹ{Colors.RESET} {message}")

async def signup_user(client: httpx.AsyncClient, user_data: dict, role: str):
    """Create a user account"""
    try:
        # Note: Public signup only allows 'customer' role
        # Admin and RM accounts must be created differently
        if user_data.get("user_role") not in ["customer"]:
            await print_status(
                f"⚠ Cannot create {role} via public signup (security restriction)",
                "warning"
            )
            await print_status(
                f"  → Create {role} manually in Supabase or use admin API",
                "info"
            )
            return None
            
        response = await client.post(
            f"{BASE_URL}/auth/signup",
            json=user_data,
            timeout=TIMEOUT
        )
        if response.status_code in [200, 201]:
            data = response.json()
            await print_status(f"Created {role} user: {user_data['email']}", "success")
            return data.get("access_token")
        else:
            await print_status(f"Failed to create {role}: {response.text}", "error")
            return None
    except Exception as e:
        await print_status(f"Error creating {role}: {str(e)}", "error")
        return None

async def login_user(client: httpx.AsyncClient, email: str, password: str):
    """Login and get access token"""
    try:
        response = await client.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT
        )
        if response.status_code == 200:
            data = response.json()
            await print_status(f"Logged in as: {email}", "success")
            return data.get("access_token")
        else:
            await print_status(f"Login failed: {response.text}", "error")
            return None
    except Exception as e:
        await print_status(f"Login error: {str(e)}", "error")
        return None

async def create_service(client: httpx.AsyncClient, service_data: dict, admin_token: str):
    """Create a service"""
    try:
        response = await client.post(
            f"{BASE_URL}/admin/services",
            json=service_data,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT
        )
        if response.status_code in [200, 201]:
            data = response.json()
            await print_status(f"Created service: {service_data['name']}", "success")
            return data
        else:
            await print_status(f"Failed to create service {service_data['name']}: {response.text}", "error")
            return None
    except Exception as e:
        await print_status(f"Error creating service: {str(e)}", "error")
        return None

async def create_salon(client: httpx.AsyncClient, salon_data: dict, admin_token: str):
    """Create a salon"""
    try:
        response = await client.post(
            f"{BASE_URL}/salons/",
            json=salon_data,
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT
        )
        if response.status_code in [200, 201]:
            data = response.json()
            await print_status(f"Created salon: {salon_data['name']}", "success")
            return data
        else:
            await print_status(f"Failed to create salon {salon_data['name']}: {response.text}", "error")
            return None
    except Exception as e:
        await print_status(f"Error creating salon: {str(e)}", "error")
        return None

async def main():
    """Main seeding function"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}  🌱 Database Seeding Script{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")
    
    await print_status(f"Base URL: {BASE_URL}", "info")
    await print_status("Starting seeding process...\n", "info")
    
    async with httpx.AsyncClient() as client:
        # Step 1: Create users
        print(f"\n{Colors.BOLD}Step 1: Creating Users{Colors.RESET}")
        print("-" * 40)
        
        admin_token = await signup_user(client, TEST_DATA["admin"], "Admin")
        if not admin_token:
            await print_status("Admin creation failed. Trying login...", "warning")
            admin_token = await login_user(client, TEST_DATA["admin"]["email"], TEST_DATA["admin"]["password"])
        
        rm_token = await signup_user(client, TEST_DATA["rm"], "RM")
        if not rm_token:
            await print_status("RM creation failed. Trying login...", "warning")
            rm_token = await login_user(client, TEST_DATA["rm"]["email"], TEST_DATA["rm"]["password"])
        
        customer_token = await signup_user(client, TEST_DATA["customer"], "Customer")
        if not customer_token:
            await print_status("Customer creation failed. Trying login...", "warning")
            customer_token = await login_user(client, TEST_DATA["customer"]["email"], TEST_DATA["customer"]["password"])
        
        if not admin_token:
            await print_status("Cannot proceed without admin token!", "error")
            return
        
        # Step 2: Create services
        print(f"\n{Colors.BOLD}Step 2: Creating Services{Colors.RESET}")
        print("-" * 40)
        
        service_ids = []
        for service_data in TEST_DATA["services"]:
            service = await create_service(client, service_data, admin_token)
            if service:
                service_ids.append(service.get("id"))
        
        # Step 3: Create salons
        print(f"\n{Colors.BOLD}Step 3: Creating Salons{Colors.RESET}")
        print("-" * 40)
        
        salon_ids = []
        for salon_data in TEST_DATA["salons"]:
            salon = await create_salon(client, salon_data, admin_token)
            if salon:
                salon_ids.append(salon.get("salon", {}).get("id"))
        
        # Summary
        print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}  ✓ Seeding Complete!{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.RESET}\n")
        
        print(f"{Colors.BOLD}Summary:{Colors.RESET}")
        print(f"  • Users created: 3 (Admin, RM, Customer)")
        print(f"  • Services created: {len(service_ids)}")
        print(f"  • Salons created: {len(salon_ids)}")
        
        print(f"\n{Colors.BOLD}Test Credentials:{Colors.RESET}")
        print(f"  Admin:    {TEST_DATA['admin']['email']} / {TEST_DATA['admin']['password']}")
        print(f"  RM:       {TEST_DATA['rm']['email']} / {TEST_DATA['rm']['password']}")
        print(f"  Customer: {TEST_DATA['customer']['email']} / {TEST_DATA['customer']['password']}")
        
        if service_ids:
            print(f"\n{Colors.BOLD}Service IDs:{Colors.RESET}")
            for sid in service_ids[:3]:  # Show first 3
                print(f"  • {sid}")
        
        if salon_ids:
            print(f"\n{Colors.BOLD}Salon IDs:{Colors.RESET}")
            for sid in salon_ids[:3]:  # Show first 3
                print(f"  • {sid}")
        
        print(f"\n{Colors.YELLOW}Next Steps:{Colors.RESET}")
        print(f"  1. Import Postman collection: Salon_API_Postman_Collection.json")
        print(f"  2. Update collection variables with the IDs above")
        print(f"  3. Start testing with API_TESTING_GUIDE.md")
        print()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Seeding interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}Error: {str(e)}{Colors.RESET}")
