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
                        elif msg_type == "audio" and message.audio:
                            await whatsapp_service.process_audio_message(
                                phone_number=phone_number,
                                audio_id=message.audio.id,
                                mime_type=message.audio.mime_type
                            )
                        elif msg_type == "image" and message.image:
                            await whatsapp_service.process_image_message(
                                phone_number=phone_number,
                                image_id=message.image.id,
                                mime_type=message.image.mime_type
                            )
                        else:
                            logger.info(f"Received unhandled message type: {msg_type}")
    except Exception as e:
        logger.error(f"Error processing webhook payload: {e}")

@router.post("/webhook")
async def handle_webhook(payload: WhatsAppWebhookPayload, background_tasks: BackgroundTasks):
    """
    Handle incoming WhatsApp Webhook events.
    Immediately returns 200 OK and dispatches payload processing to a background task.
    """
    background_tasks.add_task(process_webhook_payload, payload)
    return {"status": "success"}
