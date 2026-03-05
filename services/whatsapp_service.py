import os
import httpx
import logging
from agents import household_agent
from db import grocery_repo
from schemas.intent_schemas import HouseholdIntentPayload

logger = logging.getLogger(__name__)

async def send_whatsapp_message(to_number: str, message: str):
    """
    Sends an outbound WhatsApp message using Meta's Graph API.
    """
    try:
        token = os.getenv("WHATSAPP_API_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_ID")
        
        if not token or not phone_id:
            logger.error("Missing WHATSAPP_API_TOKEN or WHATSAPP_PHONE_ID for outbound message.")
            return False
            
        url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Successfully sent WhatsApp message to {to_number}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to send outbound WhatsApp message: {e}")
        print(f"[ERROR] Failed to send outbound WhatsApp message: {e}")
        return False

async def route_payload_to_db(payload: HouseholdIntentPayload):
    """
    Takes the structured intent payload from the LangChain agent 
    and iterates through all extracted items, sending them to the 
    repository for smart deduplication.
    """
    items_processed = 0
    
    # 1. Standard Groceries
    if payload.standard_groceries:
        for item in payload.standard_groceries:
            await grocery_repo.add_or_update_item(item)
            items_processed += 1
            
    # 2. Recipes
    if payload.recipe_extractions:
        for recipe in payload.recipe_extractions:
            for item in recipe.ingredients:
                await grocery_repo.add_or_update_item(item)
                items_processed += 1
                
    # 3. Calendar Predictions
    if payload.calendar_predictions:
        for event in payload.calendar_predictions:
            for item in event.predicted_items:
                await grocery_repo.add_or_update_item(item)
                items_processed += 1
                
    logger.info(f"Successfully routed {items_processed} items to the database.")

async def process_text_message(phone_number: str, text: str):
    """
    Processes a text message via LangChain/ReAct.
    Converts text to an extracted intent and maps it to groceries or a calendar event,
    then persists to the database.
    """
    logger.info(f"Processing text message from {phone_number}: {text}")
    print(f"\n[TRACE] whatsapp_service.process_text_message received text: '{text}' [TRACE]")
    
    # Send natural language to the Intent Engine
    intent_payload = await household_agent.process_user_intent(text)
    
    if intent_payload:
        logger.info(f"Agent determined intent: {intent_payload.summary}")
        print(f"[TRACE] Agent successfully returned intent_payload! [TRACE]")
        # Route the structured items to the Supabase repository
        await route_payload_to_db(intent_payload)
    else:
        logger.warning(f"Agent failed to parse intent for message: {text}")
        print(f"[TRACE] Agent failed to parse intent, returned None! [TRACE]")

async def process_audio_message(phone_number: str, audio_id: str, mime_type: str):
    """
    Placeholder logic for processing an audio message.
    Downloads the audio from Meta, transcribes via Whisper (temp=0.0), and processes intent.
    Currently routes a mock transcribed string to the intent engine.
    """
    logger.info(f"Processing audio message from {phone_number}, audio_id: {audio_id}")
    # TODO: Implement actual audio download and Whisper transcription here.
    # mock_transcription = whisper_service.transcribe(audio_file)
    mock_transcription = "We need eggs and flour for the party this weekend."
    
    logger.info(f"Mock Audio Transcription: '{mock_transcription}'")
    
    intent_payload = await household_agent.process_user_intent(mock_transcription)
    if intent_payload:
        await route_payload_to_db(intent_payload)

async def process_image_message(phone_number: str, image_id: str, mime_type: str):
    """
    Placeholder logic for processing an image message.
    Downloads the image and passes to OpenAI vision for generic item extraction.
    """
    logger.info(f"Processing image message from {phone_number}, image_id: {image_id}")
    # TODO: Implement actual image download and Vision extraction.
