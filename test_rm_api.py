import requests
import json

# Test the RM API endpoint
url = "http://localhost:8000/api/v1/admin/rms"

# You'll need to replace this with a valid admin token
headers = {
    "Authorization": "Bearer YOUR_TOKEN_HERE"
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"\nResponse Headers: {response.headers}")
    print(f"\nResponse Body:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
