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
            
    elif msg_type == "image" and message.image:
        image_id = message.image.id
        await handle_image_action(phone_number, image_id)
        
    elif msg_type in ["audio", "sticker"]:
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
    elif payload_id == 'CMD_COOK':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to generate_recipe()\n")
        await handle_cook_action(phone_number)
    elif payload_id == 'CMD_PREPARE_REMOVE':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to prepare_remove()\n")
        await handle_prepare_remove(phone_number)
    elif payload_id.startswith('DEL_'):
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to delete item execution()\n")
        item_to_delete = payload_id.replace("DEL_", "")
        await handle_delete_execution(phone_number, item_to_delete)
    elif payload_id == 'CMD_VIEW_SHOPPING':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to view_shopping_list()\n")
        await handle_view_shopping(phone_number)
    elif payload_id == 'CMD_CLEAR_SHOPPING':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing to clear_shopping_list()\n")
        await handle_clear_shopping(phone_number)
    elif payload_id == 'CMD_MAIN_MENU':
        print(f"\n🟢 DETECTED BUTTON CLICK: {payload_id} from {phone_number}")
        print("-> Routing back to main menu()\n")
        await route_text_message(phone_number, "Main Menu Triggered")
    else:
        # Fallback to existing interactive logic for LangChain or standard menu intents if not statically overridden.
        await whatsapp_service.process_interactive_message(phone_number, payload_id)

from services import state_manager
from services import database
from services.ui_decorator import decorate_item

