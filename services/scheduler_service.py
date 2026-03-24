import logging
import os

from services import database
from services.whatsapp_client import send_whatsapp_message

logger = logging.getLogger(__name__)


async def generate_daily_summary() -> str:
    """
    Scheduled job (runs daily at 16:00).
    Queries every household's pantry via SQLite and sends a summary
    to the configured admin WhatsApp number.
    """
    admin_number = os.getenv("WHATSAPP_ADMIN_NUMBER", "")
    if not admin_number:
        logger.warning("WHATSAPP_ADMIN_NUMBER not set — skipping daily summary.")
        return "Skipped: no admin number configured."

    try:
        with database._get_db() as conn:
            cursor = conn.execute(
                "SELECT h.household_name, s.item_name "
                "FROM shopping_list s "
                "JOIN households h ON h.id = s.household_id "
                "ORDER BY h.id, s.added_at"
            )
            rows = cursor.fetchall()

        if not rows:
            report = "🛒 Daily Grocery Report: All lists are empty."
        else:
            lines: list[str] = ["🛒 Daily Grocery Report:"]
            current_hh: str = ""
            for hh_name, item_name in rows:
                if hh_name != current_hh:
                    lines.append(f"\n*{hh_name}*")
                    current_hh = hh_name
                lines.append(f"  - {item_name}")
            report = "\n".join(lines)

        logger.info("Daily summary generated (%d items).", len(rows))

        await send_whatsapp_message({
            "messaging_product": "whatsapp",
            "to": admin_number,
            "type": "text",
            "text": {"body": report},
        })

        return report

    except Exception as exc:
        logger.error("Failed to generate daily summary: %s", exc)
        return "Error generating daily summary."
