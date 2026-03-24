from __future__ import annotations

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

DB_PATH = "pantry.db"


# ---------------------------------------------------------------------------
# Shared Connection Context Manager
# ---------------------------------------------------------------------------

@contextmanager
def _get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Yields a fully configured SQLite connection.
    Sets WAL journaling, NORMAL sync, and FK enforcement on every connection
    so callers never have to remember pragma boilerplate.
    Commits on clean exit; rolls back on exception.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Startup / Health
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Initialises the SQLite schema with WAL journaling and FK constraints.
    Handles automated schema migration from the single-user v1 model to
    the multi-user household model.
    """
    try:
        with _get_db() as conn:
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

            # Detect legacy single-user schema and migrate if needed
            cursor = conn.execute("PRAGMA table_info(pantry_items)")
            columns = [col[1] for col in cursor.fetchall()]

            if "phone_number" in columns:
                logger.info("Legacy pantry_items schema detected — running v2 migration.")

                conn.execute('''
                    CREATE TABLE IF NOT EXISTS pantry_items_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        household_id INTEGER NOT NULL,
                        item_name TEXT,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                    )
                ''')

                cursor = conn.execute("SELECT DISTINCT phone_number FROM pantry_items")
                for (phone,) in cursor.fetchall():
                    cursor2 = conn.execute(
                        "INSERT INTO households (household_name) VALUES (?)", ("Private Pantry",)
                    )
                    new_hh_id = cursor2.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO user_households (phone_number, household_id) VALUES (?, ?)",
                        (phone, new_hh_id),
                    )
                    conn.execute('''
                        INSERT INTO pantry_items_v2 (household_id, item_name, added_at)
                        SELECT ?, item_name, added_at FROM pantry_items WHERE phone_number = ?
                    ''', (new_hh_id, phone))

                conn.execute("DROP TABLE pantry_items")
                conn.execute("ALTER TABLE pantry_items_v2 RENAME TO pantry_items")
                logger.info("Migration to multi-user household schema complete.")
            else:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS pantry_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        household_id INTEGER NOT NULL,
                        item_name TEXT,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                    )
                ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS shopping_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL,
                    item_name TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                )
            ''')

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pantry_household ON pantry_items(household_id);"
            )
            logger.info("Database initialised at %s", DB_PATH)

    except sqlite3.Error as exc:
        logger.error("Failed to initialise database: %s", exc)


def health_check() -> bool:
    """
    Runs a trivial SELECT 1 to verify the database file is reachable
    and the connection stack is healthy.  Called on server startup.
    """
    try:
        with _get_db() as conn:
            conn.execute("SELECT 1")
        logger.info("Database health check passed.")
        return True
    except sqlite3.Error as exc:
        logger.error("Database health check FAILED: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Household / User Resolution
# ---------------------------------------------------------------------------

def get_household_id(phone_number: str) -> int:
    """
    Returns the household_id for this phone number.
    Auto-provisions a new 'Private Pantry' household for first-time users.
    Returns -1 on database error.
    """
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT household_id FROM user_households WHERE phone_number = ?",
                (phone_number,),
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

            cursor = conn.execute(
                "INSERT INTO households (household_name) VALUES (?)", ("Private Pantry",)
            )
            new_hh_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO user_households (phone_number, household_id) VALUES (?, ?)",
                (phone_number, new_hh_id),
            )
            return int(new_hh_id)
    except sqlite3.Error as exc:
        logger.error("DB error resolving household for %s: %s", phone_number, exc)
        return -1


def get_household_name(household_id: int) -> str:
    """Returns the display name for a household, or 'Unknown' on error."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT household_name FROM households WHERE id = ?", (household_id,)
            )
            row = cursor.fetchone()
            return str(row[0]) if row else "Unknown"
    except sqlite3.Error:
        return "Unknown"


def join_household(phone_number: str, target_id: int) -> bool:
    """Links a user to an existing household by ID.  Returns False if the ID does not exist."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM households WHERE id = ?", (target_id,)
            )
            if not cursor.fetchone():
                return False
            conn.execute('''
                INSERT INTO user_households (phone_number, household_id)
                VALUES (?, ?)
                ON CONFLICT(phone_number) DO UPDATE SET household_id = excluded.household_id
            ''', (phone_number, target_id))
            return True
    except sqlite3.Error as exc:
        logger.error("Error joining household %d for %s: %s", target_id, phone_number, exc)
        return False


# ---------------------------------------------------------------------------
# Pantry CRUD
# ---------------------------------------------------------------------------

def add_item(household_id: int, item_name: str) -> bool:
    """Inserts a new item into the household pantry."""
    try:
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO pantry_items (household_id, item_name) VALUES (?, ?)",
                (household_id, item_name),
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error adding item for household %d: %s", household_id, exc)
        return False


def get_inventory(household_id: int) -> list[str]:
    """Returns all pantry items for a household, ordered by insertion time."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT item_name FROM pantry_items WHERE household_id = ? ORDER BY added_at ASC",
                (household_id,),
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("DB error retrieving inventory for household %d: %s", household_id, exc)
        return []


def clear_pantry(household_id: int) -> bool:
    """Deletes all pantry items for a household."""
    try:
        with _get_db() as conn:
            conn.execute(
                "DELETE FROM pantry_items WHERE household_id = ?", (household_id,)
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error clearing pantry for household %d: %s", household_id, exc)
        return False


def delete_item_by_name(household_id: int, item_name: str) -> bool:
    """Removes a named item from a household's pantry."""
    try:
        with _get_db() as conn:
            conn.execute(
                "DELETE FROM pantry_items WHERE household_id = ? AND item_name = ?",
                (household_id, item_name),
            )
        return True
    except sqlite3.Error as exc:
        logger.error(
            "DB error deleting item '%s' for household %d: %s", item_name, household_id, exc
        )
        return False


# ---------------------------------------------------------------------------
# Shopping List CRUD
# ---------------------------------------------------------------------------

def add_to_shopping_list(household_id: int, item_name: str) -> bool:
    """Appends an item to the household shopping list."""
    try:
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO shopping_list (household_id, item_name) VALUES (?, ?)",
                (household_id, item_name),
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error adding to shopping list for household %d: %s", household_id, exc)
        return False


def get_shopping_list(household_id: int) -> list[str]:
    """Returns all items on the household shopping list."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT item_name FROM shopping_list WHERE household_id = ? ORDER BY added_at ASC",
                (household_id,),
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("DB error retrieving shopping list for household %d: %s", household_id, exc)
        return []


def clear_shopping_list(household_id: int) -> bool:
    """Clears all items from the household shopping list."""
    try:
        with _get_db() as conn:
            conn.execute(
                "DELETE FROM shopping_list WHERE household_id = ?", (household_id,)
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error clearing shopping list for household %d: %s", household_id, exc)
        return False
