"""
Custom Exceptions for Better Error Handling
Provides structured error responses without leaking internal details
"""
from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class AppException(HTTPException):
    """Base exception class for application errors"""

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code or f"ERR_{status_code}"


# =====================================================
# AUTHENTICATION EXCEPTIONS
# =====================================================

class AuthenticationError(AppException):
    """Authentication failed"""
    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="AUTH_REQUIRED"
        )


class AuthorizationError(AppException):
    """Insufficient permissions"""
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="INSUFFICIENT_PERMISSIONS"
        )


class TokenExpiredError(AppException):
    """JWT token has expired"""
    def __init__(self, detail: str = "Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="TOKEN_EXPIRED"
        )


# =====================================================
# RESOURCE EXCEPTIONS
# =====================================================

class NotFoundError(AppException):
    """Resource not found"""
    def __init__(self, resource: str, resource_id: str = None):
        detail = f"{resource} not found"
        if resource_id:
            detail += f" with ID {resource_id}"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code="RESOURCE_NOT_FOUND"
        )


class AlreadyExistsError(AppException):
    """Resource already exists"""
    def __init__(self, resource: str, detail: str = None):
        detail = detail or f"{resource} already exists"
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="RESOURCE_EXISTS"
        )


# =====================================================
# VALIDATION EXCEPTIONS
# =====================================================

class ValidationError(AppException):
    """Input validation failed"""
    def __init__(self, detail: str, field: str = None):
        error_detail = f"Validation error"
        if field:
            error_detail += f" for field '{field}'"
        error_detail += f": {detail}"

        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
            error_code="VALIDATION_ERROR"
        )


class InvalidDataError(AppException):
    """Invalid data provided"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="INVALID_DATA"
        )


# =====================================================
# BUSINESS LOGIC EXCEPTIONS
# =====================================================

class BusinessRuleError(AppException):
    """Business rule violation"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="BUSINESS_RULE_VIOLATION"
        )


class BookingConflictError(AppException):
    """Booking time slot conflict"""
    def __init__(self, detail: str = "Time slot already booked"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="BOOKING_CONFLICT"
        )


class PaymentError(AppException):
    """Payment processing failed"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
            error_code="PAYMENT_FAILED"
        )


class CartError(AppException):
    """Shopping cart operation failed"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="CART_ERROR"
        )


# =====================================================
# EXTERNAL SERVICE EXCEPTIONS
# =====================================================

class ExternalServiceError(AppException):
    """External service (email, payment, etc.) failed"""
    def __init__(self, service: str, detail: str):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{service} service error: {detail}",
            error_code="EXTERNAL_SERVICE_ERROR"
        )


# =====================================================
# DATABASE EXCEPTIONS
# =====================================================

class DatabaseError(AppException):
    """Database operation failed"""
    def __init__(self, operation: str, detail: str = None):
        detail = detail or f"Database {operation} failed"
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="DATABASE_ERROR"
        )


# =====================================================
# CONFIGURATION EXCEPTIONS
# =====================================================

class ConfigurationError(AppException):
    """Configuration error"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="CONFIG_ERROR"
        )