async def route_text_message(phone_number: str, text: str):
    """
    Bypasses LangChain logic entirely for the core workflow natively returning the Main Menu via Meta Interactive Lists.
    Now respects User State and acts identically to a Finite State Machine context block!
    """
    household_id = database.get_household_id(phone_number)
    
    # 1. Check for JOIN command intercept
    text_upper = text.strip().upper()
    if text_upper.startswith("JOIN "):
        try:
            target_id = int(text_upper.split(" ")[1])
            success = database.join_household(phone_number, target_id)
            if success:
                hh_name = database.get_household_name(target_id)
                await native_send_whatsapp_message({
                    "messaging_product": "whatsapp",
                    "to": phone_number,
                    "type": "text",
                    "text": {"body": f"🎉 You've successfully joined {hh_name} (Household #{target_id})!"}
                })
            else:
                await native_send_whatsapp_message({
                    "messaging_product": "whatsapp",
                    "to": phone_number,
                    "type": "text",
                    "text": {"body": f"❌ Could not find Household #{target_id}. Are you sure the ID is correct?"}
                })
            return
        except Exception:
            pass # Fall through to context routing
            
    # 2. Check Stateful Context Before Defaulting
    current_state = state_manager.get_state(phone_number)
    
    if current_state == "AWAITING_ITEM_NAME":
        logger.info(f"State matching AWAITING_ITEM_NAME for {phone_number}. Adding item: {text} to HH {household_id}")
        database.add_item(household_id, text)
        state_manager.clear_state(phone_number)
        
        # We send a quiet Button payload acknowledging this success to keep them in flow
        success_payload = WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=f"✅ Added {decorate_item(text)} to your pantry.",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
        )
        await native_send_whatsapp_message(success_payload)
        return

    # Default fallback: Show main menu
    logger.info(f"Intercepting text message from {phone_number}: Natively bouncing to Main Menu UI constraints")
    
    sections = [
        {
            "title": "Pantry Actions",
            "rows": [
                {"id": "CMD_VIEW_PANTRY", "title": "View Pantry", "description": "See your current grocery list"},
                {"id": "CMD_ADD_ITEM", "title": "Add Item", "description": "Add new items to your pantry"},
                {"id": "CMD_PREPARE_REMOVE", "title": "Remove Item", "description": "Remove items from your pantry"},
                {"id": "CMD_COOK", "title": "Cook Something", "description": "Get recipe recommendations"},
                {"id": "CMD_VIEW_SHOPPING", "title": "Shopping List", "description": "View items to replenish"}
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
    household_id = database.get_household_id(phone_number)
    household_name = database.get_household_name(household_id)
    logger.info(f"Executing deterministic intent CMD_VIEW_PANTRY for {phone_number} (HH: {household_id})")
    
    items = database.get_inventory(household_id)
    
    buttons = [
        {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
        {"id": "CMD_ADD_ITEM", "title": "Add Item"}
    ]
    
    if not items:
        text_body = f"Viewing {household_name}:\n\nYour pantry is currently empty! 🛒\nShare your Household ID #{household_id} to invite family!"
    else:
        formatted_list = "\n".join([f"- {decorate_item(item)}" for item in items])
        text_body = f"Viewing {household_name} (ID #{household_id}):\n\n{formatted_list}"
    
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text_body,
        buttons=buttons
    )
    
    await native_send_whatsapp_message(payload)

async def _dummy_add_item(phone_number: str):
    """Simulates starting the add item flow by opening up a Stateful wait cycle."""
    logger.info(f"Executing deterministic intent CMD_ADD_ITEM for {phone_number}")
    
    # 1. Set User state so the next text caught handles it cleanly
    state_manager.set_state(phone_number, "AWAITING_ITEM_NAME")
    
    # 2. Return Prompt via text
    await native_send_whatsapp_message({
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": "What item would you like to add? Please type its name."}
    })

from agents.recipe_agent import generate_recipe

async def handle_cook_action(phone_number: str):
    """
    Layer 3 FSM Hook. Fetches inventory, triggers LLM specifically for recipe creation,
    and formats the AI payload back into standard interactive UI structures.
    """
    logger.info(f"Executing Agentic intent CMD_COOK for {phone_number}")
    
    # 1. Fire temporary thinking message gracefully so user knows the bot is working
    await native_send_whatsapp_message({
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": "👨‍🍳 Analyzing your pantry..."}
    })
    
    # 2. Get true context inventory
    household_id = database.get_household_id(phone_number)
    items = database.get_inventory(household_id)
    
    if not items:
        # Prevent LLM hallucinations entirely if empty
        payload = WhatsAppUI.build_button_message(
            to_number=phone_number,
            text="You don't have any food in your pantry yet! Add some items first.",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
        )
        await native_send_whatsapp_message(payload)
        return
        
    # 3. Stream strict AI output
    recipe_text = await generate_recipe(items)
    
    # 4. Cap output contextually
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=recipe_text,
        buttons=[
            {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
            {"id": "CMD_COOK", "title": "Cook Another"}
        ]
    )
    
    await native_send_whatsapp_message(payload)

async def handle_prepare_remove(phone_number: str):
    """Generates the dynamic point-and-click WhatsApp List Message for Deletion."""
    household_id = database.get_household_id(phone_number)
    items = database.get_inventory(household_id)
    hh_name = database.get_household_name(household_id)
    
    if not items:
        payload = WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=f"Viewing {hh_name}:\n\nYour pantry is currently empty! Nothing to remove.",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
        )
        await native_send_whatsapp_message(payload)
        return
        
    # Meta lists max out at 10 rows. Grab the 10 most recent.
    recent_items = items[-10:] if len(items) > 10 else items
    
    rows = []
    for item in recent_items:
        # Strip to max 24 characters safely for WhatsApp Title constraint just in case
        safe_item_name = item[:24]
        rows.append({
            "id": f"DEL_{safe_item_name}",
            "title": decorate_item(safe_item_name),
            "description": "Tap to consume or remove"
        })
        
    sections = [
        {
            "title": "Select Item",
            "rows": rows
        }
    ]
    
    payload = WhatsAppUI.build_list_message(
        to_number=phone_number,
        text=f"Viewing {hh_name}:\n\nWhich item would you like to remove from the pantry?",
        menu_button_text="Select Item",
        sections=sections
    )
    
    await native_send_whatsapp_message(payload)

async def handle_delete_execution(phone_number: str, item_name: str):
    """Fires the database deletion constraint and confirms to the user."""
    household_id = database.get_household_id(phone_number)
    
    success = database.delete_item_by_name(household_id, item_name)
    
    if success:
        # Consumption Bridge!
        database.add_to_shopping_list(household_id, item_name)
        text = f"🗑️ Removed {decorate_item(item_name)}. I've added it to your Shopping List! ✅"
    else:
        text = f"❌ Could not remove {decorate_item(item_name)}."
        
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text,
        buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
    )
    
    await native_send_whatsapp_message(payload)

from services.whatsapp_client import download_media_base64
from services.vision_agent import analyze_image

async def handle_image_action(phone_number: str, media_id: str):
    """Downloads images automatically routing them through OCR LLMs and into the local Pantry vault!"""
    logger.info(f"Executing Agentic intent IMAGE_UPLOAD for {phone_number}")
    household_id = database.get_household_id(phone_number)
    
    # 1. Fire temporary thinking message gracefully
    await native_send_whatsapp_message({
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": "📸 Analyzing your image... give me a second!"}
    })
    
    # 2. Download media securely to base64 mapping
    base64_img = await download_media_base64(media_id)
    if not base64_img:
        await native_send_whatsapp_message({
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": "❌ Failed to secure that image from Meta! Please try again."}
        })
        return
        
    # 3. Stream data via LLM Vision APIs
    extracted_text = await analyze_image(base64_img)
    
    if extracted_text == "NONE":
        await native_send_whatsapp_message({
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": "I couldn't find any clear groceries or food items in that image! 🍅"}
        })
        return
        
    # 4. Safely loop extraction list strictly into Relational mappings Database constraints
    items_to_add = [item.strip() for item in extracted_text.split(",") if item.strip()]
    
    for item in items_to_add:
        database.add_item(household_id, item)
        
    # 5. Native UI list formatting confirmation Summary matching View constraints!
    hh_name = database.get_household_name(household_id)
    formatted_list = "\n".join([f"- {decorate_item(item)}" for item in items_to_add])
    success_text = f"✅ Successfully added to {hh_name}:\n\n{formatted_list}"
    
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=success_text,
        buttons=[{"id": "CMD_VIEW_PANTRY", "title": "View Pantry"}]
    )
    
    await native_send_whatsapp_message(payload)

