import logging
import re
from bson.objectid import ObjectId
from schemas.intent_schemas import GroceryItem
from db.mongo_client import get_database

logger = logging.getLogger(__name__)

COLLECTION_NAME = "groceries"

def parse_quantity_to_number(quantity_str: str) -> float:
    """Extracts a numeric value from the quantity string for MongoDB $inc, default to 1.0"""
    match = re.search(r'[\d\.]+', quantity_str)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return 1.0

async def add_or_update_item(item: GroceryItem, family_id: str, requested_by: str = "System"):
    """
    Core deduplication logic targeting MongoDB.
    Uses update_one with $inc and upsert=True.
    Stores who requested the item, scoped to a specific family_id.
    """
    if not family_id:
        logger.error("Attempted to add item without a family_id!")
        return
        
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        inc_amount = parse_quantity_to_number(item.quantity)
        
        logger.info(f"Adding or updating item: {item.item_name} for family {family_id} with inc_amount {inc_amount}")
        
        await collection.update_one(
            {"item_name": item.item_name, "status": "pending", "family_id": family_id},
            {
                "$inc": {"quantity_count": inc_amount},
                "$setOnInsert": {
                    "original_quantity_text": item.quantity,
                    "requested_by": requested_by,
                    "family_id": family_id
                },
                "$set": {
                    "category": item.category,
                    "urgency": item.urgency,
                    "requested_by": requested_by
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Database error in add_or_update_item for {item.item_name}: {e}")

async def get_pending_items(family_id: str) -> list:
    """
    Fetches all documents marked as 'pending' for a specific family.
    """
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        cursor = collection.find({"status": "pending", "family_id": family_id})
        items = await cursor.to_list(length=None)
        
        for item in items:
            item["_id"] = str(item["_id"])
            
        return items
    except Exception as e:
        logger.error(f"Error fetching pending items: {e}")
        return []

async def update_item_status(item_id: str, new_status: str):
    """
    Updates the status field of a specific document using MongoDB ObjectId.
    """
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        result = await collection.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {"status": new_status}}
        )
        if result.modified_count > 0:
            logger.info(f"Updated item {item_id} to status {new_status}")
        else:
            logger.warning(f"Item {item_id} not found or status already {new_status}")
    except Exception as e:
        logger.error(f"Error updating item status for {item_id}: {e}")
