import requests
import sys

BASE_URL = "http://localhost:8000/api/v1"
RM_EMAIL = "agent@salonhub.com"
RM_PASSWORD = "Safdar@1234"

def get_rm_token():
    """Login as RM and return access token."""
    login_data = {"email": RM_EMAIL, "password": RM_PASSWORD}
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.exceptions.RequestException as exc:
        print(f"Failed to login RM: {exc}")
        if getattr(exc, "response", None) is not None:
            print(f"Response: {exc.response.text}")
        sys.exit(1)

def create_vendor_request(token: str):
    """Submit a vendor join request as the RM user."""
    vendor_data = {
        "business_name": "Aurora Glow Salon",
        "business_type": "salon",
        "owner_name": "Meera Kapoor",
        "owner_email": "meera.kapoor@example.com",
        "owner_phone": "+91-9810012345",
        "business_address": "12A Cyber City, DLF Phase 3, Near Rapid Metro",
        "city": "Gurugram",
        "state": "Haryana",
        "pincode": "122002",
        "latitude": 28.444788,
        "longitude": 77.028321,
        "gst_number": "06ABCDE1234F1Z5",
        "pan_number": "ABCDE1234F",
        "cover_image_url": "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=1200",
        "gallery_images": [
            "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=1200",
            "https://images.unsplash.com/photo-1524504388940-1e6c1d6432ef?w=1200",
            "https://images.unsplash.com/photo-1507048331197-7d4ac70811cf?w=1200",
        ],
        "services_offered": {
            "Hair Services": ["Haircut", "Hair Spa", "Balayage"],
            "Skin Care": ["Hydrafacial", "Detan Facial"],
            "Nail Services": ["Gel Manicure", "Classic Pedicure"],
            "Makeup": ["Party Makeup"],
            "Spa & Massage": ["Aromatherapy Massage"],
            "Bridal Services": ["Bridal Trial Session"],
            "Men's Grooming": ["Beard Styling", "Men's Haircut"],
            "Threading & Waxing": ["Full Arms Wax", "Eyebrow Threading"],
        },
        "opening_time": "09:30:00",
        "closing_time": "21:00:00",
        "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    }

    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.post(
            f"{BASE_URL}/rm/vendor-requests",
            params={"is_draft": False},
            json=vendor_data,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        print("Vendor request created successfully")
        print(f"Request ID: {data.get('id', 'unknown')}")
        return data
    except requests.exceptions.RequestException as exc:
        print(f"Failed to create vendor request: {exc}")
        if getattr(exc, "response", None) is not None:
            print(f"Response: {exc.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    print("Creating vendor request as RM...\n")
    token = get_rm_token()
    create_vendor_request(token)
