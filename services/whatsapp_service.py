import os
import tempfile
import httpx
import logging
import base64
from openai import AsyncOpenAI
from agents import household_agent
from db import grocery_repo, user_repo
from schemas.intent_schemas import HouseholdIntentPayload, IntentType
from schemas.user_schemas import User, UserRole
from services import ecommerce_service

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

async def send_interactive_buttons(to_number: str, text_body: str, buttons: list[dict]):
    """
    Sends an interactive message with up to 3 buttons via Meta's Graph API.
    `buttons` should be a list of dicts: [{"id": "btn_1", "title": "Option 1"}, ...]
    """
    try:
        token = os.getenv("WHATSAPP_API_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_ID")
        
        if not token or not phone_id:
            logger.error("Missing WHATSAPP_API_TOKEN or WHATSAPP_PHONE_ID.")
            return False
            
        url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        formatted_buttons = [
            {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
            for b in buttons[:3] # Meta limits to 3 buttons max
        ]
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text_body},
                "action": {
                    "buttons": formatted_buttons
                }
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Successfully sent WhatsApp interactive buttons to {to_number}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to send interactive buttons: {e}")
        print(f"[ERROR] Failed to send interactive buttons: {e}")
        return False

# -- Emoji constants (real UTF-8 chars, safe for JSON/httpx) --
EMOJI_CART = "\U0001F6D2"       # shopping cart
EMOJI_SPARKLES = "\u2728"       # sparkles
EMOJI_LEAF = "\U0001F96C"       # leafy green
EMOJI_MEMO = "\U0001F4DD"       # memo / notepad
EMOJI_MIC = "\U0001F3A4"        # microphone
EMOJI_CAMERA = "\U0001F4F7"     # camera
EMOJI_WAVE = "\U0001F44B"       # waving hand
EMOJI_CHECK = "\u2705"          # white check mark
EMOJI_THINK = "\U0001F914"      # thinking face
EMOJI_SCOOTER = "\U0001F6F5"    # motor scooter (delivery)
EMOJI_RECEIPT = "\U0001F9FE"    # receipt
EMOJI_CLIPBOARD = "\U0001F4CB"  # clipboard

# Aisle emoji map — used for grouping items by category
AISLE_EMOJIS = {
    "produce": EMOJI_LEAF,
    "dairy": "\U0001F95B",       # glass of milk
    "bakery": "\U0001F35E",      # bread
    "meat": "\U0001F969",        # cut of meat
    "frozen": "\u2744\ufe0f",    # snowflake
    "beverages": "\U0001F964",   # cup with straw
    "snacks": "\U0001F36A",      # cookie
    "household": "\U0001F9F9",   # broom
    "personal care": "\U0001F9F4", # lotion bottle
}

# In-memory dictionary to track users who are currently onboarding.
# Maps phone_number to onboarding state (str).
_onboarding_state: dict[str, str] = {}

# In-memory dictionary to stage grocery items before adding them to the DB.
# Maps phone_number -> List of dicts representing GroceryItems
_staging_buffer: dict[str, list] = {}

def _build_confirmation_message(summary: str, item_names: list[str]) -> str:
    """
    Builds a premium, conversational WhatsApp confirmation message.
    Uses real UTF-8 emoji constants that are safe for JSON and httpx.
    """
    if not item_names:
        return (
            f"{EMOJI_CHECK} All sorted! I processed your message "
            f"but didn't spot any new items to add this time."
        )

    count = len(item_names)
    items_bullet = "\n".join(f"  {name}" for name in item_names)

    # Vary the opening line for a human feel
    if count == 1:
        opener = f"Got it! {EMOJI_CART} I've popped *{item_names[0]}* into the virtual pantry:"
    elif count <= 4:
        opener = f"Got it! {EMOJI_CART} I've added *{count}* items to the virtual pantry:"
    else:
        opener = f"Big haul! {EMOJI_CART} *{count}* items just landed in your virtual pantry:"

    cta = (
        f"Would you like me to send over your full grocery list "
        f"so we can double-check it? {EMOJI_SPARKLES}"
    )

    return f"{opener}\n\n{items_bullet}\n\n{cta}"

