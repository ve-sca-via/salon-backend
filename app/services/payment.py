"""
Razorpay Payment Integration Service
Low-level gateway client. Handles:
- Razorpay order creation
- Payment signature verification
"""
import razorpay
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def resolve_razorpay_credentials(config_service, *, allow_env_fallback: bool = False):
    """
    Resolve Razorpay (key_id, key_secret) from system configuration.

    Single source of truth for credential lookup, shared by all services that
    talk to Razorpay. Reads from the `system_config` table via ConfigService;
    missing/unreadable values come back as ``None`` (ConfigService swallows the
    not-found/DB errors and returns the default).

    Args:
        config_service: A ConfigService instance bound to the request db client.
        allow_env_fallback: When True, fall back to the RAZORPAY_KEY_ID /
            RAZORPAY_KEY_SECRET env settings if the DB value is empty. Booking /
            registration payments keep this False (DB-only, strict); the product
            order flow uses True to support its env/dev-simulation mode.

    Returns:
        Tuple of (key_id, key_secret); either may be None if unresolved.
    """
    key_id = await config_service.get_config_value("razorpay_key_id")
    key_secret = await config_service.get_config_value("razorpay_key_secret")

    if allow_env_fallback:
        key_id = key_id or settings.RAZORPAY_KEY_ID
        key_secret = key_secret or settings.RAZORPAY_KEY_SECRET

    return key_id, key_secret


class RazorpayService:
    """Service class for Razorpay payment operations"""
    
    def __init__(self, razorpay_key_id: Optional[str] = None, razorpay_key_secret: Optional[str] = None):
        """
        Initialize Razorpay client
        
        Args:
            razorpay_key_id: Razorpay key ID (from database or env)
            razorpay_key_secret: Razorpay key secret (from database or env)
        """
        # Use provided keys or fall back to environment variables
        key_id = razorpay_key_id or settings.RAZORPAY_KEY_ID
        key_secret = razorpay_key_secret or settings.RAZORPAY_KEY_SECRET
        
        if not key_id or not key_secret:
            # Silently tolerate missing credentials until payment operations are invoked
            logger.debug("Razorpay credentials not configured. Payment operations will fail if called.")
            self.client = None
        else:
            try:
                # Mask credentials for logging (show first 4 and last 4 characters)
                masked_key_id = f"{key_id[:4]}...{key_id[-4:]}" if len(key_id) > 8 else "***"
                logger.info(f"Initializing Razorpay client with key_id: {masked_key_id}")
                
                self.client = razorpay.Client(auth=(key_id, key_secret))
                logger.info("Razorpay client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Razorpay client: {str(e)}")
                self.client = None
    
    def create_order(
        self,
        amount: float,
        currency: str = "INR",
        receipt: str = None,
        notes: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Create a Razorpay order
        
        Args:
            amount: Amount in rupees (will be converted to paise)
            currency: Currency code (default: INR)
            receipt: Receipt ID for your reference
            notes: Additional notes as key-value pairs
        
        Returns:
            Order details including order_id
        """
        if not self.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service not configured"
            )
        
        try:
            # Convert amount to paise (Razorpay expects smallest currency unit)
            amount_paise = int(amount * 100)
            
            order_data = {
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt or f"order_{int(razorpay.utils.now())}",
                "notes": notes or {}
            }
            
            order = self.client.order.create(data=order_data)
            logger.info(f"Razorpay order created: {order['id']}")
            
            return {
                "order_id": order["id"],
                "amount": amount,
                "amount_paise": amount_paise,
                "currency": order["currency"],
                "status": order["status"],
                "created_at": order["created_at"]
            }
            
        except razorpay.errors.BadRequestError as e:
            error_message = str(e).strip()
            if "authentication failed" in error_message.lower():
                logger.error("Razorpay authentication failed while creating order")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Payment service authentication failed. Please verify Razorpay credentials."
                )

            logger.error(f"Razorpay bad request: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payment request: {error_message}"
            )
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Payment order creation failed"
            )
    
    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> bool:
        """
        Verify Razorpay payment signature
        
        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay
        
        Returns:
            True if signature is valid, raises exception otherwise
        """
        if not self.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service not configured"
            )
        
        try:
            # Verify signature
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            
            self.client.utility.verify_payment_signature(params_dict)
            logger.info(f"Payment verified: {razorpay_payment_id}")
            return True
            
        except razorpay.errors.SignatureVerificationError:
            logger.error(f"Invalid payment signature: {razorpay_payment_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment signature"
            )
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Payment verification failed"
            )
