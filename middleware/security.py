from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque

# ---------------------------------------------------------------------------
# Access Logger — writes every inbound webhook event to logs/access.log
# ---------------------------------------------------------------------------

_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "access.log")

_access_logger = logging.getLogger("pantrypilot.access")
_access_logger.setLevel(logging.INFO)
_access_logger.propagate = False  # Keep access log separate from root logger

_file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
)
_access_logger.addHandler(_file_handler)


def log_request(message_id: str, phone_number: str, timestamp: str) -> None:
    """Writes one access-log line per inbound webhook message."""
    _access_logger.info(
        "message_id=%s phone=%s ts=%s", message_id, phone_number, timestamp
    )


# ---------------------------------------------------------------------------
# Rate Limiter — sliding-window, 10 messages per 60 seconds per phone_number
# ---------------------------------------------------------------------------

RATE_LIMIT_MAX: int = 10
RATE_LIMIT_WINDOW: int = 60  # seconds

_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_rate_logger = logging.getLogger(__name__)


def check_rate_limit(phone_number: str) -> bool:
    """
    Returns True if the request is within the allowed rate.
    Returns False (and logs a warning) when the limit is exceeded.

    Uses a sliding-window algorithm: only timestamps within the last
    RATE_LIMIT_WINDOW seconds are counted.
    """
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW
    bucket = _rate_buckets[phone_number]

    # Evict timestamps outside the current window
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX:
        _rate_logger.warning(
            "Rate limit exceeded for %s — %d messages in %ds window",
            phone_number,
            len(bucket),
            RATE_LIMIT_WINDOW,
        )
        return False

    bucket.append(now)
    return True