async def route_payload_to_db(payload: HouseholdIntentPayload, requester_name: str = "System") -> list[str]:
    """
    Takes the structured intent payload from the LangChain agent 
    and iterates through all extracted items, sending them to the 
    repository for smart deduplication.
    Returns a list of item names that were persisted.
    """
    saved_items: list[str] = []
    
    # 1. Standard Groceries
    if payload.standard_groceries:
        for item in payload.standard_groceries:
            await grocery_repo.add_or_update_item(item, requested_by=requester_name)
            saved_items.append(item.item_name)
            
    # 2. Recipes
    if payload.recipe_extractions:
        for recipe in payload.recipe_extractions:
            for item in recipe.ingredients:
                await grocery_repo.add_or_update_item(item, requested_by=requester_name)
                saved_items.append(item.item_name)
                
    # 3. Calendar Predictions
    if payload.calendar_predictions:
        for event in payload.calendar_predictions:
            for item in event.predicted_items:
                await grocery_repo.add_or_update_item(item, requested_by=requester_name)
                saved_items.append(item.item_name)
                
    logger.info(f"Successfully routed {len(saved_items)} items to the database.")
    return saved_items

def _build_grocery_list_message(items: list[dict]) -> str:
    """
    Builds a grouped-by-aisle grocery list message.
    Each item dict is expected to have: item_name, category, quantity_count.
    """
    if not items:
        return (
            f"{EMOJI_CLIPBOARD} Your grocery list is empty! "
            f"Send me items anytime and I'll keep track {EMOJI_SPARKLES}"
        )

    # Group by category
    aisles: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "Other").strip()
        aisles.setdefault(cat, []).append(item)

    lines = [f"{EMOJI_CLIPBOARD} *Here's what's on your list:*\n"]
    for aisle, aisle_items in sorted(aisles.items()):
        emoji = AISLE_EMOJIS.get(aisle.lower(), EMOJI_CART)
        lines.append(f"{emoji} *{aisle}*")
        for it in aisle_items:
            qty = it.get("quantity_count", 1)
            qty_display = int(qty) if qty == int(qty) else qty
            lines.append(f"    - {it['item_name']} (x{qty_display})")
        lines.append("")  # blank line between aisles

    lines.append(
        f"*{len(items)}* items total. "
        f"Want me to order these via Checkers Sixty60? {EMOJI_SCOOTER}"
    )
    return "\n".join(lines)


def _build_checkout_message_grouped(item_count: int, total_zar: float, items: list[dict]) -> str:
    """
    Builds a premium Checkers Sixty60 checkout staged message, grouping by who requested what.
    """
    # Group items by requester
    requesters: dict[str, list[dict]] = {}
    for item in items:
        req_by = item.get("requested_by", "Family")
        requesters.setdefault(req_by, []).append(item)

    lines = [
        f"{EMOJI_SCOOTER} *Checkers Sixty60 Order Staged!*\n",
        f"Your cart has been pre-loaded with *{item_count}* items.\n"
    ]
    
    for req, req_items in sorted(requesters.items()):
        lines.append(f"\n*{req}'s Requests:*")
        for it in req_items:
            lines.append(f"  - {it['name']} (R{it['price']:.2f})")
            
    lines.extend([
        f"\nEstimated Total: *R{total_zar:.2f}*\n",
        f"Reply *CONFIRM* to dispatch the delivery {EMOJI_SPARKLES}"
    ])
    
    return "\n".join(lines)


