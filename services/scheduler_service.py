import os
import logging
from db.mongo_client import get_database
from services.whatsapp_service import send_whatsapp_message

logger = logging.getLogger(__name__)

async def generate_daily_summary():
    """
    Queries MongoDB for pending grocery items and generates a clean,
    emoji-free daily summary report for the Household Admin.
    """
    try:
        db = await get_database()
        collection = db.groceries
        
        # Query for unbought/pending items
        cursor = collection.find({"status": "pending"})
        items = await cursor.to_list(length=200)
        
        if not items:
            report = "Pantry is fully stocked. No pending items to report."
            print(report)
            admin_number = os.getenv("WHATSAPP_ADMIN_NUMBER", "1234567890")
            await send_whatsapp_message(admin_number, report)
            return report
            
        report_parts = ["Daily Pantry Report:"]
        item_strings = []
        
        for item in items:
            name = item.get("item_name", "Unknown Item")
            qty = item.get("quantity_count", 1)
            # Format: '1x Milk'
            # Convert float quantity to int if it's a whole number for cleaner display
            if isinstance(qty, float) and qty.is_integer():
                qty = int(qty)
            item_strings.append(f"{qty}x {name}")
            
        final_report = "Daily Pantry Report: " + ", ".join(item_strings)
        
        # Crucial: Emitting cleanly to terminal with NO EMOJIS to avoid UnicodeEncodeError in PowerShell
        print("\n" + "="*30)
        print(final_report)
        print("="*30 + "\n")
        
        # Send to WhatsApp
        admin_number = os.getenv("WHATSAPP_ADMIN_NUMBER", "1234567890")
        await send_whatsapp_message(admin_number, final_report)
        
        return final_report
        
    except Exception as e:
        logger.error(f"Failed to generate daily summary: {e}")
        return "Error generating daily summary."


# Optional block for manual testing
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    # Force load the environment variables before running
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(override=True)
    asyncio.run(generate_daily_summary())
