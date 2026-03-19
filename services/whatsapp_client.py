import os
import httpx
import logging

logger = logging.getLogger(__name__)

async def send_whatsapp_message(payload: dict) -> bool:
    """
    Sends the dynamically constructed strict JSON payload dictionary 
    directly to Meta's WhatsApp Cloud API endpoints.
    Gracefully catches and logs all exceptions.
    """
    try:
        # Securely pull environment variables (support existing env mappings as fallback)
        token = os.getenv("WHATSAPP_ACCESS_TOKEN", os.getenv("WHATSAPP_API_TOKEN"))
        phone_id = os.getenv("PHONE_NUMBER_ID", os.getenv("WHATSAPP_PHONE_ID"))
        
        if not token or not phone_id:
            logger.error("Missing WhatsApp API credentials. Please configure .env parameters.")
            return False
            
        url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=8.0)
            
            if response.status_code != 200:
                logger.error(f"WhatsApp API Responded {response.status_code}: {response.text}")
                
            response.raise_for_status()
            logger.info("Successfully delivered webhook response payload to Meta API.")
            return True
            
    except httpx.HTTPError as e:
        logger.error(f"HTTP exception during WhatsApp API transmission: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected Python error in WhatsApp API transmission: {e}")
        return False
