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

def create_service_category(token, category_data):
    """Create service category via admin API"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(f"{BASE_URL}/admin/service-categories", json=category_data, headers=headers)
        response.raise_for_status()
        result = response.json()
        print(f"Created category: {category_data['name']}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error creating category {category_data['name']}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")

def seed_categories():
    """Seed all service categories"""
    categories = [
        {
            "name": "Hair Services",
            "description": "Professional hair styling, cutting, coloring, and treatments",
            "icon_url": "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=400",
            "display_order": 1,
            "is_active": True
        },
        {
            "name": "Skin Care",
            "description": "Facials, skin treatments, and beauty therapies",
            "icon_url": "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=400",
            "display_order": 2,
            "is_active": True
        },
        {
            "name": "Nail Services",
            "description": "Manicure, pedicure, and nail art services",
            "icon_url": "https://images.unsplash.com/photo-1604654894610-df63bc536371?w=400",
            "display_order": 3,
            "is_active": True
        },
        {
            "name": "Makeup",
            "description": "Professional makeup services for all occasions",
            "icon_url": "https://images.unsplash.com/photo-1512496015851-a90fb38ba796?w=400",
            "display_order": 4,
            "is_active": True
        },
        {
            "name": "Spa & Massage",
            "description": "Relaxing spa treatments and therapeutic massages",
            "icon_url": "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=400",
            "display_order": 5,
            "is_active": True
        },
        {
            "name": "Bridal Services",
            "description": "Complete bridal packages and wedding services",
            "icon_url": "https://images.unsplash.com/photo-1519741497674-611481863552?w=400",
            "display_order": 6,
            "is_active": True
        },
        {
            "name": "Men's Grooming",
            "description": "Specialized grooming services for men",
            "icon_url": "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=400",
            "display_order": 7,
            "is_active": True
        },
        {
            "name": "Threading & Waxing",
            "description": "Hair removal services including threading and waxing",
            "icon_url": "https://images.unsplash.com/photo-1516975080664-ed2fc6a32937?w=400",
            "display_order": 8,
            "is_active": True
        }
    ]
    
    token = get_admin_token()
    
    for category in categories:
        create_service_category(token, category)
    
    print(f"\nSeeded {len(categories)} service categories successfully")

if __name__ == "__main__":
    print("Seeding service categories...\n")
    seed_categories()
