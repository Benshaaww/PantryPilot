import json
import re
import os
import logging

logger = logging.getLogger(__name__)

ASSETS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "ui_assets.json")

# 1. Load configuration and compile regex once globally for O(1) matching
_ASSETS = {}
_REGEX = None

try:
    with open(ASSETS_FILE, "r", encoding="utf-8") as f:
        _ASSETS = json.load(f)
        
    # Sort keys by length descending so longer words match first (e.g. "ice cream" before "ice")
    # Escape keys for regex strictly
    escaped_keys = [re.escape(k) for k in sorted(_ASSETS.keys(), key=len, reverse=True)]
    
    # Compile regex: word boundary, capturing group for keys, optional 's' or 'es', word boundary
    pattern = r"\b(" + "|".join(escaped_keys) + r")(?:s|es)?\b"
    _REGEX = re.compile(pattern, re.IGNORECASE)
    logger.info("UI Decorator Engine strictly loaded and compiled regex assets O(1).")
except Exception as e:
    logger.error(f"Failed to load UI Assets config. Fallback emoji only. {e}")
    _ASSETS = {}
    _REGEX = None

def decorate_item(item_name: str) -> str:
    """
    Applies Title Casing and a contextual Unicode Emoji to a clean string natively via internal RegEx hooks.
    """
    if not item_name:
        return ""
        
    clean_name = item_name.strip().title()
    lower_target = item_name.lower()
    
    if _REGEX:
        # Search the entire string for the first matching category
        match = _REGEX.search(lower_target)
        if match:
            # Group 1 is the base key matched
            base_key = match.group(1).lower()
            emoji = _ASSETS.get(base_key, "📦")
            return f"{emoji} {clean_name}"
            
    # Fallback default
    return f"📦 {clean_name}"
