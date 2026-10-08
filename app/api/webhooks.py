"""
Webhook Endpoints - Thin Layer

    POST /webhooks/razorpay — Razorpay event deliveries

Unauthenticated by necessity: Razorpay has no token of ours. The HMAC in
`X-Razorpay-Signature`, computed over the exact request body with the webhook
secret, is the whole of the authentication, and nothing in the body is read before
it verifies.

Status codes matter more here than anywhere else in the API, because they are
instructions to Razorpay's retry machinery:

    200  received (handled, or deliberately ignored) — do not redeliver
    400  the signature did not verify — not ours, never redeliver
    503  we have no webhook secret configured — redeliver, this is our fault
    500  we failed while handling a verified event — redeliver

So the handler must not return 200 for work it did not do, and must not return an
error for an event it chose to ignore.

All business logic lives in RazorpayWebhookService (service layer pattern).
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response, status
from supabase import Client

from app.core.database import get_db_client
from app.core.rate_limit import limiter
from app.services.webhook_service import RazorpayWebhookService, WebhookSecretMissing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/razorpay", include_in_schema=False)
@limiter.exempt
async def razorpay_webhook(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    x_razorpay_signature: str = Header(None),
    db: Client = Depends(get_db_client),
):
    """
    Receive a Razorpay event — principally `payment.captured`.

    This is the only path by which a captured payment becomes a booking when the
    customer's browser never comes back (audit C-3). Exempt from the global rate
    limit on purpose: throttling this endpoint discards notifications about money
    that has already moved.
    """
    service = RazorpayWebhookService(db)

    try:
        secret = await service.resolve_secret()
    except WebhookSecretMissing as e:
        # 503, not 500: Razorpay retries, so the deliveries are not lost once
        # someone sets the secret.
        logger.error(f"Razorpay webhook rejected — {e}. Deliveries will be retried.")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_configured"}

    # The raw bytes, not a re-serialised model: the signature is over exactly what
    # was sent, and any round trip through a parser can change it.
    raw_body = await request.body()

    if not service.signature_is_valid(raw_body, x_razorpay_signature, secret):
        logger.warning(
            "Razorpay webhook rejected — signature did not verify "
            f"({len(raw_body)} byte body, signature header "
            f"{'present' if x_razorpay_signature else 'missing'})"
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"status": "invalid_signature"}

    event = service.parse_body(raw_body)
    if event is None:
        # Verified with our own secret, so it is genuinely from Razorpay, but
        # unparseable. Redelivering identical bytes will not help.
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"status": "invalid_body"}

    try:
        # The confirmation emails go behind the response, as they do on the
        # browser path: Resend retries up to four times with a 15 s timeout
        # (audit C-1), which would push this response well past the few seconds
        # Razorpay waits before calling it a failure and redelivering.
        result = await service.handle_event(event, background_tasks=background_tasks)
    except Exception as e:
        # Deliberately not swallowed: a 500 asks Razorpay to deliver again, which
        # is the only retry this path has.
        logger.error(
            f"Razorpay webhook handling failed for event {event.get('event')!r}: {e}",
            exc_info=True,
        )
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"status": "error"}

    logger.info(f"Razorpay webhook handled: {result}")
    return {"status": "ok", **result}
