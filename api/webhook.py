import os
import logging
from fastapi import APIRouter, Request, HTTPException, Query, Response, BackgroundTasks
from schemas.whatsapp import WhatsAppWebhookPayload
from services import whatsapp_service

import time
from collections import deque

logger = logging.getLogger(__name__)
router = APIRouter()

# --- MODULE: PRODUCTION-GRADE DEDUPLICATION ---
# Store the last 500 message IDs with their timestamps to prevent replay/retry loops.
PROCESSED_WAMIDS = {}
WAMID_EXPIRY_SECONDS = 60
WAMID_CLEANUP_THRESHOLD = 500

def is_duplicate(wamid: str) -> bool:
    """Checks if a wamid has been processed in the last 60 seconds."""
    now = time.time()
    
    # Prune old entries if the cache gets too large
    if len(PROCESSED_WAMIDS) > WAMID_CLEANUP_THRESHOLD:
        expired = [wid for wid, ts in PROCESSED_WAMIDS.items() if now - ts > WAMID_EXPIRY_SECONDS]
        for wid in expired:
            del PROCESSED_WAMIDS[wid]

    if wamid in PROCESSED_WAMIDS:
        if now - PROCESSED_WAMIDS[wamid] < WAMID_EXPIRY_SECONDS:
            return True
    
    PROCESSED_WAMIDS[wamid] = now
    return False


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Meta Webhook Verification Endpoint.
    """
    VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "pantrypilot_secure_123")
    
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("WhatsApp Webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")
    
    raise HTTPException(status_code=403, detail="Verification failed")

from services.router import process_inbound_message

async def process_webhook_payload(payload: WhatsAppWebhookPayload):
    """
    Background task to process the webhook payload.
    Layer 1 Gateway: Strips Meta wrappers and sends to Layer 2 Router.
    """
    print("\n[ALARM] WEBHOOK ENDPOINT HIT! [ALARM]")
    print(f"Raw Parsed Payload: {payload.model_dump()}\n")
    phone_number = None
    try:
        for entry in payload.entry:
            for change in entry.changes:
                value = change.value
                if value.messages:
                    for message in value.messages:
                        phone_number = message.from_
                        # Handoff cleanly extracted message payload to Layer 2 Router
                        await process_inbound_message(message)
    except Exception as e:
        logger.error(f"Error processing webhook payload: {e}", exc_info=True)
        if phone_number:
            try:
                await whatsapp_service.send_whatsapp_message(
                    phone_number,
                    "🔧 PantryPilot is stretching its gears! I hit a small snag processing that. Could you try again or type 'Help'?"
                )
            except Exception as nested_e:
                logger.error(f"Failed to send fallback error message: {nested_e}")

@router.post("/webhook")
async def handle_webhook(payload: WhatsAppWebhookPayload, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp Webhook events.
    Immediately returns 200 OK and dispatches payload processing to a background task.
    Includes production-grade deduplication for Meta retries.
    """
    # 1. Quick Extraction of WAMIDs for Deduplication
    try:
        for entry in payload.entry:
            for change in entry.changes:
                if change.value.messages:
                    for message in change.value.messages:
                        if is_duplicate(message.id):
                            logger.info(f"Duplicate message detected (wamid: {message.id}). Discarding.")
                            return {"status": "success", "detail": "duplicate"}
    except Exception as e:
        logger.error(f"Error during quick deduplication check: {e}")

    # 2. Dispatch to Background Task (Async/Snappy response)
    background_tasks.add_task(process_webhook_payload, payload)
    return {"status": "success"}
