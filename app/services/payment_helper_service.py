"""
Payment Helper Service - Unified Payments Table
Provides helper methods for working with the new payments table
"""
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PaymentHelperService:
    """Service for payment record operations with new unified payments table"""
    
    def __init__(self, db_client):
        self.db = db_client
    
    def get_booking_payment_status(self, booking_id: str) -> Dict[str, Any]:
        """
        Get comprehensive payment status for a booking.
        
        Args:
            booking_id: Booking UUID
            
        Returns:
            Dict with payment status details
        """
        try:
            response = self.db.table("payments").select("*").eq(
                "booking_id", booking_id
            ).is_("deleted_at", "null").execute()
            
            payments = response.data or []
            
            convenience_fee_payment = next(
                (p for p in payments if p["payment_type"] == "convenience_fee"), None
            )
            service_payment = next(
                (p for p in payments if p["payment_type"] == "service_payment"), None
            )
            
            return {
                "booking_id": booking_id,
                "convenience_fee_paid": convenience_fee_payment and convenience_fee_payment["status"] == "success",
                "convenience_fee_amount": convenience_fee_payment["amount"] if convenience_fee_payment else 0,
                "convenience_fee_paid_at": convenience_fee_payment.get("paid_at") if convenience_fee_payment else None,
                "service_paid": service_payment and service_payment["status"] == "success",
                "service_amount": service_payment["amount"] if service_payment else 0,
                "service_paid_at": service_payment.get("paid_at") if service_payment else None,
                "fully_paid": (
                    convenience_fee_payment and convenience_fee_payment["status"] == "success" and
                    service_payment and service_payment["status"] == "success"
                ),
                "total_paid": sum(
                    p["amount"] for p in payments if p["status"] == "success"
                ),
                "total_pending": sum(
                    p["amount"] for p in payments if p["status"] == "pending"
                )
            }
        except Exception as e:
            logger.error(f"Failed to get payment status for booking {booking_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve payment status"
            )
    
    def record_service_payment(
        self,
        booking_id: str,
        amount: float,
        payment_method: str,
        recorded_by: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record service payment made at salon.
        
        Args:
            booking_id: Booking UUID
            amount: Amount paid
            payment_method: 'cash', 'card', 'upi', etc.
            recorded_by: User ID recording payment (vendor/staff)
            notes: Optional payment notes
            
        Returns:
            Created payment record
        """
        try:
            # Get booking to find customer_id
            booking = self.db.table("bookings").select(
                "id, customer_id, service_price"
            ).eq("id", booking_id).single().execute()
            
            if not booking.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found"
                )
            
            # Check if service payment already exists
            existing = self.db.table("payments").select("id, status").eq(
                "booking_id", booking_id
            ).eq("payment_type", "service_payment").execute()
            
            if existing.data and existing.data[0]["status"] == "success":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Service payment already recorded for this booking"
                )
            
            # Update existing pending payment or create new
            if existing.data:
                # Update existing pending payment
                payment_data = {
                    "amount": amount,
                    "payment_method": payment_method,
                    "status": "success",
                    "paid_at": datetime.utcnow().isoformat(),
                    "notes": notes,
                    "updated_by": recorded_by
                }
                
                response = self.db.table("payments").update(payment_data).eq(
                    "id", existing.data[0]["id"]
                ).execute()
            else:
                # Create new payment record
                payment_data = {
                    "booking_id": booking_id,
                    "customer_id": booking.data["customer_id"],
                    "payment_type": "service_payment",
                    "amount": amount,
                    "currency": "INR",
                    "payment_method": payment_method,
                    "status": "success",
                    "paid_at": datetime.utcnow().isoformat(),
                    "notes": notes,
                    "created_by": recorded_by,
                    "updated_by": recorded_by
                }
                
                response = self.db.table("payments").insert(payment_data).execute()
            
            # Update deprecated service_paid flag in bookings for backward compatibility
            self.db.table("bookings").update({
                "service_paid": True,
                "updated_by": recorded_by
            }).eq("id", booking_id).execute()
            
            logger.info(f"Recorded service payment for booking {booking_id}: ₹{amount}")
            
            return {
                "success": True,
                "message": "Service payment recorded successfully",
                "payment": response.data[0] if response.data else None
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to record service payment: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to record service payment: {str(e)}"
            )
    
    def get_pending_service_payments(
        self,
        salon_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all pending service payments (to be paid at salon).
        
        Args:
            salon_id: Optional filter by salon
            limit: Max results to return
            
        Returns:
            List of pending payment records with booking details
        """
        try:
            query = self.db.table("payments").select(
                "*, bookings(id, booking_number, booking_date, booking_time, salon_id, salons(business_name))"
            ).eq("payment_type", "service_payment").eq("status", "pending").is_(
                "deleted_at", "null"
            )
            
            if salon_id:
                # This requires joining through bookings
                # Using a different approach - get payments first, filter after
                response = query.limit(limit * 2).execute()  # Get more to filter
                payments = [
                    p for p in (response.data or [])
                    if p.get("bookings", {}).get("salon_id") == salon_id
                ][:limit]
            else:
                response = query.limit(limit).execute()
                payments = response.data or []
            
            logger.info(f"Retrieved {len(payments)} pending service payments")
            return payments
            
        except Exception as e:
            logger.error(f"Failed to get pending service payments: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve pending payments"
            )
    
    def get_platform_revenue(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate platform revenue from convenience fees.
        
        Args:
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            
        Returns:
            Revenue summary
        """
        try:
            query = self.db.table("payments").select(
                "amount, paid_at, currency"
            ).eq("payment_type", "convenience_fee").eq("status", "success").is_(
                "deleted_at", "null"
            )
            
            if date_from:
                query = query.gte("paid_at", date_from)
            if date_to:
                query = query.lte("paid_at", date_to)
            
            response = query.execute()
            payments = response.data or []
            
            total_revenue = sum(float(p["amount"]) for p in payments)
            transaction_count = len(payments)
            avg_transaction = total_revenue / transaction_count if transaction_count > 0 else 0
            
            return {
                "total_revenue": total_revenue,
                "transaction_count": transaction_count,
                "avg_transaction": avg_transaction,
                "currency": "INR",
                "date_from": date_from,
                "date_to": date_to
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate platform revenue: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to calculate revenue"
            )
    
    def get_vendor_revenue(
        self,
        salon_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate vendor revenue from service payments.
        
        Args:
            salon_id: Salon UUID
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            
        Returns:
            Revenue summary for vendor
        """
        try:
            # Get all service payments for this salon's bookings
            query = self.db.table("payments").select(
                "amount, paid_at, bookings!inner(salon_id)"
            ).eq("payment_type", "service_payment").eq("status", "success").eq(
                "bookings.salon_id", salon_id
            ).is_("deleted_at", "null")
            
            if date_from:
                query = query.gte("paid_at", date_from)
            if date_to:
                query = query.lte("paid_at", date_to)
            
            response = query.execute()
            payments = response.data or []
            
            total_revenue = sum(float(p["amount"]) for p in payments)
            transaction_count = len(payments)
            avg_transaction = total_revenue / transaction_count if transaction_count > 0 else 0
            
            return {
                "salon_id": salon_id,
                "total_revenue": total_revenue,
                "transaction_count": transaction_count,
                "avg_transaction": avg_transaction,
                "currency": "INR",
                "date_from": date_from,
                "date_to": date_to
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate vendor revenue: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to calculate vendor revenue"
            )
