"""
Razorpay Payment Integration Service
Handles all payment operations including:
- Vendor registration fee
- Customer booking convenience fee
- Payment verification
- Refunds
"""
import razorpay
import hmac
import hashlib
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class RazorpayService:
    """Service class for Razorpay payment operations"""
    
    def __init__(self):
        """Initialize Razorpay client"""
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            logger.warning("Razorpay credentials not configured")
            self.client = None
        else:
            self.client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
    
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
            logger.error(f"Razorpay bad request: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payment request: {str(e)}"
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
    
    def get_payment_details(self, payment_id: str) -> Dict[str, Any]:
        """
        Fetch payment details from Razorpay
        
        Args:
            payment_id: Razorpay payment ID
        
        Returns:
            Payment details
        """
        if not self.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service not configured"
            )
        
        try:
            payment = self.client.payment.fetch(payment_id)
            
            return {
                "payment_id": payment["id"],
                "order_id": payment.get("order_id"),
                "amount": payment["amount"] / 100,  # Convert from paise to rupees
                "currency": payment["currency"],
                "status": payment["status"],
                "method": payment.get("method"),
                "email": payment.get("email"),
                "contact": payment.get("contact"),
                "created_at": payment["created_at"],
                "captured": payment.get("captured", False)
            }
            
        except razorpay.errors.BadRequestError:
            logger.error(f"Payment not found: {payment_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        except Exception as e:
            logger.error(f"Failed to fetch payment: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch payment details"
            )
    
    def capture_payment(self, payment_id: str, amount: float) -> Dict[str, Any]:
        """
        Capture a payment (for manual capture)
        
        Args:
            payment_id: Razorpay payment ID
            amount: Amount to capture in rupees
        
        Returns:
            Captured payment details
        """
        if not self.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service not configured"
            )
        
        try:
            amount_paise = int(amount * 100)
            payment = self.client.payment.capture(payment_id, amount_paise)
            logger.info(f"Payment captured: {payment_id}")
            
            return {
                "payment_id": payment["id"],
                "amount": payment["amount"] / 100,
                "status": payment["status"],
                "captured": payment.get("captured", False)
            }
            
        except Exception as e:
            logger.error(f"Payment capture failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Payment capture failed"
            )
    
    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        notes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Refund a payment (full or partial)
        
        Args:
            payment_id: Razorpay payment ID
            amount: Amount to refund in rupees (None for full refund)
            notes: Additional notes
        
        Returns:
            Refund details
        """
        if not self.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment service not configured"
            )
        
        try:
            refund_data = {}
            
            if amount is not None:
                refund_data["amount"] = int(amount * 100)  # Convert to paise
            
            if notes:
                refund_data["notes"] = notes
            
            refund = self.client.payment.refund(payment_id, refund_data)
            logger.info(f"Refund created: {refund['id']} for payment {payment_id}")
            
            return {
                "refund_id": refund["id"],
                "payment_id": refund["payment_id"],
                "amount": refund["amount"] / 100,
                "currency": refund["currency"],
                "status": refund["status"],
                "created_at": refund["created_at"]
            }
            
        except Exception as e:
            logger.error(f"Refund failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Refund processing failed"
            )
    
    def verify_webhook_signature(
        self,
        webhook_body: str,
        webhook_signature: str
    ) -> bool:
        """
        Verify Razorpay webhook signature
        
        Args:
            webhook_body: Raw webhook body as string
            webhook_signature: Signature from X-Razorpay-Signature header
        
        Returns:
            True if signature is valid
        """
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            logger.warning("Webhook secret not configured")
            return False
        
        try:
            expected_signature = hmac.new(
                settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
                webhook_body.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, webhook_signature)
            
        except Exception as e:
            logger.error(f"Webhook verification failed: {str(e)}")
            return False
    
    def create_registration_fee_order(
        self,
        vendor_id: str,
        salon_id: str,
        amount: float
    ) -> Dict[str, Any]:
        """
        Create order for vendor registration fee
        
        Args:
            vendor_id: Vendor's user ID
            salon_id: Salon ID
            amount: Registration fee amount
        
        Returns:
            Order details
        """
        return self.create_order(
            amount=amount,
            receipt=f"reg_{salon_id}_{int(razorpay.utils.now())}",
            notes={
                "payment_type": "registration_fee",
                "vendor_id": vendor_id,
                "salon_id": salon_id
            }
        )
    
    def create_booking_order(
        self,
        customer_id: str,
        booking_id: str,
        amount: float,
        convenience_fee: float
    ) -> Dict[str, Any]:
        """
        Create order for booking payment
        
        Args:
            customer_id: Customer's user ID
            booking_id: Booking ID
            amount: Service amount
            convenience_fee: Convenience fee amount
        
        Returns:
            Order details
        """
        total_amount = amount + convenience_fee
        
        return self.create_order(
            amount=total_amount,
            receipt=f"booking_{booking_id}",
            notes={
                "payment_type": "booking",
                "customer_id": customer_id,
                "booking_id": booking_id,
                "service_amount": amount,
                "convenience_fee": convenience_fee
            }
        )
    
    def get_key_id(self) -> str:
        """
        Get Razorpay Key ID for frontend
        
        Returns:
            Razorpay Key ID (public key)
        """
        return settings.RAZORPAY_KEY_ID


# Create singleton instance
razorpay_service = RazorpayService()