async def _route_intent(phone_number: str, intent_payload: HouseholdIntentPayload, user: User):
    """
    Central intent router. Handles add_items, read_list, and checkout_sixty60.
    """
    intent = intent_payload.intent
    logger.info(f"Routing intent '{intent.value}' for {phone_number} (User: {user.name}, Role: {user.role.value})")

    if intent == IntentType.ADD_ITEMS:
        # Extract items from all fields in the payload
        extracted_items = []
        if intent_payload.standard_groceries:
            extracted_items.extend([i.dict() for i in intent_payload.standard_groceries])
            
        if intent_payload.recipe_extractions:
            for recipe in intent_payload.recipe_extractions:
                extracted_items.extend([i.dict() for i in recipe.ingredients])
                
        if intent_payload.calendar_predictions:
            for event in intent_payload.calendar_predictions:
                extracted_items.extend([i.dict() for i in event.predicted_items])

        if not extracted_items:
            await send_whatsapp_message(
                phone_number,
                f"{EMOJI_CHECK} All sorted! I processed your message but didn't spot any new items to add to the list this time."
            )
            return

        # Stage the items
        _staging_buffer[phone_number] = extracted_items

        # Build Staging UI
        item_bullet_list = "\n".join([f"  {item['item_name']}" for item in extracted_items])
        msg_text = (
            f"📝 I've extracted these items:\n"
            f"{item_bullet_list}\n\n"
            f"Should I add these to your family pantry?"
        )
        
        buttons = [
            {"id": "commit_pending", "title": "✅ Confirm & Add"},
            {"id": "clear_pending", "title": "✏️ Edit / Try Again"}
        ]
        
        await send_interactive_buttons(phone_number, msg_text, buttons)

    elif intent == IntentType.READ_LIST:
        pending_items = await grocery_repo.get_pending_items(user.family_id)
        reply = _build_grocery_list_message(pending_items)
        await send_whatsapp_message(phone_number, reply)

    elif intent == IntentType.CHECKOUT_SIXTY60:
        if user.role == UserRole.REQUESTER:
            logger.info(f"Checkout blocked for requester {user.name}.")
            await send_whatsapp_message(
                phone_number,
                f"You are registered as a Requester! \U0001F6D1 Only the Family Buyer can authorize Checkers Sixty60 orders."
            )
            return

        pending_items = await grocery_repo.get_pending_items(user.family_id)
        if not pending_items:
            await send_whatsapp_message(
                phone_number,
                f"{EMOJI_CART} Your list is empty! Add some items first, "
                f"then tell me to checkout {EMOJI_SPARKLES}"
            )
            return
        result = await ecommerce_service.push_to_sixty60(pending_items)
            # TODO: Implement _build_checkout_message_grouped
        reply = _build_checkout_message_grouped(result["item_count"], result["estimated_total_zar"], result["items"])
        await send_whatsapp_message(phone_number, reply)

    elif intent == IntentType.RECOMMEND_RECIPES:
        buttons = [
            {"id": "add_recipe_1", "title": "🛒 Add Recipe 1"},
            {"id": "add_recipe_2", "title": "🛒 Add Recipe 2"}
        ]
        await send_interactive_buttons(phone_number, intent_payload.summary, buttons)

    elif intent == IntentType.SETTINGS:
        day = "Thursday"
        for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            if d.lower() in intent_payload.summary.lower():
                day = d
                break
        
        await user_repo.update_user_settings(phone_number, reminder_day=day, enabled=True)
        await send_whatsapp_message(phone_number, f"⚙️ {intent_payload.summary}")


async def check_user_or_onboard(phone_number: str, text: str = "") -> User | None:
    """
    Checks if a user is registered. Handles the onboarding flow if not.
    """
    user = await user_repo.get_user(phone_number)
    
    if user:
        return user
        
    # If not registered, see if they are in the pending dictionary
    state = _onboarding_state.get(phone_number)
    if state:
        if state == "pending_family_id":
            # Let this pass through to process_text_message
            return None
            
        # User is mid-onboarding but sent text instead of a button click.
        await send_whatsapp_message(
            phone_number,
            "🤔 I'm waiting for you to complete setup! Please tap one of the buttons I just sent you."
        )
        return None
            
    # New unrecognized number -> Start Onboarding Step 1
    _onboarding_state[phone_number] = "pending_setup_type"
    welcome_msg = (
        f"🌟 Welcome to PantryPilot! {EMOJI_CART}\n"
        f"Your household's intelligent AI grocery assistant.\n\n"
        f"To configure your account, please select your setup below:"
    )
    buttons = [
        {"id": "onboard_family", "title": "👨‍👩‍👧‍👦 Family Account"},
        {"id": "onboard_single", "title": "👤 Single User"},
        {"id": "onboard_join", "title": "🔗 Join Existing Family"}
    ]
    await send_interactive_buttons(phone_number, welcome_msg, buttons)
    return None

def _get_god_tier_success_msg() -> str:
    return (
        "🌟 Your AI Kitchen is Ready! 🌟\n\n"
        "Try these 'God-Tier' features:\n"
        "🎤 Voice: Hold the mic and speak your list.\n"
        "📸 Vision: Send a photo of your open fridge!\n"
        "🍳 Recipes: Type 'Suggest a dinner' for ideas.\n"
        "⚙️ Settings: Type 'Settings' to schedule your weekly reminder."
    )

