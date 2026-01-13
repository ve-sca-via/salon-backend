import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"

def create_admin_user():
    """Create admin user via signup API"""
    signup_data = {
        "email": "admin@salonhub.com",
        "password": "Safdar@1234",
        "full_name": "system-admin",
        "user_role": "customer"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/signup", json=signup_data)
        response.raise_for_status()
        result = response.json()
        print(f"Admin user created: {result['user']['email']}")
        print(f"User ID: {result['user']['id']}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error creating admin user: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    print("Seeding admin user...")
    create_admin_user()
    print("Seeding completed,  go to mailpit to confirm the email. and go to supabase dashboard to change the role to admin")
