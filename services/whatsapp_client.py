import base64
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v17.0"


def _credentials() -> tuple[str, str]:
    """
    Returns (token, phone_id) from environment variables.
    Supports both the v1 and v2 env-var naming conventions.
    Raises RuntimeError if either value is missing.
    """
    token = os.getenv("WHATSAPP_ACCESS_TOKEN") or os.getenv("WHATSAPP_API_TOKEN")
    phone_id = os.getenv("PHONE_NUMBER_ID") or os.getenv("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        raise RuntimeError(
            "Missing WhatsApp credentials. Set WHATSAPP_ACCESS_TOKEN and PHONE_NUMBER_ID."
        )
    return token, phone_id


async def send_whatsapp_message(payload: dict) -> bool:
    """
    POSTs a pre-built JSON payload to the Meta Graph API.
    Returns True on success, False on any error.
    """
    try:
        token, phone_id = _credentials()
        url = f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=8.0)
            if response.status_code != 200:
                logger.error("WhatsApp API %d: %s", response.status_code, response.text)
            response.raise_for_status()
        logger.info("Message delivered to Meta API.")
        return True
    except RuntimeError as exc:
        logger.error("Credential error: %s", exc)
        return False
    except httpx.HTTPError as exc:
        logger.error("HTTP error sending WhatsApp message: %s", exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error sending WhatsApp message: %s", exc)
        return False


async def download_media_base64(media_id: str) -> str:
    """
    Downloads a media file from Meta's Graph API and returns it as a
    base64-encoded string.  Returns an empty string on any failure.
    """
    try:
        token, _ = _credentials()
    except RuntimeError as exc:
        logger.error("Credential error for media download: %s", exc)
        return ""

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient() as client:
            # Step 1 — resolve media URL
            info_resp = await client.get(
                f"https://graph.facebook.com/{_GRAPH_API_VERSION}/{media_id}",
                headers=headers,
                timeout=8.0,
            )
            info_resp.raise_for_status()
            media_url: str = info_resp.json().get("url", "")
            if not media_url:
                logger.error("No URL in media info response for %s.", media_id)
                return ""

            # Step 2 — download binary content
            dl_resp = await client.get(media_url, headers=headers, timeout=15.0)
            dl_resp.raise_for_status()

        return base64.b64encode(dl_resp.content).decode("utf-8")

    except Exception as exc:
        logger.error("Failed to download media %s: %s", media_id, exc)
        return ""
