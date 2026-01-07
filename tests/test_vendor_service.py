"""
Unit tests for VendorService

Tests the service layer in isolation using mocked database calls.
This demonstrates proper pytest patterns for testing FastAPI services.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi import HTTPException

from app.services.vendor_service import VendorService
from app.schemas import ServiceCreate, ServiceUpdate


# =====================================================
# FIXTURES
# =====================================================

@pytest.fixture
def vendor_service(mock_db):
    """Create VendorService instance for testing"""
    return VendorService(db_client=mock_db)


@pytest.fixture
def mock_db():
    """Mock Supabase database client"""
    return MagicMock()


@pytest.fixture
def sample_vendor_id():
    """Sample vendor user ID"""
    return "vendor-123-uuid"


@pytest.fixture
def sample_salon_id():
    """Sample salon ID"""
    return 42


@pytest.fixture
def sample_service_create():
    """Sample service creation data"""
    return ServiceCreate(
        name="Haircut",
        description="Professional haircut service",
        duration_minutes=30,
        price=500.0,
        category_id="cat-123-uuid",
        image_url="https://example.com/haircut.jpg"
    )


@pytest.fixture
def sample_service_update():
    """Sample service update data"""
    return ServiceUpdate(
        name="Premium Haircut",
        price=750.0
    )


# =====================================================
# GET SALON TESTS
# =====================================================

@pytest.mark.asyncio
async def test_get_vendor_salon_success(vendor_service, mock_db, sample_vendor_id):
    """Test successful salon retrieval"""
    # Arrange
    mock_salon_data = {
        "id": 42,
        "vendor_id": sample_vendor_id,
        "business_name": "Test Salon",
        "city": "Mumbai"
    }
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = mock_salon_data
    
    # Act
    result = await vendor_service.get_vendor_salon(sample_vendor_id)
    
    # Assert
    assert result == mock_salon_data
    assert result["business_name"] == "Test Salon"
    mock_db.table.assert_called_with("salons")


@pytest.mark.asyncio
async def test_get_vendor_salon_not_found(vendor_service, mock_db, sample_vendor_id):
    """Test salon not found raises HTTPException"""
    # Arrange
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    
    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await vendor_service.get_vendor_salon(sample_vendor_id)
    
    assert exc_info.value.status_code == 404
    assert "Salon not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_vendor_salon_id_success(vendor_service, mock_db, sample_vendor_id, sample_salon_id):
    """Test successful salon ID retrieval"""
    # Arrange
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": sample_salon_id
    }
    
    # Act
    result = await vendor_service.get_vendor_salon_id(sample_vendor_id)
    
    # Assert
    assert result == sample_salon_id
    mock_db.table.assert_called_with("salons")


# =====================================================
# GET SERVICES TESTS
# =====================================================

@pytest.mark.asyncio
async def test_get_services_success(vendor_service, mock_db, sample_vendor_id, sample_salon_id):
    """Test successful services retrieval"""
    # Arrange
    # Mock get_vendor_salon_id
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": sample_salon_id
    }
    
    # Mock services query
    mock_services = [
        {
            "id": "service-1",
            "name": "Haircut",
            "price": 500.0,
            "salon_id": sample_salon_id,
            "service_categories": {"name": "Hair"}
        },
        {
            "id": "service-2",
            "name": "Massage",
            "price": 1000.0,
            "salon_id": sample_salon_id,
            "service_categories": {"name": "Spa"}
        }
    ]
    
    # Create a separate mock for the services query
    services_mock = MagicMock()
    services_mock.execute.return_value.data = mock_services
    
    # Setup the table mock to return different results for different calls
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "services":
            return MagicMock(
                select=MagicMock(return_value=MagicMock(
                    eq=MagicMock(return_value=MagicMock(
                        order=MagicMock(return_value=services_mock)
                    ))
                ))
            )
    
    mock_db.table.side_effect = table_side_effect
    
    # Act
    result = await vendor_service.get_services(sample_vendor_id)
    
    # Assert
    assert len(result) == 2
    assert result[0]["name"] == "Haircut"
    assert result[1]["name"] == "Massage"


@pytest.mark.asyncio
async def test_get_services_empty_list(vendor_service, mock_db, sample_vendor_id, sample_salon_id):
    """Test services retrieval with no services"""
    # Arrange
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "services":
            services_mock = MagicMock()
            services_mock.execute.return_value.data = []
            return MagicMock(
                select=MagicMock(return_value=MagicMock(
                    eq=MagicMock(return_value=MagicMock(
                        order=MagicMock(return_value=services_mock)
                    ))
                ))
            )
    
    mock_db.table.side_effect = table_side_effect
    
    # Act
    result = await vendor_service.get_services(sample_vendor_id)
    
    # Assert
    assert result == []


# =====================================================
# CREATE SERVICE TESTS
# =====================================================

@pytest.mark.asyncio
async def test_create_service_success(
    vendor_service,
    mock_db,
    sample_vendor_id,
    sample_salon_id,
    sample_service_create
):
    """Test successful service creation"""
    # Arrange
    created_service = {
        "id": "service-new-123",
        "name": "Haircut",
        "price": 500.0,
        "salon_id": sample_salon_id,
        "category_id": "cat-123-uuid"
    }
    
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "service_categories":
            cat_mock = MagicMock()
            cat_mock.select.return_value.eq.return_value.execute.return_value.data = [{"id": "cat-123-uuid"}]
            return cat_mock
        elif table_name == "services":
            service_mock = MagicMock()
            service_mock.insert.return_value.execute.return_value.data = [created_service]
            return service_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act
    result = await vendor_service.create_service(sample_vendor_id, sample_service_create)
    
    # Assert
    assert result["id"] == "service-new-123"
    assert result["name"] == "Haircut"
    assert result["salon_id"] == sample_salon_id


@pytest.mark.asyncio
async def test_create_service_invalid_category(
    vendor_service,
    mock_db,
    sample_vendor_id,
    sample_salon_id,
    sample_service_create
):
    """Test service creation with invalid category"""
    # Arrange
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "service_categories":
            cat_mock = MagicMock()
            cat_mock.select.return_value.eq.return_value.execute.return_value.data = []  # Empty = invalid
            return cat_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await vendor_service.create_service(sample_vendor_id, sample_service_create)
    
    assert exc_info.value.status_code == 400
    assert "Invalid category_id" in exc_info.value.detail


# =====================================================
# UPDATE SERVICE TESTS
# =====================================================

@pytest.mark.asyncio
async def test_update_service_success(
    vendor_service,
    mock_db,
    sample_vendor_id,
    sample_salon_id,
    sample_service_update
):
    """Test successful service update"""
    # Arrange
    service_id = "service-123"
    updated_service = {
        "id": service_id,
        "name": "Premium Haircut",
        "price": 750.0,
        "salon_id": sample_salon_id
    }
    
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "services":
            service_mock = MagicMock()
            # Mock ownership check
            service_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"salon_id": sample_salon_id}
            # Mock update
            service_mock.update.return_value.eq.return_value.execute.return_value.data = [updated_service]
            return service_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act
    result = await vendor_service.update_service(sample_vendor_id, service_id, sample_service_update)
    
    # Assert
    assert result["name"] == "Premium Haircut"
    assert result["price"] == 750.0


@pytest.mark.asyncio
async def test_update_service_not_owned(
    vendor_service,
    mock_db,
    sample_vendor_id,
    sample_service_update
):
    """Test updating service not owned by vendor"""
    # Arrange
    service_id = "service-123"
    other_salon_id = 999
    
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": 42}
            return salon_mock
        elif table_name == "services":
            service_mock = MagicMock()
            service_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"salon_id": other_salon_id}
            return service_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await vendor_service.update_service(sample_vendor_id, service_id, sample_service_update)
    
    assert exc_info.value.status_code == 404
    assert "access denied" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_update_service_no_fields(
    vendor_service,
    mock_db,
    sample_vendor_id,
    sample_salon_id
):
    """Test updating service with no fields provided"""
    # Arrange
    service_id = "service-123"
    empty_update = ServiceUpdate()
    
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "services":
            service_mock = MagicMock()
            service_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"salon_id": sample_salon_id}
            return service_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await vendor_service.update_service(sample_vendor_id, service_id, empty_update)
    
    assert exc_info.value.status_code == 400
    assert "No fields provided" in exc_info.value.detail


# =====================================================
# DELETE SERVICE TESTS
# =====================================================

@pytest.mark.asyncio
async def test_delete_service_success(
    vendor_service,
    mock_db,
    sample_vendor_id,
    sample_salon_id
):
    """Test successful service deletion"""
    # Arrange
    service_id = "service-123"
    
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": sample_salon_id}
            return salon_mock
        elif table_name == "services":
            service_mock = MagicMock()
            # Mock ownership check
            service_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"salon_id": sample_salon_id}
            # Mock delete
            service_mock.delete.return_value.eq.return_value.execute.return_value = MagicMock()
            return service_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act
    result = await vendor_service.delete_service(sample_vendor_id, service_id)
    
    # Assert
    assert result["success"] is True
    assert "deleted successfully" in result["message"].lower()


@pytest.mark.asyncio
async def test_delete_service_not_owned(
    vendor_service,
    mock_db,
    sample_vendor_id
):
    """Test deleting service not owned by vendor"""
    # Arrange
    service_id = "service-123"
    other_salon_id = 999
    
    def table_side_effect(table_name):
        if table_name == "salons":
            salon_mock = MagicMock()
            salon_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"id": 42}
            return salon_mock
        elif table_name == "services":
            service_mock = MagicMock()
            service_mock.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {"salon_id": other_salon_id}
            return service_mock
    
    mock_db.table.side_effect = table_side_effect
    
    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await vendor_service.delete_service(sample_vendor_id, service_id)
    
    assert exc_info.value.status_code == 404
    assert "access denied" in exc_info.value.detail.lower()
