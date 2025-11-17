"""
Integration tests for CustomerService using local Supabase Docker

Run with: pytest tests/integration/test_customer_integration.py -v
Requires: Supabase Docker running (supabase start)
"""
import pytest
from app.services.customer_service import CustomerService
from app.schemas.request.customer import CartItemCreate


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_empty_cart(db_integration, test_user_data):
    """Test getting cart for user with no cart"""
    service = CustomerService(db_client=db_integration)
    
    # Use test user ID
    customer_id = test_user_data["email"]  # In real scenario, would be user UUID
    
    result = await service.get_cart(customer_id)
    
    assert result["success"] is True
    assert result["items"] == []
    assert result["total_amount"] == 0.0
    assert result["item_count"] == 0


@pytest.mark.asyncio
async def test_clear_cart(db_integration, test_user_data):
    """Test clearing user's cart"""
    service = CustomerService(db_integration)
    
    customer_id = test_user_data["email"]
    
    # Clear cart (should work even if empty)
    result = await service.clear_cart(customer_id)
    
    assert result["success"] is True
    
    # Verify cart is empty
    cart = await service.get_cart(customer_id)
    assert cart["items"] == []


@pytest.mark.asyncio  
async def test_get_salons_by_city(db_integration):
    """Test browsing salons by city"""
    service = CustomerService(db_integration)
    
    # Get salons in Mumbai (if any exist in test data)
    result = await service.get_salons_by_city(
        city="Mumbai",
        limit=10,
        offset=0
    )
    
    assert "salons" in result
    assert isinstance(result["salons"], list)
    assert "total" in result


@pytest.mark.asyncio
async def test_search_salons(db_integration):
    """Test searching salons"""
    service = CustomerService(db_integration)
    
    result = await service.search_salons(
        query="salon",
        city=None,
        limit=20
    )
    
    assert "salons" in result
    assert isinstance(result["salons"], list)


@pytest.mark.asyncio
async def test_get_nearby_salons(db_integration):
    """Test getting nearby salons by coordinates"""
    service = CustomerService(db_integration)
    
    # Mumbai coordinates
    result = await service.get_nearby_salons(
        latitude=19.0760,
        longitude=72.8777,
        radius_km=10.0,
        limit=10
    )
    
    assert "salons" in result
    assert isinstance(result["salons"], list)
