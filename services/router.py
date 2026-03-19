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

from services.whatsapp_ui import WhatsAppUI
from services.whatsapp_client import send_whatsapp_message as native_send_whatsapp_message

async def route_interactive_message(phone_number: str, payload_id: str):
    """
    Deterministic routing for interactive messages (buttons and lists).
    Pure Python match/case state machine.
    """
    logger.info(f"Routing interactive payload: '{payload_id}' for {phone_number}")

    if payload_id == 'CMD_VIEW_PANTRY':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to get_inventory()\n")
        await _dummy_get_inventory(phone_number)
    elif payload_id == 'CMD_ADD_ITEM':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to add_item()\n")
        await _dummy_add_item(phone_number)
    elif payload_id == 'CMD_MAIN_MENU':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing back to main menu()\n")
        await route_text_message(phone_number, "Main Menu Triggered")
    else:
        # Fallback to existing interactive logic for LangChain or standard menu intents if not statically overridden.
        await whatsapp_service.process_interactive_message(phone_number, payload_id)

async def route_text_message(phone_number: str, text: str):
    """
    Bypasses LangChain logic entirely for the core workflow natively returning the Main Menu via Meta Interactive Lists.
    """
    logger.info(f"Intercepting text message from {phone_number}: Natively bouncing to Main Menu UI constraints")
    
    sections = [
        {
            "title": "Pantry Actions",
            "rows": [
                {"id": "CMD_VIEW_PANTRY", "title": "View Pantry", "description": "See your current grocery list"},
                {"id": "CMD_ADD_ITEM", "title": "Add Item", "description": "Add new items to your pantry"},
                {"id": "CMD_COOK_SOMETHING", "title": "Cook Something", "description": "Get recipe recommendations"}
            ]
        }
    ]
    
    payload = WhatsAppUI.build_list_message(
        to_number=phone_number,
        text="👋 Welcome to PantryPilot v2.0! What would you like to do?",
        menu_button_text="Main Menu",
        sections=sections
    )
    
    await native_send_whatsapp_message(payload)

async def _dummy_get_inventory(phone_number: str):
    """Retrieves pantry inventory natively sending Meta API Interactive Quick Reply buttons backwards."""
    logger.info(f"Executing deterministic intent CMD_VIEW_PANTRY for {phone_number}")
    
    buttons = [
        {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
        {"id": "CMD_ADD_ITEM", "title": "Add Item"}
    ]
    
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text="Your pantry has 3 items. (Database connection coming soon!)",
        buttons=buttons
    )
    
    await native_send_whatsapp_message(payload)

async def _dummy_add_item(phone_number: str):
    """Dummy static function to simulate starting the add item flow."""
    logger.info(f"Executing deterministic intent CMD_ADD_ITEM for {phone_number}")
    await whatsapp_service.send_whatsapp_message(
        phone_number,
        "What item would you like to add? Please type its name. (Dummy Data)"
    )