async def process_interactive_message(phone_number: str, payload_id: str):
    """
    Handles interactive button replies for the onboarding flow.
    """
    logger.info(f"Received interactive button reply from {phone_number}: {payload_id}")
    
    # --- State Protection ---
    existing_user = await user_repo.get_user(phone_number)
    if existing_user and payload_id in ["onboard_family", "onboard_single", "onboard_join", "role_parent", "role_child"]:
        await send_whatsapp_message(
            phone_number,
            "⚠️ You are already registered! No need to tap those setup buttons again."
        )
        return

    state = _onboarding_state.get(phone_number)
    
    if payload_id.startswith("add_recipe_"):
        await send_whatsapp_message(phone_number, "🛒 Recipe ingredients queued for addition! (Placeholder)")
        return
        
    if payload_id == "commit_pending":
        if phone_number in _staging_buffer:
            items_to_save = _staging_buffer[phone_number]
            user = await user_repo.get_user(phone_number)
            requester_name = user.name if user else "System"
            
            saved_names = []
            for item in items_to_save:
                # Build a temporary GroceryItem object to match the repository signature
                from schemas.intent_schemas import GroceryItem
                item_obj = GroceryItem(
                    item_name=item["item_name"],
                    quantity=item.get("quantity", "1"),
                    category=item.get("category", "Other"),
                    urgency=item.get("urgency", "Normal")
                )
                
                saved = await grocery_repo.add_or_update_item(
                    item=item_obj,
                    family_id=user.family_id,
                    requested_by=requester_name
                )
                if saved is not False:
                    saved_names.append(item["item_name"])
            
            del _staging_buffer[phone_number]
            
            # Send standard confirmation
            confirmation = _build_confirmation_message("Staged items committed", saved_names)
            await send_whatsapp_message(phone_number, confirmation)
        else:
            await send_whatsapp_message(phone_number, "⚠️ I couldn't find any pending items to confirm. Try sending them again!")
        return
        
    if payload_id == "clear_pending":
        if phone_number in _staging_buffer:
            del _staging_buffer[phone_number]
        await send_whatsapp_message(phone_number, "No problem! Go ahead and speak or type the items again.")
        return
        
    if not state:
        logger.warning(f"Received button reply {payload_id} from {phone_number} but no onboarding state found.")
        return

    # STEP 1 Responses (Setup Type)
    if state == "pending_setup_type":
        if payload_id == "onboard_family":
            # Ask for role
            _onboarding_state[phone_number] = "pending_role"
            msg = "🏡 *Family Setup*\nWill you be managing the checkouts, or just requesting items?"
            buttons = [
                {"id": "role_parent", "title": "💳 Parent (Buyer)"},
                {"id": "role_child", "title": "📱 Child (Requester)"}
            ]
            await send_interactive_buttons(phone_number, msg, buttons)
            return
            
        elif payload_id == "onboard_single":
            # Auto-register as Buyer (Family ID generated automatically)
            user = await user_repo.register_user(phone_number, "User", UserRole.BUYER)
            if user:
                del _onboarding_state[phone_number]
                await send_whatsapp_message(phone_number, _get_god_tier_success_msg())
            return
            
        elif payload_id == "onboard_join":
            _onboarding_state[phone_number] = "pending_family_id"
            await send_whatsapp_message(
                phone_number,
                "Please type the 6-digit Family ID provided by your Household Buyer."
            )
            return

    # STEP 2 Responses (Family Role)
    elif state == "pending_role":
        if payload_id == "role_parent":
            user = await user_repo.register_user(phone_number, "Parent", UserRole.BUYER)
            if user:
                del _onboarding_state[phone_number]
                invite_link = f"https://wa.me/[YourBotNumber]?text=Join%20Family%20Code:%20{user.family_id}"
                await send_whatsapp_message(
                    phone_number,
                    f"✅ You are the Buyer! Your Family ID is: *{user.family_id}*.\n\n"
                    f"Hey! Join our family pantry on WhatsApp. Click this link and send the message to get started: {invite_link}\n\n" + _get_god_tier_success_msg()
                )
            return
            
        elif payload_id == "role_child":
            user = await user_repo.register_user(phone_number, "Requester", UserRole.REQUESTER)
            if user:
                del _onboarding_state[phone_number]
                await send_whatsapp_message(phone_number, _get_god_tier_success_msg())
            return

    logger.warning(f"Unhandled interactive payload {payload_id} in state {state}")

