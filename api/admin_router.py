import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from db.grocery_repo import get_pending_items, update_item_status
from services.playwright_service import automate_grocery_cart

logger = logging.getLogger(__name__)

router = APIRouter()

class AdminCommandPayload(BaseModel):
    """Payload representing a direct command from the household admin."""
    command: str

@router.post("/admin/command")
async def handle_admin_command(payload: AdminCommandPayload, background_tasks: BackgroundTasks, family_id: str = "DEFAULT"):
    """
    Webhook endpoint to receive admin commands. 
    If 'Approve All' is received, fetch pending items, update DB status, and trigger Playwright.
    """
    command = payload.command.strip().lower()
    
    if command == "approve all":
        logger.info(f"Received 'Approve All' command from Admin for family {family_id}.")
        
        try:
            # 1. Fetch pending items
            pending_items = await get_pending_items(family_id)
            
            if not pending_items:
                return {"status": "success", "message": "No pending items to approve."}
                
            approved_list = []
            
            # 2. Update status in MongoDB synchronously (within the async route)
            for item in pending_items:
                item_id = str(item["_id"])
                await update_item_status(item_id, "ordered")
                approved_list.append(item)
                
            logger.info(f"Marked {len(approved_list)} items as ordered.")
            
            # 3. Trigger Playwright as a FastAPI Background Task so we don't block the HTTP response
            background_tasks.add_task(automate_grocery_cart, approved_list)
            
            return {"status": "success", "message": "Approval processed. Checkout automation initiated."}
            
        except Exception as e:
            logger.error(f"Error processing Admin command: {e}")
            raise HTTPException(status_code=500, detail="Internal server error managing checkout.")
    
    return {"status": "ignored", "message": "Command not recognized."}
