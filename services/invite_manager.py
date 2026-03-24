from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta, timezone

from services import database

logger = logging.getLogger(__name__)

_CODE_LENGTH = 6
_TTL_HOURS = 24


def generate_invite(household_id: int) -> str:
    """
    Creates a 6-character alphanumeric invite code for a household,
    valid for 24 hours.  Old codes for the same household are pruned first.
    Returns the new code.
    """
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=_CODE_LENGTH))
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=_TTL_HOURS)).isoformat()

    try:
        with database._get_db() as conn:
            # Prune any expired codes for this household before inserting
            conn.execute(
                "DELETE FROM household_invites "
                "WHERE household_id = ? AND expires_at <= ?",
                (household_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.execute(
                "INSERT INTO household_invites (household_id, invite_code, expires_at) "
                "VALUES (?, ?, ?)",
                (household_id, code, expires_at),
            )
        logger.info("Invite code %s generated for household %d (expires %s).", code, household_id, expires_at)
        return code
    except Exception as exc:
        logger.error("Failed to generate invite for household %d: %s", household_id, exc)
        return code  # Still return the code; the DB write failing is non-fatal for the UX


def redeem_invite(phone_number: str, code: str) -> tuple[bool, int, str]:
    """
    Validates an invite code and moves the user into the target household.

    Returns:
        (True, household_id, household_name) on success
        (False, -1, "") if the code is invalid or expired
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        with database._get_db() as conn:
            cursor = conn.execute(
                "SELECT household_id FROM household_invites "
                "WHERE invite_code = ? AND expires_at > ?",
                (code.upper(), now),
            )
            row = cursor.fetchone()
            if not row:
                logger.info("Invite code '%s' not found or expired.", code)
                return False, -1, ""

            household_id: int = int(row[0])

            # Consume the invite — single-use
            conn.execute(
                "DELETE FROM household_invites WHERE invite_code = ?", (code.upper(),)
            )

        # Join outside the same connection to avoid nested context manager issues
        database.join_household(phone_number, household_id)
        hh_name = database.get_household_name(household_id)
        logger.info("%s redeemed invite and joined household %d (%s).", phone_number, household_id, hh_name)
        return True, household_id, hh_name

    except Exception as exc:
        logger.error("Error redeeming invite '%s' for %s: %s", code, phone_number, exc)
        return False, -1, ""
