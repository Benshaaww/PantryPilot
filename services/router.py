from __future__ import annotations

import logging
from typing import Awaitable, Callable

from schemas.whatsapp import Message
from services import state_manager, database
from services.ui_decorator import decorate_item
from services.whatsapp_ui import WhatsAppUI
from services.whatsapp_client import send_whatsapp_message as _send
from agents.recipe_agent import generate_recipe
from services.whatsapp_client import download_media_base64
from services.vision_agent import analyze_image

logger = logging.getLogger(__name__)

# Type alias for a handler that accepts a phone number and returns a coroutine.
_Handler = Callable[[str], Awaitable[None]]

_ERROR_MESSAGE = "⚠️ Oops! Something went wrong on my end. Try again in a second?"


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

async def process_inbound_message(message: Message) -> None:
    """
    Layer 2: Deterministic FSM Router.
    Dispatches by message type.  Any unhandled exception sends the user
    a polite error instead of silently failing.
    """
    phone_number = message.from_
    msg_type = message.type

    try:
        if msg_type == "text" and message.text:
            await route_text_message(phone_number, message.text.body)

        elif msg_type == "interactive" and message.interactive:
            interactive = message.interactive
            payload_id: str | None = None

            if interactive.type == "button_reply" and interactive.button_reply:
                payload_id = interactive.button_reply.id
            elif interactive.type == "list_reply" and interactive.list_reply:
                payload_id = interactive.list_reply.id

            if payload_id:
                await route_interactive_message(phone_number, payload_id)
            else:
                logger.warning("Interactive message with no extractable payload_id.")
                await _send_text(phone_number, _ERROR_MESSAGE)

        elif msg_type == "image" and message.image:
            await handle_image_action(phone_number, message.image.id)

        elif msg_type in ("audio", "sticker"):
            await _send_text(
                phone_number,
                "I'm still learning to process media! Please type your grocery requests.",
            )
        else:
            logger.info("Unhandled message type: %s", msg_type)

    except Exception as exc:
        logger.error(
            "Unhandled exception in router for %s: %s", phone_number, exc, exc_info=True
        )
        try:
            await _send_text(phone_number, _ERROR_MESSAGE)
        except Exception:
            pass  # Never let error-handling itself propagate


# ---------------------------------------------------------------------------
# Interactive message registry
# ---------------------------------------------------------------------------

# Populated after handler definitions at the bottom of this file.
_INTERACTIVE_REGISTRY: dict[str, _Handler] = {}


async def route_interactive_message(phone_number: str, payload_id: str) -> None:
    """
    Registry-pattern router for interactive payloads.
    Exact matches are looked up in O(1); DEL_ prefix is handled as a
    special case; anything unknown falls through to the main menu.
    """
    logger.info("Interactive payload '%s' from %s", payload_id, phone_number)

    handler = _INTERACTIVE_REGISTRY.get(payload_id)
    if handler:
        await handler(phone_number)
    elif payload_id.startswith("DEL_"):
        item_name = payload_id[4:]  # strip "DEL_" prefix
        await handle_delete_execution(phone_number, item_name)
    else:
        logger.warning("Unknown payload_id '%s' — showing main menu.", payload_id)
        await route_text_message(phone_number, "")


# ---------------------------------------------------------------------------
# Text / FSM routing
# ---------------------------------------------------------------------------

