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
    Sets WAL journaling, NORMAL sync, and FK enforcement on every connection.
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
    Initialises the SQLite schema.
    Handles all migrations:
      - v1 → v2: phone-keyed pantry_items → household model
      - v2 → v3: pantry_items → grocery (shopping_list), invite codes, buyer roles
    """
    try:
        with _get_db() as conn:

            # --- Core tables ---
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
                    role TEXT NOT NULL DEFAULT 'MEMBER',
                    FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                )
            ''')

            # Migration: add role column if it doesn't exist yet (v2 → v3)
            cursor = conn.execute("PRAGMA table_info(user_households)")
            uh_cols = [col[1] for col in cursor.fetchall()]
            if "role" not in uh_cols:
                conn.execute(
                    "ALTER TABLE user_households ADD COLUMN role TEXT NOT NULL DEFAULT 'MEMBER'"
                )
                logger.info("Migrated user_households: added role column.")

            # --- Grocery list (primary data table) ---
            conn.execute('''
                CREATE TABLE IF NOT EXISTS shopping_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                )
            ''')
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_grocery_household "
                "ON shopping_list(household_id);"
            )

            # --- Invitation codes ---
            conn.execute('''
                CREATE TABLE IF NOT EXISTS household_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    household_id INTEGER NOT NULL,
                    invite_code TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
                )
            ''')

            # --- v1 legacy migration: phone_number-keyed pantry_items ---
            cursor = conn.execute("PRAGMA table_info(pantry_items)")
            pantry_cols = [col[1] for col in cursor.fetchall()]

            if pantry_cols and "phone_number" in pantry_cols:
                logger.info("v1 pantry_items detected — migrating to household grocery model.")
                cursor = conn.execute("SELECT DISTINCT phone_number FROM pantry_items")
                for (phone,) in cursor.fetchall():
                    cur2 = conn.execute(
                        "INSERT INTO households (household_name) VALUES (?)", ("My Groceries",)
                    )
                    new_hh_id = cur2.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO user_households (phone_number, household_id) "
                        "VALUES (?, ?)", (phone, new_hh_id)
                    )
                    conn.execute('''
                        INSERT INTO shopping_list (household_id, item_name, added_at)
                        SELECT ?, item_name, added_at FROM pantry_items WHERE phone_number = ?
                    ''', (new_hh_id, phone))
                conn.execute("DROP TABLE pantry_items")
                logger.info("v1 migration complete — pantry_items merged into grocery list.")

            # --- v2 legacy migration: household_id-keyed pantry_items → shopping_list ---
            elif pantry_cols and "household_id" in pantry_cols:
                logger.info("v2 pantry_items detected — merging into grocery list.")
                conn.execute('''
                    INSERT OR IGNORE INTO shopping_list (household_id, item_name, added_at)
                    SELECT household_id, item_name, added_at FROM pantry_items
                ''')
                conn.execute("DROP TABLE pantry_items")
                logger.info("v2 migration complete — pantry_items merged into grocery list.")

            logger.info("Database initialised at %s", DB_PATH)

    except sqlite3.Error as exc:
        logger.error("Failed to initialise database: %s", exc)


def health_check() -> bool:
    """Runs a SELECT 1 to verify the DB is reachable. Called on server startup."""
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
    Auto-provisions a 'My Groceries' household for first-time users.
    Returns -1 on error.
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
                "INSERT INTO households (household_name) VALUES (?)", ("My Groceries",)
            )
            new_hh_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO user_households (phone_number, household_id, role) VALUES (?, ?, ?)",
                (phone_number, new_hh_id, "MEMBER"),
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


def get_household_members(household_id: int) -> list[str]:
    """Returns all phone numbers belonging to a household."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT phone_number FROM user_households WHERE household_id = ?",
                (household_id,),
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("DB error fetching members for household %d: %s", household_id, exc)
        return []


def get_household_buyers(household_id: int) -> list[str]:
    """Returns phone numbers of all members with the BUYER role."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT phone_number FROM user_households "
                "WHERE household_id = ? AND role = 'BUYER'",
                (household_id,),
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("DB error fetching buyers for household %d: %s", household_id, exc)
        return []


def set_member_role(phone_number: str, role: str) -> bool:
    """Sets the role ('MEMBER' or 'BUYER') for a given phone number."""
    try:
        with _get_db() as conn:
            conn.execute(
                "UPDATE user_households SET role = ? WHERE phone_number = ?",
                (role, phone_number),
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error setting role for %s: %s", phone_number, exc)
        return False


def join_household(phone_number: str, target_id: int) -> bool:
    """Links a user to an existing household by ID. Returns False if not found."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM households WHERE id = ?", (target_id,)
            )
            if not cursor.fetchone():
                return False
            conn.execute('''
                INSERT INTO user_households (phone_number, household_id, role)
                VALUES (?, ?, 'MEMBER')
                ON CONFLICT(phone_number) DO UPDATE SET
                    household_id = excluded.household_id,
                    role = 'MEMBER'
            ''', (phone_number, target_id))
            return True
    except sqlite3.Error as exc:
        logger.error("Error joining household %d for %s: %s", target_id, phone_number, exc)
        return False


# ---------------------------------------------------------------------------
# Grocery List CRUD  (shopping_list is the single source of truth)
# ---------------------------------------------------------------------------

def add_grocery_item(household_id: int, item_name: str) -> bool:
    """Adds an item directly to the household grocery list."""
    try:
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO shopping_list (household_id, item_name) VALUES (?, ?)",
                (household_id, item_name),
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error adding grocery item for household %d: %s", household_id, exc)
        return False


def get_grocery_list(household_id: int) -> list[str]:
    """Returns all items on the household grocery list, oldest first."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT item_name FROM shopping_list "
                "WHERE household_id = ? ORDER BY added_at ASC",
                (household_id,),
            )
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("DB error fetching grocery list for household %d: %s", household_id, exc)
        return []


def delete_grocery_item(household_id: int, item_name: str) -> bool:
    """Removes a single item from the household grocery list by name."""
    try:
        with _get_db() as conn:
            conn.execute(
                "DELETE FROM shopping_list WHERE household_id = ? AND item_name = ?",
                (household_id, item_name),
            )
        return True
    except sqlite3.Error as exc:
        logger.error(
            "DB error deleting '%s' from grocery list for household %d: %s",
            item_name, household_id, exc,
        )
        return False


def clear_grocery_list(household_id: int) -> bool:
    """Clears all items from the household grocery list."""
    try:
        with _get_db() as conn:
            conn.execute(
                "DELETE FROM shopping_list WHERE household_id = ?", (household_id,)
            )
        return True
    except sqlite3.Error as exc:
        logger.error("DB error clearing grocery list for household %d: %s", household_id, exc)
        return False