async def handle_view_shopping(phone_number: str):
    """Retrieves shopping ledger and natively sends interactive list response."""
    household_id = database.get_household_id(phone_number)
    household_name = database.get_household_name(household_id)
    logger.info(f"Executing deterministic intent CMD_VIEW_SHOPPING for {phone_number} (HH: {household_id})")
    
    items = database.get_shopping_list(household_id)
    
    buttons = [
        {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
        {"id": "CMD_CLEAR_SHOPPING", "title": "Clear List"}
    ]
    
    if not items:
        text_body = f"🛒 {household_name}'s Shopping List:\n\nYour shopping list is currently empty!"
        # If empty, don't need a clear button
        buttons = [{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
    else:
        formatted_list = "\n".join([f"🛒 {decorate_item(item)}" for item in items])
        text_body = f"🛒 {household_name}'s Shopping List:\n\n{formatted_list}"
    
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text_body,
        buttons=buttons
    )
    
    await native_send_whatsapp_message(payload)

async def handle_clear_shopping(phone_number: str):
    """Fires database deletion cleanly against the active household shopping ledger."""
    household_id = database.get_household_id(phone_number)
    
    success = database.clear_shopping_list(household_id)
    
    if success:
        text = f"✅ Cleared your Shopping List. You are all done!"
    else:
        text = f"❌ Error clearing the list."
        
    payload = WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text,
        buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
    )
    
    await native_send_whatsapp_message(payload)
