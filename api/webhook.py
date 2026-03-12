import os
import logging
from fastapi import APIRouter, Request, HTTPException, Query, Response, BackgroundTasks
from schemas.whatsapp import WhatsAppWebhookPayload
from services import whatsapp_service

logger = logging.getLogger(__name__)
router = APIRouter()

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

async def process_webhook_payload(payload: WhatsAppWebhookPayload):
    """
    Background task to process the webhook payload.
    """
    print("\n[ALARM] WEBHOOK ENDPOINT HIT! [ALARM]")
    print(f"Raw Parsed Payload: {payload}\n")
    phone_number = None
    try:
        for entry in payload.entry:
            for change in entry.changes:
                value = change.value
                if value.messages:
                    for message in value.messages:
                        phone_number = message.from_
                        msg_type = message.type
                        
                        if msg_type == "text" and message.text:
                            await whatsapp_service.process_text_message(
                                phone_number=phone_number,
                                text=message.text.body
                            )
                        elif msg_type in ["audio", "image", "sticker"]:
                            # MODULE 4: Unsupported Media Bypass
                            await whatsapp_service.send_whatsapp_message(
                                phone_number,
                                "I'm still learning to process media! For now, please type out your grocery requests."
                            )
                        elif msg_type == "interactive" and message.interactive:
                            if message.interactive.type == "button_reply" and message.interactive.button_reply:
                                await whatsapp_service.process_interactive_message(
                                    phone_number=phone_number,
                                    payload_id=message.interactive.button_reply.id
                                )
                        else:
                            logger.info(f"Received unhandled message type: {msg_type}")
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
    """
    background_tasks.add_task(process_webhook_payload, payload)
    return {"status": "success"}
