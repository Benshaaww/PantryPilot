import os
import httpx
import logging
import base64

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

async def download_media_base64(media_id: str) -> str:
    """
    Downloads media from Meta's Graph API safely in two steps and returns a base64 string.
    Returns an empty string if it fails to resolve securely.
    """
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", os.getenv("WHATSAPP_API_TOKEN"))
    if not token:
        logger.error("Missing WhatsApp API credentials for media download.")
        return ""
        
    try:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            # Step 1: Get the Media URL reference
            media_info_url = f"https://graph.facebook.com/v17.0/{media_id}"
            info_response = await client.get(media_info_url, headers=headers, timeout=8.0)
            info_response.raise_for_status()
            
            media_url = info_response.json().get("url")
            if not media_url:
                logger.error(f"No media URL returned for media_id {media_id}.")
                return ""
                
            # Step 2: Download the binary payload natively
            download_response = await client.get(media_url, headers=headers, timeout=15.0)
            download_response.raise_for_status()
            
            # Encode payload into structural Base64 array
            encoded_bytes = base64.b64encode(download_response.content)
            return encoded_bytes.decode('utf-8')
            
    except Exception as e:
        logger.error(f"Failed to download/encode media {media_id}: {e}")
        return ""