async def route_text_message(phone_number: str, text: str) -> None:
    """
    Routes plain-text messages.
    Priority order:
      1. JOIN <id> command
      2. Stateful context (AWAITING_ITEM_NAME)
      3. Default — show Main Menu
    """
    text_upper = text.strip().upper()

    # 1. JOIN household command
    if text_upper.startswith("JOIN "):
        await _handle_join_command(phone_number, text_upper)
        return

    # 2. Stateful context check
    if state_manager.get_state(phone_number) == "AWAITING_ITEM_NAME":
        household_id = database.get_household_id(phone_number)
        logger.info(
            "AWAITING_ITEM_NAME for %s — adding '%s' to household %d",
            phone_number, text, household_id,
        )
        database.add_item(household_id, text)
        state_manager.clear_state(phone_number)
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=f"✅ Added {decorate_item(text)} to your pantry.",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
        ))
        return

    # 3. Main menu fallback
    logger.info("Showing main menu to %s", phone_number)
    sections = [
        {
            "title": "Pantry Actions",
            "rows": [
                {"id": "CMD_VIEW_PANTRY",    "title": "View Pantry",    "description": "See your current grocery list"},
                {"id": "CMD_ADD_ITEM",       "title": "Add Item",       "description": "Add new items to your pantry"},
                {"id": "CMD_PREPARE_REMOVE", "title": "Remove Item",    "description": "Remove items from your pantry"},
                {"id": "CMD_COOK",           "title": "Cook Something", "description": "Get recipe recommendations"},
                {"id": "CMD_VIEW_SHOPPING",  "title": "Shopping List",  "description": "View items to replenish"},
            ],
        }
    ]
    await _send(WhatsAppUI.build_list_message(
        to_number=phone_number,
        text="👋 Welcome to PantryPilot v2.0! What would you like to do?",
        menu_button_text="Main Menu",
        sections=sections,
    ))


# ---------------------------------------------------------------------------
# Individual command handlers
# ---------------------------------------------------------------------------

async def _handle_join_command(phone_number: str, text_upper: str) -> None:
    try:
        target_id = int(text_upper.split(" ")[1])
        if database.join_household(phone_number, target_id):
            hh_name = database.get_household_name(target_id)
            await _send_text(
                phone_number,
                f"🎉 You've successfully joined {hh_name} (Household #{target_id})!",
            )
        else:
            await _send_text(
                phone_number,
                f"❌ Could not find Household #{target_id}. Are you sure the ID is correct?",
            )
    except (IndexError, ValueError):
        pass  # Fall through; let the main menu render


async def _handle_view_pantry(phone_number: str) -> None:
    household_id = database.get_household_id(phone_number)
    household_name = database.get_household_name(household_id)
    logger.info("CMD_VIEW_PANTRY for %s (HH %d)", phone_number, household_id)

    items = database.get_inventory(household_id)
    buttons = [
        {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
        {"id": "CMD_ADD_ITEM",  "title": "Add Item"},
    ]

    if not items:
        text = (
            f"Viewing {household_name}:\n\n"
            f"Your pantry is currently empty! 🛒\n"
            f"Share your Household ID #{household_id} to invite family!"
        )
    else:
        item_lines = "\n".join(f"- {decorate_item(i)}" for i in items)
        text = f"Viewing {household_name} (ID #{household_id}):\n\n{item_lines}"

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number, text=text, buttons=buttons
    ))


async def _handle_add_item(phone_number: str) -> None:
    logger.info("CMD_ADD_ITEM for %s", phone_number)
    state_manager.set_state(phone_number, "AWAITING_ITEM_NAME")
    await _send_text(phone_number, "What item would you like to add? Please type its name.")


async def handle_cook_action(phone_number: str) -> None:
    logger.info("CMD_COOK for %s", phone_number)
    await _send_text(phone_number, "👨‍🍳 Analyzing your pantry...")

    household_id = database.get_household_id(phone_number)
    items = database.get_inventory(household_id)

    if not items:
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text="You don't have any food in your pantry yet! Add some items first.",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
        ))
        return

    recipe_text = await generate_recipe(items)
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=recipe_text,
        buttons=[
            {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
            {"id": "CMD_COOK",      "title": "Cook Another"},
        ],
    ))


async def handle_prepare_remove(phone_number: str) -> None:
    household_id = database.get_household_id(phone_number)
    items = database.get_inventory(household_id)
    hh_name = database.get_household_name(household_id)

    if not items:
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=f"Viewing {hh_name}:\n\nYour pantry is empty — nothing to remove.",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
        ))
        return

    recent_items = items[-10:] if len(items) > 10 else items
    rows = [
        {
            "id": f"DEL_{item[:24]}",
            "title": decorate_item(item[:24]),
            "description": "Tap to consume or remove",
        }
        for item in recent_items
    ]
    await _send(WhatsAppUI.build_list_message(
        to_number=phone_number,
        text=f"Viewing {hh_name}:\n\nWhich item would you like to remove?",
        menu_button_text="Select Item",
        sections=[{"title": "Select Item", "rows": rows}],
    ))


