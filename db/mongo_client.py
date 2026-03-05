import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

async def get_database():
    """
    Initializes and returns the MongoDB database instance asynchronously.
    """
    uri = os.environ.get("MONGO_URI")
    db_name = os.environ.get("MONGO_DB_NAME")
    
    if not uri or not db_name:
        logger.critical("MongoDB credentials missing! Ensure MONGO_URI and MONGO_DB_NAME are set.")
        raise ValueError("Missing MongoDB environment variables.")
        
    try:
        client = AsyncIOMotorClient(uri)
        db = client[db_name]
        return db
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB client: {e}")
        raise
