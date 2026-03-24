from __future__ import annotations

from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import APIRouter, Request, Response, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from schemas.whatsapp import Message
from services.router import process_inbound_message
from services import state_manager
from middleware.security import check_rate_limit, log_request

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Meta Webhook Verification
# ---------------------------------------------------------------------------

@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
) -> Response:
    """Responds to Meta's one-time webhook verification handshake."""
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "pantrypilot_secure_123")

    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("WhatsApp Webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("Webhook verification failed — bad token or mode.")
    return JSONResponse(status_code=403, content={"detail": "Verification failed"})


# ---------------------------------------------------------------------------
# Background payload processor
# ---------------------------------------------------------------------------

async def _process_webhook_payload(payload: dict) -> None:
    """
    Layer 1 Gateway: strips Meta envelope, deduplicates, rate-limits,
    logs access, then forwards each Message to the Layer 2 router.
    """
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg_dict in value.get("messages", []):
                    phone_number: str = msg_dict.get("from", "")
                    message_id: str = msg_dict.get("id", "")
                    timestamp: str = msg_dict.get("timestamp", "")

                    # Access log
                    log_request(message_id, phone_number, timestamp)

                    # Rate limit check — 429 is silent from Meta's perspective
                    # (we already returned 200); just skip processing.
                    if not check_rate_limit(phone_number):
                        logger.warning(
                            "Dropping message %s from %s — rate limit exceeded.",
                            message_id,
                            phone_number,
                        )
                        continue

                    try:
                        message_obj = Message(**msg_dict)
                        await process_inbound_message(message_obj)
                    except Exception as exc:
                        logger.error(
                            "Pydantic parsing failed for message %s: %s",
                            message_id,
                            exc,
                        )
    except Exception as exc:
        logger.error("Unhandled error in webhook background task: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# POST /webhook — returns 200 immediately, processes in background
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Receives Meta webhook events.  Returns 200 OK immediately so Meta
    does not retry; all processing happens in a BackgroundTask.
    Deduplication is checked synchronously before dispatching.
    """
    try:
        payload: dict = await request.json()
    except Exception as exc:
        logger.error("Failed to parse JSON from Meta webhook: %s", exc)
        return {"status": "error", "message": "invalid_json"}

    # --- Idempotent Firewall: deduplicate before spawning background work ---
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for msg_dict in change.get("value", {}).get("messages", []):
                    msg_id: str = msg_dict.get("id", "")
                    if msg_id and state_manager.is_duplicate_message(msg_id):
                        logger.warning("Dropped duplicate webhook (wamid: %s).", msg_id)
                        return {"status": "success", "detail": "duplicate"}
    except Exception as exc:
        logger.error("Error during deduplication check: %s", exc)

    background_tasks.add_task(_process_webhook_payload, payload)
    return {"status": "success"}
