import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"

def get_admin_token():
    """Login as admin and get access token"""
    login_data = {
        "email": "admin@salonhub.com",
        "password": "Safdar@1234"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        response.raise_for_status()
        result = response.json()
        return result['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error logging in as admin: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

def create_rm_user(token):
    """Create RM user via admin API"""
    user_data = {
        "email": "agent@salonhub.com",
        "password": "Safdar@1234",
        "full_name": "RM Agent",
        "role": "relationship_manager"
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(f"{BASE_URL}/admin/users/", json=user_data, headers=headers)
        response.raise_for_status()
        result = response.json()
        print(f"RM user created: {user_data['email']}")
        print(f"User ID: {result['data']['user_id']}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error creating RM user: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    print("Seeding RM user...")
    token = get_admin_token()
    create_rm_user(token)
    print("Seeding completed")
