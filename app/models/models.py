from sqlalchemy import Column, Integer, String, DECIMAL, Text, TIMESTAMP, Boolean, JSON, Date, UUID, CheckConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class Salon(Base):
    __tablename__ = "salons"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(UUID, nullable=True)
    status = Column(String, default="pending", nullable=False)
    
    # Basic Info
    name = Column(Text, nullable=False)
    description = Column(Text)
    email = Column(Text)
    phone = Column(Text, nullable=False)
    
    # Address
    address_line1 = Column(Text, nullable=False)
    address_line2 = Column(Text)
    city = Column(Text, nullable=False)
    state = Column(Text, nullable=False)
    pincode = Column(Text, nullable=False)
    
    # Geolocation (will add via migration)
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))
    
    # Business Hours (JSONB)
    business_hours = Column(JSON)
    
    # Media
    cover_image = Column(Text)
    logo = Column(Text)
    images = Column(JSON, default=list)
    
    # Ratings
    rating = Column(DECIMAL(2, 1), default=0)
    total_reviews = Column(Integer, default=0)
    total_bookings = Column(Integer, default=0)
    
    # Features
    amenities = Column(JSON, default=list)
    specialties = Column(JSON, default=list)
    
    # Submission Info
    submitted_by = Column(UUID)
    submitted_at = Column(TIMESTAMP(timezone=True))
    
    # Approval Info
    reviewed_by = Column(UUID)
    reviewed_at = Column(TIMESTAMP(timezone=True))
    rejection_reason = Column(Text)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class SalonService(Base):
    __tablename__ = "salon_services"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    salon_id = Column(Integer, nullable=False)
    
    # Service Info
    name = Column(Text, nullable=False)
    description = Column(Text)
    category = Column(Text, nullable=False)
    
    # Pricing
    price = Column(DECIMAL(10, 2), nullable=False)
    discounted_price = Column(DECIMAL(10, 2))
    
    # Duration
    duration_minutes = Column(Integer, nullable=False)
    is_available = Column(Boolean, default=True)
    
    # Media
    image = Column(Text)
    
    # Stats
    booking_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(UUID, primary_key=True)
    user_id = Column(UUID, nullable=False)
    salon_id = Column(Integer, nullable=False)
    salon_name = Column(Text, nullable=False)
    
    # Booking details
    booking_date = Column(Date, nullable=False)
    booking_time = Column(Text, nullable=False)
    status = Column(String, default="pending")
    
    # Services (JSONB)
    services = Column(JSON, nullable=False, default=list)
    
    # Pricing
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    discount_applied = Column(DECIMAL(10, 2), default=0)
    final_amount = Column(DECIMAL(10, 2), nullable=False)
    
    # Payment
    payment_status = Column(String, default="pending")
    payment_method = Column(Text, default="pay_after_service")
    
    # Additional
    notes = Column(Text)
    cancellation_reason = Column(Text)
    
    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(TIMESTAMP(timezone=True))
    cancelled_at = Column(TIMESTAMP(timezone=True))
