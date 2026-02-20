"""
Load testing file for the Salon Management API
Run with: locust -f locustfile.py --users 50 --spawn-rate 5 --host http://localhost:8000
"""
from locust import HttpUser, task, between


class SalonAPIUser(HttpUser):
    """Simulates a user interacting with the Salon Management API"""
    
    # Wait 1-3 seconds between tasks (simulate real user behavior)
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a simulated user starts - login here if needed"""
        # TODO: Add login logic if your endpoints require authentication
        # response = self.client.post("/api/auth/login", json={
        #     "email": "test@example.com",
        #     "password": "testpass"
        # })
        # self.token = response.json().get("token")
        pass
    
    @task(3)  # Weight: runs 3x more often than other tasks
    def get_salons(self):
        """Test getting list of salons"""
        self.client.get("/api/salons")
    
    @task(2)
    def get_services(self):
        """Test getting services"""
        self.client.get("/api/services")
    
    @task(1)
    def health_check(self):
        """Test health endpoint"""
        self.client.get("/health")
    
    # Add more tasks for your specific endpoints
    # @task(1)
    # def create_booking(self):
    #     """Test creating a booking"""
    #     self.client.post("/api/bookings", json={
    #         "salon_id": "123",
    #         "service_id": "456",
    #         "date": "2026-01-15",
    #         "time": "10:00"
    #     })


class AdminUser(HttpUser):
    """Simulates an admin user"""
    
    wait_time = between(2, 5)
    
    @task
    def view_dashboard(self):
        """Test dashboard endpoint"""
        self.client.get("/api/admin/dashboard")