async def handle_delete_execution(phone_number: str, item_name: str) -> None:
    household_id = database.get_household_id(phone_number)
    success = database.delete_item_by_name(household_id, item_name)

    if success:
        database.add_to_shopping_list(household_id, item_name)
        text = f"🗑️ Removed {decorate_item(item_name)}. Added to your Shopping List! ✅"
    else:
        text = f"❌ Could not remove {decorate_item(item_name)}."

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text,
        buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
    ))


async def handle_view_shopping(phone_number: str) -> None:
    household_id = database.get_household_id(phone_number)
    household_name = database.get_household_name(household_id)
    logger.info("CMD_VIEW_SHOPPING for %s (HH %d)", phone_number, household_id)

    items = database.get_shopping_list(household_id)

    if not items:
        text = f"🛒 {household_name}'s Shopping List:\n\nYour shopping list is empty!"
        buttons = [{"id": "CMD_MAIN_MENU", "title": "Main Menu"}]
    else:
        text = f"🛒 {household_name}'s Shopping List:\n\n" + "\n".join(
            f"🛒 {decorate_item(i)}" for i in items
        )
        buttons = [
            {"id": "CMD_MAIN_MENU",      "title": "Main Menu"},
            {"id": "CMD_CLEAR_SHOPPING", "title": "Clear List"},
        ]

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number, text=text, buttons=buttons
    ))


async def handle_clear_shopping(phone_number: str) -> None:
    household_id = database.get_household_id(phone_number)
    if database.clear_shopping_list(household_id):
        text = "✅ Shopping list cleared. You're all set!"
    else:
        text = "❌ Error clearing the list."

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text,
        buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
    ))


async def handle_image_action(phone_number: str, media_id: str) -> None:
    logger.info("IMAGE_UPLOAD for %s (media_id: %s)", phone_number, media_id)
    household_id = database.get_household_id(phone_number)

    await _send_text(phone_number, "📸 Analyzing your image... give me a second!")

    base64_img = await download_media_base64(media_id)
    if not base64_img:
        await _send_text(phone_number, "❌ Failed to retrieve that image from Meta. Please try again.")
        return

    extracted_text = await analyze_image(base64_img)
    if extracted_text == "NONE":
        await _send_text(phone_number, "I couldn't find any clear groceries in that image! 🍅")
        return

    items_to_add = [item.strip() for item in extracted_text.split(",") if item.strip()]
    for item in items_to_add:
        database.add_item(household_id, item)

    hh_name = database.get_household_name(household_id)
    item_lines = "\n".join(f"- {decorate_item(i)}" for i in items_to_add)
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=f"✅ Successfully added to {hh_name}:\n\n{item_lines}",
        buttons=[{"id": "CMD_VIEW_PANTRY", "title": "View Pantry"}],
    ))


# ---------------------------------------------------------------------------
# Helper: send a plain-text message
# ---------------------------------------------------------------------------

async def _send_text(phone_number: str, body: str) -> None:
    await _send({
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": body},
    })


# ---------------------------------------------------------------------------
# Build the registry — must come AFTER all handler definitions
# ---------------------------------------------------------------------------

_INTERACTIVE_REGISTRY = {
    "CMD_VIEW_PANTRY":    _handle_view_pantry,
    "CMD_ADD_ITEM":       _handle_add_item,
    "CMD_COOK":           handle_cook_action,
    "CMD_PREPARE_REMOVE": handle_prepare_remove,
    "CMD_VIEW_SHOPPING":  handle_view_shopping,
    "CMD_CLEAR_SHOPPING": handle_clear_shopping,
    "CMD_MAIN_MENU":      lambda phone: route_text_message(phone, ""),
}
