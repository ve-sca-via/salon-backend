import requests
import sys
from datetime import time

BASE_URL = "http://localhost:8000/api/v1"

def get_admin_token():
    """Login as admin and get access token"""
    login_data = {
        "email": "admin@salonhub.com",
        "password": "12345678"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        response.raise_for_status()
        result = response.json()
        return result['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error logging in as admin: {e}")
        sys.exit(1)

def get_rm_token():
    """Login as RM and get access token"""
    login_data = {
        "email": "agent@salonhub.com",
        "password": "Safdar@1234"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        response.raise_for_status()
        result = response.json()
        return result['access_token']
    except requests.exceptions.RequestException as e:
        print(f"Error logging in as RM: {e}")
        sys.exit(1)

def create_vendor_request(token):
    """Create vendor join request as RM"""
    vendor_data = {
        "business_name": "Elite Beauty Salon",
        "business_type": "salon",
        "owner_name": "Priya Sharma",
        "owner_email": "vendor@salonhub.com",
        "owner_phone": "9876543210",
        "business_address": "123 MG Road, Kormangala",
        "city": "Bangalore",
        "state": "Karnataka",
        "pincode": "560034",
        "latitude": 12.9352,
        "longitude": 77.6245,
        "gst_number": "29ABCDE1234F1Z5",
        "pan_number": "ABCDE1234F",
        "cover_image_url": "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=800",
        "gallery_images": [
            "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800",
            "https://images.unsplash.com/photo-1562322140-8baeececf3df?w=800"
        ],
        "services_offered": {
            "Hair Services": ["Haircut", "Hair Color", "Hair Spa"],
            "Skin Care": ["Facial", "Clean Up"]
        },
        "staff_count": 5,
        "opening_time": "09:00:00",
        "closing_time": "20:00:00",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(
            f"{BASE_URL}/rm/vendor-requests",
            json=vendor_data,
            params={"is_draft": False},
            headers=headers
        )
        response.raise_for_status()
        result = response.json()
        request_id = result['id']
        print(f"Created vendor request: {vendor_data['business_name']}")
        print(f"Request ID: {request_id}")
        return request_id
    except requests.exceptions.RequestException as e:
        print(f"Error creating vendor request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

def approve_vendor_request(token, request_id):
    """Approve vendor request as admin"""
    approval_data = {
        "admin_notes": "All documents verified. Approved for onboarding."
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(
            f"{BASE_URL}/admin/vendor-requests/{request_id}/approve",
            json=approval_data,
            headers=headers
        )
        response.raise_for_status()
        result = response.json()
        print(f"Vendor request approved successfully")
        print(f"Salon ID: {result.get('salon_id', 'N/A')}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error approving vendor request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    print("Seeding vendor request and approval...\n")
    
    print("Step 1: RM creating vendor request...")
    rm_token = get_rm_token()
    request_id = create_vendor_request(rm_token)
    
    print("\nStep 2: Admin approving vendor request...")
    admin_token = get_admin_token()
    approve_vendor_request(admin_token, request_id)
    
    print("\nSeeding completed successfully")
