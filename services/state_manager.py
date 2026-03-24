from __future__ import annotations

import time
from typing import Optional

# Robust Memory Bank
# Mapping of phone_number -> {"state": str, "timestamp": float}
USER_STATES: dict[str, dict[str, float | str]] = {}

# Deduplication Cache
# Mapping of message_id -> timestamp (float)
PROCESSED_MESSAGES: dict[str, float] = {}

STATE_TTL_SECONDS = 300  # 5 minutes
MESSAGE_TTL_SECONDS = 600  # 10 minutes

def cleanup_stale_data() -> None:
    """Removes expired states and processed messages to prevent memory leaks."""
    now = time.time()
    
    # Clean USER_STATES
    stale_phones = [
        phone for phone, data in USER_STATES.items() 
        if now - float(data["timestamp"]) > STATE_TTL_SECONDS
    ]
    for phone in stale_phones:
        del USER_STATES[phone]
        
    # Clean PROCESSED_MESSAGES
    stale_messages = [
        msg_id for msg_id, ts in PROCESSED_MESSAGES.items() 
        if now - ts > MESSAGE_TTL_SECONDS
    ]
    for msg_id in stale_messages:
        del PROCESSED_MESSAGES[msg_id]

def set_state(phone: str, state: str) -> None:
    """Sets the user's state securely and triggers memory cleanup."""
    cleanup_stale_data()
    USER_STATES[phone] = {"state": state, "timestamp": time.time()}

def get_state(phone: str) -> Optional[str]:
    """Gets the user's active state if it exists and hasn't expired."""
    cleanup_stale_data()
    user_data = USER_STATES.get(phone)
    if user_data:
        return str(user_data["state"])
    return None

def clear_state(phone: str) -> None:
    """Clears the user's state manually."""
    cleanup_stale_data()
    if phone in USER_STATES:
        del USER_STATES[phone]

def is_duplicate_message(message_id: str) -> bool:
    """
    Checks if a message_id has been processed recently.
    If not, records it to prevent future duplicates.
    """
    cleanup_stale_data()
    if message_id in PROCESSED_MESSAGES:
        return True
    
    PROCESSED_MESSAGES[message_id] = time.time()
    return False