async def process_text_message(phone_number: str, text: str):
    """
    Processes a text message via LangChain/ReAct.
    Classifies intent, then routes to the appropriate handler.
    """
    logger.info(f"Processing text message from {phone_number}: {text}")
    print(f"\n[TRACE] whatsapp_service.process_text_message received text: '{text}' [TRACE]")
    
    # Check if they are in the "join family" flow
    state = _onboarding_state.get(phone_number)
    
    # Check for Deep Link pattern
    text_lower = text.strip().lower()
    if text_lower.startswith("join family code:"):
        code = text_lower.split("join family code:")[1].strip().upper()
        if len(code) == 6 and await user_repo.validate_family_id(code):
            user = await user_repo.register_user(phone_number, "Requester", UserRole.REQUESTER, family_id=code)
            if user:
                if phone_number in _onboarding_state:
                    del _onboarding_state[phone_number]
                await send_whatsapp_message(
                    phone_number, 
                    f"✅ Successfully joined Family {code} as a Requester!\n\n" + _get_god_tier_success_msg()
                )
        else:
            await send_whatsapp_message(
                phone_number, 
                "❌ Invalid Family ID in your invite link. Please make sure the code is correct."
            )
        return
        
    if state == "pending_family_id":
        code = text.strip().upper()
        if len(code) == 6 and await user_repo.validate_family_id(code):
            user = await user_repo.register_user(phone_number, "Requester", UserRole.REQUESTER, family_id=code)
            if user:
                del _onboarding_state[phone_number]
                await send_whatsapp_message(
                    phone_number, 
                    f"✅ Successfully joined Family {code} as a Requester!\n\n" + _get_god_tier_success_msg()
                )
        else:
            await send_whatsapp_message(
                phone_number, 
                "❌ Invalid Family ID. Please make sure you typed the 6-character code correctly, or type 'cancel' to restart."
            )
            if text.strip().lower() == "cancel":
                del _onboarding_state[phone_number]
                await check_user_or_onboard(phone_number, "")
        return
    
    user = await check_user_or_onboard(phone_number, text)
    if not user:
        return # Handled by onboarding flow
        
    # --- Status Command ---
    if text.strip().lower() == "status":
        family_id = getattr(user, 'family_id', None)
        
        if not family_id:
            status_msg = "🏠 Family ID: Not Linked (Type 'Join Family' to start)"
        else:
            pending_items = await grocery_repo.get_pending_items(family_id)
            staged_items = _staging_buffer.get(phone_number, [])
            status_msg = (
                f"🏠 Family ID: {family_id}\n"
                f"👤 Role: {user.role.value.capitalize()}\n"
                f"📦 Staged Items: {len(staged_items)}\n"
                f"🛒 Current List: {len(pending_items)}\n"
                f"💡 Tip: Try sending a voice note or a photo of your fridge!"
            )
        await send_whatsapp_message(phone_number, status_msg)
        return
    
    # Send natural language to the Intent Engine
    # TODO: Update agent to receive user context
    intent_payload = await household_agent.process_user_intent(text)
    
    if intent_payload:
        logger.info(f"Agent classified intent: {intent_payload.intent.value} | {intent_payload.summary}")
        print(f"[TRACE] Agent returned intent: {intent_payload.intent.value} [TRACE]")
        await _route_intent(phone_number, intent_payload, user)
    else:
        logger.warning(f"Agent failed to parse intent for message: {text}")
        print(f"[TRACE] Agent failed to parse intent, returned None! [TRACE]")
        await send_whatsapp_message(
            phone_number,
            f"{EMOJI_THINK} Hmm, I couldn't quite figure that one out. "
            f"Could you rephrase it or send the items one more time?"
        )

