import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_PATH = "pantry.db"

def init_db() -> None:
    """
    Initializes the SQLite database with WAL journaling and Foreign Keys.
    Handles automated schema migrations from Single-User to Multi-User Household architectures.
    """
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            # Enable WAL mode for strict concurrency and Foreign Keys
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            
            # --- SCHEMA V2: HouseHolds & User Links ---
            conn.execute('''
                CREATE TABLE IF NOT EXISTS households (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_name TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_households (
                    phone_number TEXT PRIMARY KEY,
                    household_id INTEGER NOT NULL,
                    FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                )
            ''')
            
            # Check if we need to migrate the legacy table
            cursor = conn.execute("PRAGMA table_info(pantry_items)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if "phone_number" in columns:
                logger.info("Legacy pantry_items schema detected. Commencing V2 Multi-User Migration...")
                
                # Create the V2 structured table
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS pantry_items_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        household_id INTEGER NOT NULL, 
                        item_name TEXT, 
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                    )
                ''')
                
                # Fetch distinct users from legacy table
                cursor = conn.execute("SELECT DISTINCT phone_number FROM pantry_items")
                legacy_users = [row[0] for row in cursor.fetchall()]
                
                for phone in legacy_users:
                    # Create default household
                    cursor = conn.execute("INSERT INTO households (household_name) VALUES (?)", ("Private Pantry",))
                    new_hh_id = cursor.lastrowid
                    
                    # Link user
                    conn.execute("INSERT OR IGNORE INTO user_households (phone_number, household_id) VALUES (?, ?)", (phone, new_hh_id))
                    
                    # Migrate items sideways over to V2 table assigned to new user household ID
                    conn.execute('''
                        INSERT INTO pantry_items_v2 (household_id, item_name, added_at)
                        SELECT ?, item_name, added_at FROM pantry_items WHERE phone_number = ?
                    ''', (new_hh_id, phone))
                
                # Swap out old tables seamlessly
                conn.execute("DROP TABLE pantry_items")
                conn.execute("ALTER TABLE pantry_items_v2 RENAME TO pantry_items")
                
                logger.info("Successfully migrated Legacy database to Multi-User Relational Architecture.")
            else:
                # Normal creation if starting fresh or already migrated
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS pantry_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        household_id INTEGER NOT NULL, 
                        item_name TEXT, 
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                    )
                ''')
                
            # Create Shopping List Table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS shopping_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL,
                    item_name TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                )
            ''')
                
            # O(1) Lookups for household IDs
            conn.execute("CREATE INDEX IF NOT EXISTS idx_household ON pantry_items(household_id);")
            logger.info(f"Database successfully initialized at {DB_PATH}")
            
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize SQLite database: {e}")

def get_household_id(phone_number: str) -> int:
    """Gets a user's household ID, generating a default 'Private Pantry' if disconnected."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cursor = conn.execute("SELECT household_id FROM user_households WHERE phone_number = ?", (phone_number,))
            row = cursor.fetchone()
            
            if row:
                return row[0]
                
            # Create a default Private Pantry for new connections
            cursor = conn.execute("INSERT INTO households (household_name) VALUES (?)", ("Private Pantry",))
            new_hh_id = cursor.lastrowid
            conn.execute("INSERT INTO user_households (phone_number, household_id) VALUES (?, ?)", (phone_number, new_hh_id))
            
            return new_hh_id
    except sqlite3.Error as e:
        logger.error(f"Database error resolving household for {phone_number}: {e}")
        return -1

def get_household_name(household_id: int) -> str:
    """Retrieves the plaintext string representing a household's name."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            cursor = conn.execute("SELECT household_name FROM households WHERE id = ?", (household_id,))
            row = cursor.fetchone()
            return row[0] if row else "Unknown"
    except sqlite3.Error:
        return "Unknown"

def join_household(phone_number: str, target_id: int) -> bool:
    """Updates a user's household_id pointer to link them to an existing shared household."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            # Check if target_id exists safely
            cursor = conn.execute("SELECT id FROM households WHERE id = ?", (target_id,))
            if not cursor.fetchone():
                return False
                
            # Perform upsert binding them to the new home
            conn.execute('''
                INSERT INTO user_households (phone_number, household_id) 
                VALUES (?, ?)
                ON CONFLICT(phone_number) DO UPDATE SET household_id=excluded.household_id
            ''', (phone_number, target_id))
            return True
    except sqlite3.Error as e:
        logger.error(f"Error joining household {target_id} for {phone_number}: {e}")
        return False

def add_item(household_id: int, item_name: str) -> bool:
    """Inserts a new item into the household's pantry strictly and defensively."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "INSERT INTO pantry_items (household_id, item_name) VALUES (?, ?)", 
                (household_id, item_name)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while adding item for household {household_id}: {e}")
        return False

def get_inventory(household_id: int) -> list[str]:
    """Retrieves all items currently in the household's pantry."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            cursor = conn.execute(
                "SELECT item_name FROM pantry_items WHERE household_id = ? ORDER BY added_at ASC", 
                (household_id,)
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error while retrieving inventory for household {household_id}: {e}")
        return []

def clear_pantry(household_id: int) -> bool:
    """Deletes all items associated with a household_id."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "DELETE FROM pantry_items WHERE household_id = ?", 
                (household_id,)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while clearing pantry for household {household_id}: {e}")
        return False

def delete_item_by_name(household_id: int, item_name: str) -> bool:
    """Removes a specific item from the household's pantry cleanly."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "DELETE FROM pantry_items WHERE household_id = ? AND item_name = ?", 
                (household_id, item_name)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while deleting item {item_name} for household {household_id}: {e}")
        return False

def add_to_shopping_list(household_id: int, item_name: str) -> bool:
    """Inserts an item directly into the household's shopping list ledger."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "INSERT INTO shopping_list (household_id, item_name) VALUES (?, ?)", 
                (household_id, item_name)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while adding to shopping list for household {household_id}: {e}")
        return False

def get_shopping_list(household_id: int) -> list[str]:
    """Retrieves all items currently in the household's shopping list ledger."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            cursor = conn.execute(
                "SELECT item_name FROM shopping_list WHERE household_id = ? ORDER BY added_at ASC", 
                (household_id,)
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Database error while retrieving shopping list for household {household_id}: {e}")
        return []

def clear_shopping_list(household_id: int) -> bool:
    """Deletes all items associated with a household's shopping ledger."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            conn.execute(
                "DELETE FROM shopping_list WHERE household_id = ?", 
                (household_id,)
            )
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error while clearing shopping list for household {household_id}: {e}")
        return False
