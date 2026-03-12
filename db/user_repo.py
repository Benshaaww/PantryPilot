import logging
import random
import string
from db.mongo_client import get_database
from schemas.user_schemas import User, UserRole

logger = logging.getLogger(__name__)

COLLECTION_NAME = "users"

async def get_user(phone_number: str) -> User | None:
    """Fetches a user by their phone number."""
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        user_doc = await collection.find_one({"phone_number": phone_number})
        if user_doc:
            return User(
                phone_number=user_doc["phone_number"],
                name=user_doc["name"],
                role=UserRole(user_doc["role"]),
                family_id=user_doc.get("family_id"),
                reminder_day=user_doc.get("reminder_day"),
                notification_enabled=user_doc.get("notification_enabled", False),
                chat_history=user_doc.get("chat_history", [])
            )
        return None
    except Exception as e:
        logger.error(f"Error fetching user {phone_number}: {e}")
        return None

async def register_user(phone_number: str, name: str, role: UserRole, family_id: str | None = None) -> User | None:
    """Registers a new user in the database. Generates a family_id if none is provided."""
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        if not family_id:
            # Generate a 6-character uppercase alphanumeric ID
            family_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            logger.info(f"Generated new family_id: {family_id} for user {phone_number}")
            
        user = User(
            phone_number=phone_number, 
            name=name, 
            role=role,
            family_id=family_id,
            reminder_day=None,
            notification_enabled=False
        )
        
        await collection.update_one(
            {"phone_number": phone_number},
            {"$set": {
                "name": name,
                "role": role.value,
                "family_id": family_id
            }, "$setOnInsert": {
                "reminder_day": None,
                "notification_enabled": False
            }},
            upsert=True
        )
        logger.info(f"Registered user: {name} ({phone_number}) as {role.value} in family {family_id}")
        return user
    except Exception as e:
        logger.error(f"Error registering user {phone_number}: {e}")
        return None

async def validate_family_id(family_id: str) -> bool:
    """Checks if a family_id exists in the users collection."""
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        count = await collection.count_documents({"family_id": family_id})
        return count > 0
    except Exception as e:
        logger.error(f"Error validating family_id {family_id}: {e}")
        return False

async def update_user_settings(phone_number: str, reminder_day: str, enabled: bool) -> bool:
    """Updates the user's reminder settings."""
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        result = await collection.update_one(
            {"phone_number": phone_number},
            {"$set": {
                "reminder_day": reminder_day,
                "notification_enabled": enabled
            }}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated settings for user {phone_number}: day={reminder_day}, enabled={enabled}")
            return True
        return False
    except Exception as e:
        return False

async def update_user_history(phone_number: str, role: str, content: str):
    """
    Appends a message to the user's chat history.
    Keeps only the last 6 messages (3 turns).
    """
    try:
        db = await get_database()
        collection = db[COLLECTION_NAME]
        
        # Add new message and slice to last 6
        await collection.update_one(
            {"phone_number": phone_number},
            {
                "$push": {
                    "chat_history": {
                        "$each": [{"role": role, "content": content}],
                        "$slice": -6
                    }
                }
            }
        )
    except Exception as e:
        logger.error(f"Error updating chat history for {phone_number}: {e}")
