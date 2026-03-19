import os
import logging
from fastapi import APIRouter, Request, HTTPException, Query, Response, BackgroundTasks
from schemas.whatsapp import WhatsAppWebhookPayload
from services import whatsapp_service

import time
from collections import deque

logger = logging.getLogger(__name__)
router = APIRouter()

from services import state_manager


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
from schemas.whatsapp import Message

async def process_webhook_payload(payload: dict):
    """
    Background task to process the webhook payload.
    Layer 1 Gateway: Strips Meta wrappers via dictionary traversal and sends to Layer 2 Router.
    """
    print("\n[ALARM] WEBHOOK ENDPOINT HIT! [ALARM]")
    print(f"Raw Parsed Payload: {payload}\n")
    phone_number = None
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg_dict in messages:
                    phone_number = msg_dict.get("from")
                    # Strict validation ONLY on the core message object
                    try:
                        message_obj = Message(**msg_dict)
                        await process_inbound_message(message_obj)
                    except Exception as e:
                        logger.error(f"Pydantic parsing failed for inner message: {e}")
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
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp Webhook events.
    Accepts raw Request to bypass 422 Validation Errors on messy Meta outer wrappers.
    Immediately returns 200 OK and dispatches payload processing to a background task.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON from Meta webhook: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    # 1. Quick Extraction of WAMIDs for Deduplication
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg_dict in messages:
                    msg_id = msg_dict.get("id")
                    if msg_id and state_manager.is_duplicate_message(msg_id):
                        logger.warning(f"⚠️ Dropped duplicate webhook (wamid: {msg_id}). Discarding.")
                        return {"status": "success", "detail": "duplicate"}
    except Exception as e:
        logger.error(f"Error during quick deduplication check: {e}")

    # 2. Dispatch to Background Task (Async/Snappy response)
    background_tasks.add_task(process_webhook_payload, payload)
    return {"status": "success"}
