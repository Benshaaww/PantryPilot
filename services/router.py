import logging
from schemas.whatsapp import Message
from services import whatsapp_service

logger = logging.getLogger(__name__)

async def process_inbound_message(message: Message):
    """
    Layer 2: The Deterministic Router.
    Routes incoming standard text strings and interactive message payloads
    based on a strict finite state machine approach.
    """
    phone_number = message.from_
    msg_type = message.type
    
    if msg_type == "text" and message.text:
        text_content = message.text.body
        await route_text_message(phone_number, text_content)
        
    elif msg_type == "interactive" and message.interactive:
        interactive = message.interactive
        payload_id = None
        
        # Extract ID depending on if it's a button or list selection
        if interactive.type == "button_reply" and interactive.button_reply:
            payload_id = interactive.button_reply.id
        elif interactive.type == "list_reply" and interactive.list_reply:
            payload_id = interactive.list_reply.id
            
        if payload_id:
            await route_interactive_message(phone_number, payload_id)
        else:
            logger.warning("Interactive message received but no payload_id extracted.")
            await whatsapp_service.send_whatsapp_message(
                phone_number,
                "Sorry, I couldn't process your interactive selection."
            )
            
    elif msg_type in ["audio", "image", "sticker"]:
        # Unsupported Media Bypass
        await whatsapp_service.send_whatsapp_message(
            phone_number,
            "I'm still learning to process media! For now, please type out your grocery requests."
        )
    else:
        logger.info(f"Received unhandled message type: {msg_type}")

async def route_interactive_message(phone_number: str, payload_id: str):
    """
    Deterministic routing for interactive messages (buttons and lists).
    Pure Python match/case state machine.
    """
    logger.info(f"Routing interactive payload: '{payload_id}' for {phone_number}")

    # The deterministic router overrides or intercepts specific payload IDs here.
    if payload_id == 'CMD_VIEW_PANTRY':
        await _dummy_get_inventory(phone_number)
    elif payload_id == 'CMD_ADD_ITEM':
        await _dummy_add_item(phone_number)
    else:
        # Fallback to existing interactive logic for LangChain or standard menu intents if not statically overridden.
        await whatsapp_service.process_interactive_message(phone_number, payload_id)

async def route_text_message(phone_number: str, text: str):
    """
    Default routing for standard text messages.
    """
    logger.info(f"Routing text message from {phone_number} to LangChain engine")
    # For standard text strings, default to LangChain agent (via standard process)
    await whatsapp_service.process_text_message(phone_number, text)

async def _dummy_get_inventory(phone_number: str):
    """Dummy static function to simulate retrieving pantry inventory."""
    logger.info(f"Executing deterministic intent CMD_VIEW_PANTRY for {phone_number}")
    await whatsapp_service.send_whatsapp_message(
        phone_number,
        "Here is your pantry inventory: \n- 🍎 Apples\n- 🍞 Bread\n- 🥛 Milk (Dummy Data)"
    )

async def _dummy_add_item(phone_number: str):
    """Dummy static function to simulate starting the add item flow."""
    logger.info(f"Executing deterministic intent CMD_ADD_ITEM for {phone_number}")
    await whatsapp_service.send_whatsapp_message(
        phone_number,
        "What item would you like to add? Please type its name. (Dummy Data)"
    )