async def _download_media_from_meta(media_id: str) -> bytes:
    """
    Two-step Meta media download:
    1. GET the media metadata to obtain the download URL.
    2. GET the actual binary from that URL.
    Returns the raw audio bytes.
    """
    token = os.getenv("WHATSAPP_API_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1 - get the CDN url
        meta_resp = await client.get(
            f"https://graph.facebook.com/v18.0/{media_id}",
            headers=headers,
        )
        meta_resp.raise_for_status()
        download_url = meta_resp.json()["url"]

        # Step 2 - download the binary
        audio_resp = await client.get(download_url, headers=headers)
        audio_resp.raise_for_status()
        return audio_resp.content


async def _transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """
    Saves audio bytes to a temp .ogg file and sends it to
    OpenAI Whisper (whisper-1) for transcription.
    Returns the transcribed text.
    """
    # Choose extension from mime type (Meta usually sends audio/ogg)
    ext = ".ogg"
    if "mp4" in mime_type:
        ext = ".m4a"
    elif "mpeg" in mime_type:
        ext = ".mp3"

    tmp_path = None
    try:
        # Write to a named temp file so we can pass its path to OpenAI
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        client = AsyncOpenAI()  # picks up OPENAI_API_KEY from env
        with open(tmp_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return transcript.text
    finally:
        # Cleanup - always delete the temp file
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.info(f"Cleaned up temp audio file: {tmp_path}")


async def process_audio_message(phone_number: str, audio_id: str, mime_type: str):
    """
    Full audio pipeline:
    1. Download audio binary from Meta Graph API
    2. Transcribe via OpenAI Whisper
    3. Route transcription through the LangGraph intent engine
    """
    logger.info(f"Processing audio message from {phone_number}, audio_id: {audio_id}")
    try:
        user = await check_user_or_onboard(phone_number, "")
        if not user:
            return
            
        await send_whatsapp_message(
            phone_number,
            "🎧 Processing your voice note..."
        )

        # --- Download ---
        logger.info(f"Downloading audio media {audio_id} from Meta...")
        audio_bytes = await _download_media_from_meta(audio_id)
        logger.info(f"Downloaded {len(audio_bytes)} bytes of audio.")

        # --- Transcribe ---
        logger.info("Sending audio to Whisper for transcription...")
        transcription = await _transcribe_audio(audio_bytes, mime_type)
        logger.info(f"Whisper transcription: '{transcription}'")
        print(f"[TRACE] Whisper transcription: '{transcription}' [TRACE]")

        if not transcription or not transcription.strip():
            await send_whatsapp_message(
                phone_number,
                f"{EMOJI_MIC} I received your voice note, but it sounded empty. "
                f"Could you try recording it again?"
            )
            return

        # --- Route through the agent (same path as text) ---
        intent_payload = await household_agent.process_user_intent(transcription)
        if intent_payload:
            await _route_intent(phone_number, intent_payload, user)
        else:
            await send_whatsapp_message(
                phone_number,
                f"{EMOJI_MIC} I got your voice note, but couldn't pick out any items. "
                f"Mind sending it again a little slower?"
            )

    except Exception as e:
        logger.error(f"Audio pipeline error for {phone_number}: {e}", exc_info=True)
        await send_whatsapp_message(
            phone_number,
            f"{EMOJI_MIC} Oops! Something went wrong while processing your voice note. "
            f"Could you try sending it again, or just type the items instead?"
        )

async def process_image_message(phone_number: str, image_id: str, mime_type: str):
    """
    Downloads an image, passes it to OpenAI GPT-4o Vision for fridge analysis.
    """
    logger.info(f"Processing image message from {phone_number}, image_id: {image_id}")
    try:
        user = await check_user_or_onboard(phone_number, "")
        if not user:
            return
            
        await send_whatsapp_message(
            phone_number,
            "📸 Scanning your fridge/pantry for missing items..."
        )
        
        # 1. Download
        image_bytes = await _download_media_from_meta(image_id)
        
        # 2. Encode to base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # 3. Vision Prompt
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at visual inventory. Analyze this fridge/pantry photo. Identify items that are nearly empty or missing. Keep it concise. Return ONLY a comma-separated list of the missing item names. No conversational text."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What are we missing?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        
        analysis = response.choices[0].message.content
        logger.info(f"Vision analysis complete for {phone_number}.")
        
        # 4. Reply & Stage
        if not analysis or analysis.strip() == "":
            await send_whatsapp_message(phone_number, f"{EMOJI_CHECK} Looks good! I don't see anything missing.")
            return
            
        # Parse the CSV returned by the vision model
        items = [i.strip() for i in analysis.split(",") if i.strip()]
        if not items:
            await send_whatsapp_message(phone_number, f"{EMOJI_CHECK} Looks good! I didn't spot any clear missing items.")
            return
            
        extracted_items = []
        for item_name in items:
            extracted_items.append({
                "item_name": item_name,
                "quantity": "1",
                "category": "Other",
                "urgency": "Normal"
            })
            
        _staging_buffer[phone_number] = extracted_items
        
        item_bullet_list = "\n".join([f"  {item['item_name']}" for item in extracted_items])
        msg_text = (
            f"📸 I've spotted these missing items from your photo:\n"
            f"{item_bullet_list}\n\n"
            f"Should I add these to your family pantry?"
        )
        
        buttons = [
            {"id": "commit_pending", "title": "✅ Confirm & Add"},
            {"id": "clear_pending", "title": "✏️ Edit / Try Again"}
        ]
        
        await send_interactive_buttons(phone_number, msg_text, buttons)
        
    except Exception as e:
        logger.error(f"Vision pipeline error for {phone_number}: {e}", exc_info=True)
        await send_whatsapp_message(
            phone_number,
            f"{EMOJI_CAMERA} Oops! I had trouble scanning that photo. "
            f"Could you try sending it again, or just type the items instead?"
        )
