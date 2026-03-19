import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_PATH = "pantry.db"

def init_db() -> None:
    """
    Initializes the local SQLite database. Uses WAL journaling
    to handle concurrent webhook reads and writes efficiently without blocking.
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            # Enable WAL mode for strict concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pantry_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    phone_number TEXT, 
                    item_name TEXT, 
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # O(1) Lookups for phone numbers
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON pantry_items(phone_number);")
            
            logger.info(f"Database successfully initialized at {DB_PATH}")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize SQLite database: {e}")

def add_item(phone_number: str, item_name: str) -> bool:
    """Inserts a new item into the user's pantry strictly and defensively."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "INSERT INTO pantry_items (phone_number, item_name) VALUES (?, ?)", 
                (phone_number, item_name)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while adding item for {phone_number}: {e}")
        return False

def get_inventory(phone_number: str) -> list[str]:
    """Retrieves all items currently in the user's pantry."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            cursor = conn.execute(
                "SELECT item_name FROM pantry_items WHERE phone_number = ? ORDER BY added_at ASC", 
                (phone_number,)
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error while retrieving inventory for {phone_number}: {e}")
        return []

def clear_pantry(phone_number: str) -> bool:
    """Deletes all items associated with a phone_number."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "DELETE FROM pantry_items WHERE phone_number = ?", 
                (phone_number,)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while clearing pantry for {phone_number}: {e}")
        return False
