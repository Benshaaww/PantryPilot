from __future__ import annotations

import logging
from typing import Awaitable, Callable

from schemas.whatsapp import Message
from services import state_manager, database
from services.invite_manager import generate_invite, redeem_invite
from services.ui_decorator import decorate_item
from services.whatsapp_ui import WhatsAppUI
from services.whatsapp_client import send_whatsapp_message as _send
from agents.recipe_agent import generate_recipe
from services.whatsapp_client import download_media_base64
from services.vision_agent import analyze_image

logger = logging.getLogger(__name__)

_Handler = Callable[[str], Awaitable[None]]

_ERROR_MESSAGE = "⚠️ Oops! Something went wrong on my end. Try again in a second?"

_WELCOME = (
    "Welcome to PantryPilot! 🚀 Your kitchen's new best friend.\n\n"
    "Let's get these groceries sorted so you can get back to the fun stuff."
)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

async def process_inbound_message(message: Message) -> None:
    """
    Layer 2: Deterministic FSM Router.
    Dispatches by message type. Any unhandled exception sends a polite error.
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
                logger.warning("Interactive message with no payload_id.")
                await _send_text(phone_number, _ERROR_MESSAGE)

        elif msg_type == "image" and message.image:
            await handle_image_action(phone_number, message.image.id)

        elif msg_type in ("audio", "sticker"):
            await _send_text(
                phone_number,
                "I can read images and text — audio isn't supported yet! "
                "Type an item name or send a photo of your groceries. 📸",
            )
        else:
            logger.info("Unhandled message type: %s", msg_type)

    except Exception as exc:
        logger.error("Unhandled exception in router for %s: %s", phone_number, exc, exc_info=True)
        try:
            await _send_text(phone_number, _ERROR_MESSAGE)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Interactive message registry (populated at bottom of file)
# ---------------------------------------------------------------------------

_INTERACTIVE_REGISTRY: dict[str, _Handler] = {}


async def route_interactive_message(phone_number: str, payload_id: str) -> None:
    """O(1) registry lookup; DEL_ and SETBUYER_ are handled as prefix cases."""
    logger.info("Interactive payload '%s' from %s", payload_id, phone_number)

    handler = _INTERACTIVE_REGISTRY.get(payload_id)
    if handler:
        await handler(phone_number)
    elif payload_id.startswith("DEL_"):
        await handle_delete_execution(phone_number, payload_id[4:])
    elif payload_id.startswith("SETBUYER_"):
        await _handle_set_buyer(phone_number, payload_id[9:])
    else:
        logger.warning("Unknown payload_id '%s' — showing main menu.", payload_id)
        await route_text_message(phone_number, "")


# ---------------------------------------------------------------------------
# Text / FSM routing
# ---------------------------------------------------------------------------

async def route_text_message(phone_number: str, text: str) -> None:
    """
    Priority order:
      1. JOIN <code>  — invite-code redemption
      2. AWAITING_ITEM_NAME state — add item to grocery list
      3. Default — main menu
    """
    text_stripped = text.strip()
    text_upper = text_stripped.upper()

    # 1. Invite code redemption
    if text_upper.startswith("JOIN "):
        await _handle_join_command(phone_number, text_stripped)
        return

    # 2. Stateful: waiting for item name — supports comma-separated batch input
    if state_manager.get_state(phone_number) == "AWAITING_ITEM_NAME":
        household_id = database.get_household_id(phone_number)

        # "Shatter": split on commas, title-case each token, drop blanks
        items = [i.strip().title() for i in text_stripped.split(",") if i.strip()]
        if not items:
            await _send_text(phone_number, "I didn't catch that — please type at least one item name.")
            return

        logger.info("AWAITING_ITEM_NAME for %s — adding %d item(s): %s", phone_number, len(items), items)
        for item in items:
            database.add_grocery_item(household_id, item)
        state_manager.clear_state(phone_number)

        # Bulleted confirmation with per-item emoji decoration
        bullet_lines = "\n".join(f"  {decorate_item(i)}" for i in items)
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=f"✅ Added to your list:\n\n{bullet_lines}",
            buttons=[
                {"id": "CMD_ADD_ITEM",     "title": "Add More"},
                {"id": "CMD_VIEW_GROCERY", "title": "View List"},
                {"id": "CMD_MAIN_MENU",    "title": "Main Menu"},
            ],
        ))
        return

    # 3. Main menu fallback
    await _show_main_menu(phone_number)


async def _show_main_menu(phone_number: str) -> None:
    logger.info("Showing main menu to %s", phone_number)
    sections = [
        {
            "title": "Grocery Actions",
            "rows": [
                {
                    "id": "CMD_VIEW_GROCERY",
                    "title": "📝 View Grocery List",
                    "description": "See everything on the list",
                },
                {
                    "id": "CMD_ADD_ITEM",
                    "title": "➕ Add Item",
                    "description": "Type an item to add it",
                },
                {
                    "id": "CMD_SCAN",
                    "title": "📸 Scan Items",
                    "description": "Photo or receipt — AI reads it",
                },
                {
                    "id": "CMD_COOK",
                    "title": "👨‍🍳 Cook from List",
                    "description": "Get a recipe from what you have",
                },
                {
                    "id": "CMD_INVITE_FAMILY",
                    "title": "👥 Invite Family",
                    "description": "Share this list with your household",
                },
                {
                    "id": "CMD_DISPATCH_LIST",
                    "title": "🛒 Send to Buyer",
                    "description": "Dispatch the list to your shopper",
                },
            ],
        }
    ]
    await _send(WhatsAppUI.build_list_message(
        to_number=phone_number,
        text=_WELCOME,
        menu_button_text="Open Menu",
        sections=sections,
    ))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def _handle_join_command(phone_number: str, text: str) -> None:
    """Handles 'JOIN <CODE>' — redeems an invite code."""
    parts = text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        await _send_text(phone_number, "Please type JOIN followed by your invite code, e.g. JOIN ABC123")
        return

    code = parts[1].strip()
    success, household_id, hh_name = redeem_invite(phone_number, code)

    if success:
        # Role is set to MEMBER by join_household() — verify and build sync preview
        items = database.get_grocery_list(household_id)
        if items:
            preview_items = items[:5]
            item_lines = "\n".join(f"  {decorate_item(i)}" for i in preview_items)
            more_note = f"\n  _...and {len(items) - 5} more_" if len(items) > 5 else ""
            sync_section = f"\n\n📋 *Current List ({len(items)} items):*\n{item_lines}{more_note}"
        else:
            sync_section = "\n\n📋 The list is empty — you're first! Start adding items."

        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=(
                f"✅ *Sync Successful!*\n\n"
                f"Welcome to *{hh_name}*! You've been added as a Member."
                f"{sync_section}"
            ),
            buttons=[
                {"id": "CMD_VIEW_GROCERY", "title": "📝 View Full List"},
                {"id": "CMD_MAIN_MENU",    "title": "Main Menu"},
            ],
        ))
    else:
        await _send_text(
            phone_number,
            f"❌ The code *{code}* is invalid or has expired.\n"
            "Ask your household to generate a fresh invite.",
        )


async def _handle_view_grocery(phone_number: str) -> None:
    household_id = database.get_household_id(phone_number)
    hh_name = database.get_household_name(household_id)
    items = database.get_grocery_list(household_id)
    logger.info("CMD_VIEW_GROCERY for %s (HH %d)", phone_number, household_id)

    if not items:
        text = (
            f"📝 *{hh_name}* Grocery List\n\n"
            "Your list is empty — nothing here yet!\n"
            "Add something or scan a receipt to get started. 🛒"
        )
        buttons = [
            {"id": "CMD_ADD_ITEM",  "title": "➕ Add Item"},
            {"id": "CMD_SCAN",      "title": "📸 Scan"},
            {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
        ]
    else:
        item_lines = "\n".join(f"  {decorate_item(i)}" for i in items)
        text = f"📝 *{hh_name}* Grocery List ({len(items)} items)\n\n{item_lines}"
        buttons = [
            {"id": "CMD_ADD_ITEM",      "title": "➕ Add Item"},
            {"id": "CMD_REMOVE_ITEM",   "title": "🗑️ Remove"},
            {"id": "CMD_DISPATCH_LIST", "title": "🛒 Send to Buyer"},
        ]

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number, text=text, buttons=buttons
    ))


async def _handle_add_item(phone_number: str) -> None:
    logger.info("CMD_ADD_ITEM for %s", phone_number)
    state_manager.set_state(phone_number, "AWAITING_ITEM_NAME")
    await _send_text(phone_number, "What would you like to add? Just type the item name. 🖊️")


async def _handle_scan(phone_number: str) -> None:
    """Prompts the user to send an image — OCR fires automatically on receipt."""
    await _send_text(
        phone_number,
        "📸 Send me a photo of your groceries or a receipt!\n\n"
        "I'll read it and add everything to your list automatically.",
    )


async def handle_cook_action(phone_number: str) -> None:
    logger.info("CMD_COOK for %s", phone_number)
    await _send_text(phone_number, "👨‍🍳 Checking your grocery list for inspiration...")

    household_id = database.get_household_id(phone_number)
    items = database.get_grocery_list(household_id)

    if not items:
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text="Your grocery list is empty! Add some ingredients first. 🥕",
            buttons=[
                {"id": "CMD_ADD_ITEM",  "title": "➕ Add Item"},
                {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
            ],
        ))
        return

    recipe_text = await generate_recipe(items)
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=recipe_text,
        buttons=[
            {"id": "CMD_COOK",      "title": "👨‍🍳 Another"},
            {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
        ],
    ))


async def _handle_remove_item(phone_number: str) -> None:
    """Shows the grocery list as a selectable list for deletion."""
    household_id = database.get_household_id(phone_number)
    items = database.get_grocery_list(household_id)
    hh_name = database.get_household_name(household_id)

    if not items:
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text=f"📝 *{hh_name}* — list is already empty, nothing to remove!",
            buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
        ))
        return

    recent = items[-10:] if len(items) > 10 else items
    rows = [
        {
            "id": f"DEL_{item[:24]}",
            "title": decorate_item(item[:24]),
            "description": "Tap to remove",
        }
        for item in recent
    ]
    await _send(WhatsAppUI.build_list_message(
        to_number=phone_number,
        text=f"📝 *{hh_name}* — which item would you like to remove?",
        menu_button_text="Remove Item",
        sections=[{"title": "Grocery List", "rows": rows}],
    ))


async def handle_delete_execution(phone_number: str, item_name: str) -> None:
    household_id = database.get_household_id(phone_number)
    database.delete_grocery_item(household_id, item_name)
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=f"🗑️ Removed {decorate_item(item_name)} from your list.",
        buttons=[
            {"id": "CMD_VIEW_GROCERY", "title": "📝 View List"},
            {"id": "CMD_MAIN_MENU",    "title": "Main Menu"},
        ],
    ))


async def _handle_clear_list(phone_number: str) -> None:
    household_id = database.get_household_id(phone_number)
    if database.clear_grocery_list(household_id):
        text = "✅ Grocery list cleared — fresh start!"
    else:
        text = "❌ Couldn't clear the list. Please try again."
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text,
        buttons=[{"id": "CMD_MAIN_MENU", "title": "Main Menu"}],
    ))


async def _handle_invite_family(phone_number: str) -> None:
    """Generates a fresh invite code and deep link, then shares both."""
    import os
    household_id = database.get_household_id(phone_number)
    hh_name = database.get_household_name(household_id)
    invite_code = generate_invite(household_id)
    logger.info("CMD_INVITE_FAMILY for %s — code %s", phone_number, invite_code)

    bot_number = os.getenv("WHATSAPP_BOT_NUMBER", os.getenv("WHATSAPP_PHONE_NUMBER", ""))
    clean_bot_number = bot_number.replace("+", "").replace(" ", "").strip()

    if clean_bot_number:
        invite_link = f"https://wa.me/{clean_bot_number}?text=JOIN%20{invite_code}"
        text_body = (
            f"👥 Invite someone to *{hh_name}*!\n\n"
            f"Tap the link below to invite them to your household! 🏠\n"
            f"{invite_link}\n"
            f"(Tapping the link opens WhatsApp with the join message ready to send)\n\n"
            f"Or they can type manually:  JOIN {invite_code}\n\n"
            f"_(Expires in 24 hours)_"
        )
    else:
        text_body = (
            f"👥 Invite someone to *{hh_name}*!\n\n"
            f"Tell them to text this code to me:\n"
            f"JOIN {invite_code}\n\n"
            f"_(Expires in 24 hours)_"
        )

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=text_body,
        buttons=[
            {"id": "CMD_INVITE_FAMILY", "title": "🔄 New Code"},
            {"id": "CMD_MAIN_MENU",     "title": "Main Menu"},
        ],
    ))


async def handle_dispatch_list(phone_number: str) -> None:
    """
    Sends the full grocery list to every BUYER in the household.
    If no buyer is designated, prompts the user to set one.
    """
    household_id = database.get_household_id(phone_number)
    buyers = database.get_household_buyers(household_id)

    if not buyers:
        # Show all household members so the user can designate one as buyer
        members = database.get_household_members(household_id)
        if len(members) <= 1:
            await _send(WhatsAppUI.build_button_message(
                to_number=phone_number,
                text=(
                    "🛒 No buyer designated yet!\n\n"
                    "Invite your household first, then come back and set a buyer.\n"
                    "Or tap below to make *yourself* the buyer."
                ),
                buttons=[
                    {"id": f"SETBUYER_{phone_number}", "title": "🙋 I'm the Buyer"},
                    {"id": "CMD_INVITE_FAMILY",         "title": "👥 Invite Family"},
                    {"id": "CMD_MAIN_MENU",             "title": "Main Menu"},
                ],
            ))
            return

        rows = [
            {
                "id": f"SETBUYER_{m}",
                "title": f"{'Me 🙋' if m == phone_number else m[-6:]}",
                "description": "Designate as buyer for this household",
            }
            for m in members
        ]
        await _send(WhatsAppUI.build_list_message(
            to_number=phone_number,
            text=(
                "🛒 No buyer set yet!\n\n"
                "Who should receive the grocery list? "
                "Select a household member to designate as buyer."
            ),
            menu_button_text="Select Buyer",
            sections=[{"title": "Household Members", "rows": rows}],
        ))
        return

    # Buyers exist — fetch list and dispatch
    items = database.get_grocery_list(household_id)
    if not items:
        await _send(WhatsAppUI.build_button_message(
            to_number=phone_number,
            text="🛒 Your grocery list is empty — add some items before sending!",
            buttons=[
                {"id": "CMD_ADD_ITEM",  "title": "➕ Add Item"},
                {"id": "CMD_MAIN_MENU", "title": "Main Menu"},
            ],
        ))
        return

    hh_name = database.get_household_name(household_id)
    item_lines = "\n".join(f"  {decorate_item(i)}" for i in items)
    dispatch_body = (
        f"🛒 *{hh_name}* — Grocery List\n\n"
        f"{item_lines}\n\n"
        f"_Sent via PantryPilot 🚀_"
    )

    sent_count = 0
    for buyer_phone in buyers:
        try:
            await _send({
                "messaging_product": "whatsapp",
                "to": buyer_phone,
                "type": "text",
                "text": {"body": dispatch_body},
            })
            sent_count += 1
        except Exception as exc:
            logger.error("Failed to dispatch list to buyer %s: %s", buyer_phone, exc)

    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=f"✅ Grocery list sent to {sent_count} buyer(s)!",
        buttons=[
            {"id": "CMD_VIEW_GROCERY", "title": "📝 View List"},
            {"id": "CMD_MAIN_MENU",    "title": "Main Menu"},
        ],
    ))


async def _handle_set_buyer(phone_number: str, buyer_phone: str) -> None:
    """Designates a household member as BUYER and immediately dispatches the list."""
    database.set_member_role(buyer_phone, "BUYER")
    logger.info("%s designated %s as BUYER", phone_number, buyer_phone)

    label = "you" if buyer_phone == phone_number else buyer_phone[-6:]
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=f"✅ *{label}* is now the designated buyer!\n\nTapping 'Send to Buyer' again will dispatch the list.",
        buttons=[
            {"id": "CMD_DISPATCH_LIST", "title": "🛒 Send List Now"},
            {"id": "CMD_MAIN_MENU",     "title": "Main Menu"},
        ],
    ))


async def handle_image_action(phone_number: str, media_id: str) -> None:
    """Downloads an image, runs OCR, and adds all detected items to the grocery list."""
    logger.info("IMAGE_UPLOAD for %s (media_id: %s)", phone_number, media_id)
    household_id = database.get_household_id(phone_number)

    await _send_text(phone_number, "📸 Identifying your items... searching for labels... 🔎")

    base64_img = await download_media_base64(media_id)
    if not base64_img:
        await _send_text(phone_number, "❌ Failed to retrieve that image from Meta. Please try again.")
        return

    extracted_text = await analyze_image(base64_img)
    if extracted_text == "NONE":
        await _send_text(phone_number, "I couldn't spot any groceries in that image! Try a clearer photo. 📷")
        return

    items_to_add = [i.strip() for i in extracted_text.split(",") if i.strip()]
    for item in items_to_add:
        database.add_grocery_item(household_id, item)

    hh_name = database.get_household_name(household_id)
    item_lines = "\n".join(f"  {decorate_item(i)}" for i in items_to_add)
    await _send(WhatsAppUI.build_button_message(
        to_number=phone_number,
        text=f"✅ Added {len(items_to_add)} item(s) to *{hh_name}*:\n\n{item_lines}",
        buttons=[
            {"id": "CMD_VIEW_GROCERY",  "title": "📝 View List"},
            {"id": "CMD_DISPATCH_LIST", "title": "🛒 Send to Buyer"},
            {"id": "CMD_MAIN_MENU",     "title": "Main Menu"},
        ],
    ))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _send_text(phone_number: str, body: str) -> None:
    await _send({
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": body},
    })


# ---------------------------------------------------------------------------
# Registry — must be defined AFTER all handlers
# ---------------------------------------------------------------------------

_INTERACTIVE_REGISTRY: dict[str, _Handler] = {
    "CMD_VIEW_GROCERY":   _handle_view_grocery,
    "CMD_ADD_ITEM":       _handle_add_item,
    "CMD_SCAN":           _handle_scan,
    "CMD_COOK":           handle_cook_action,
    "CMD_REMOVE_ITEM":    _handle_remove_item,
    "CMD_CLEAR_LIST":     _handle_clear_list,
    "CMD_INVITE_FAMILY":  _handle_invite_family,
    "CMD_DISPATCH_LIST":  handle_dispatch_list,
    "CMD_MAIN_MENU":      lambda phone: route_text_message(phone, ""),
}
