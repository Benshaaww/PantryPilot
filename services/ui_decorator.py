from __future__ import annotations

import json
import os
import re
import logging

logger = logging.getLogger(__name__)

_ASSETS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "ui_assets.json")

# ---------------------------------------------------------------------------
# Singleton: load config and compile regex once at module import time
# ---------------------------------------------------------------------------

_ASSETS: dict[str, str] = {}
_REGEX: re.Pattern[str] | None = None

try:
    with open(_ASSETS_FILE, "r", encoding="utf-8") as _f:
        _ASSETS = json.load(_f)

    # Sort keys longest-first so multi-word keys (e.g. "ice cream") win over
    # single-word sub-keys (e.g. "ice").
    _escaped = [re.escape(k) for k in sorted(_ASSETS.keys(), key=len, reverse=True)]
    _REGEX = re.compile(
        r"\b(" + "|".join(_escaped) + r")(?:s|es)?\b",
        re.IGNORECASE,
    )
    logger.info("UI Decorator Engine loaded — %d emoji mappings compiled.", len(_ASSETS))
except Exception as exc:
    logger.error("Failed to load UI assets; falling back to 📦. %s", exc)
    _ASSETS = {}
    _REGEX = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decorate_item(item_name: str) -> str:
    """
    Returns the item name in Title Case with a contextual emoji prefix.

    Matching strategy (highest priority first):
    1. Full-string regex search — handles exact names, plurals (milk/milks),
       and compound phrases where the keyword appears anywhere
       (e.g. "Green Apple" → finds "apple" → 🍎).
    2. Word-level fuzzy fallback — splits the name into individual words
       and tries each one independently.  Catches constructs like
       "Granny Smith Apple" or "Organic Whole Milk" where the base keyword
       is not at a clean word boundary in the full string (rare, but safe).
    3. Default emoji 📦 if no match found.
    """
    if not item_name:
        return ""

    clean_name = item_name.strip().title()
    lower = item_name.lower()

    if _REGEX is None:
        return f"📦 {clean_name}"

    # --- Strategy 1: full-string search ---
    match = _REGEX.search(lower)
    if match:
        emoji = _ASSETS.get(match.group(1).lower(), "📦")
        return f"{emoji} {clean_name}"

    # --- Strategy 2: word-level fuzzy fallback ---
    for word in lower.split():
        word_match = _REGEX.fullmatch(word) or _REGEX.search(f" {word} ")
        if word_match:
            emoji = _ASSETS.get(word_match.group(1).lower(), "📦")
            return f"{emoji} {clean_name}"

    return f"📦 {clean_name}"
