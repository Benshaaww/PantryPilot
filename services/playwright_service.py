import os
import logging
from playwright.async_api import async_playwright
from db.mongo_client import get_database

logger = logging.getLogger(__name__)

async def fetch_pending_groceries():
    """Queries MongoDB for items that need to be bought."""
    print("[QUERY] Searching MongoDB for pending groceries...")
    try:
        db = await get_database()
        collection = db.groceries
        
        cursor = collection.find({"status": "pending"})
        items = await cursor.to_list(length=100)
        
        shopping_list = []
        for item in items:
            name = item.get("item_name", "Unknown Item")
            qty = item.get("quantity_count", 1)
            item_id = str(item.get("_id"))
            shopping_list.append({"name": name, "quantity": qty, "id": item_id})
            
        print(f"[FOUND] Found {len(shopping_list)} items to buy: {shopping_list}")
        return shopping_list
    except Exception as e:
        logger.error(f"Error fetching pending groceries: {e}")
        return []

from db.grocery_repo import update_item_status

async def automate_grocery_cart():
    """The main Playwright engine."""
    items_to_buy = await fetch_pending_groceries()
    
    if not items_to_buy:
        print("[SKIP] Pantry is full. No items to buy.")
        return

    print("[BOOT] Booting up Playwright Engine for checkout...")
    try:
        async with async_playwright() as p:
            # We keep headless=False to observe the real automation
            browser = await p.chromium.launch(headless=False)
            
            # Mask the default automation fingerprint with a real user agent
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            import asyncio
            
            print("[NAVIGATE] Bootstrapping store connection...")
            await page.goto("https://www.woolworths.co.za/")
            await asyncio.sleep(3) # Wait for initial DOM settling
            
            # --- 1. RESILIENCE: MODAL CLEARING ---
            try:
                # Attempt a soft click on common consent/cookie button patterns
                consent_btn = page.locator("button:has-text('Accept'), button:has-text('Agree'), button:has-text('Close')")
                if await consent_btn.count() > 0:
                    await consent_btn.first.click(timeout=3000)
                    print("[INFO] Cleared consent modal.")
            except Exception:
                # If the modal doesn't exist or times out, we silently continue
                print("[INFO] No blocking modals detected or unable to close them.")

            # --- 2. SEARCH & ADD LOOP ---
            print(f"[ACTION] Processing {len(items_to_buy)} items via Search...")
            
            for item in items_to_buy:
                item_name = item['name']
                item_id = item['id']
                # URL encode the item name for the path parameter
                search_query = item_name.replace(" ", "+")
                search_url = f"https://www.woolworths.co.za/cat?Ntt={search_query}"
                
                print(f"[SEARCH] Looking for: {item_name} -> {search_url}")
                await page.goto(search_url)
                
                try:
                    # Wait for JS to render the search results grid
                    await page.wait_for_load_state('domcontentloaded', timeout=10000)
                    
                    # Wait slightly longer to ensure the DOM hydrates
                    await asyncio.sleep(2)
                    
                    # Target generic "Add to cart" language with built-in auto-waiting
                    await page.locator("button:has-text('Add to cart'), button:has-text('Add')").first.click(timeout=5000)
                    print(f"[SUCCESS] Added {item_name} to cart.")
                    
                    # State Management: Update DB Status to "in_cart"
                    await update_item_status(item_id, "in_cart")
                    print(f"[DB] Updated status of {item_name} to in_cart.")
                    
                    await asyncio.sleep(1) # Let the cart animation finalize
                    
                except Exception as e:
                    # Swallow the specific item failure and move on to the next one
                    # This happens gracefully if the text locator times out after 5s
                    print(f"[WARN] No add to cart button found for {item_name}. Might be out of stock.")
            
            # --- 3. VALIDATION ---
            print("[NAVIGATE] Going to the cart to validate...")
            await page.goto("https://www.woolworths.co.za/checkout/cart")
            
            os.makedirs("tests", exist_ok=True)
            screenshot_path = "tests/poc_cart_success.png"
            
            await asyncio.sleep(4) # Allow images to load
            await page.screenshot(path=screenshot_path)
            print(f"[SUCCESS] Screenshot captured: {screenshot_path}")
            
            await asyncio.sleep(2) # Pausing to let user see final result
            
            await context.close()
            await browser.close()
            print("[DONE] Automated checkout sequence complete.")
    except Exception as e:
        logger.error(f"Playwright automation failed: {e}")
