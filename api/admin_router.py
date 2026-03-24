from __future__ import annotations

import logging

from fastapi import APIRouter

from services.database import health_check, _get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def admin_health() -> dict[str, str]:
    """Returns the database health status."""
    ok = health_check()
    return {"status": "ok" if ok else "degraded", "db": "sqlite"}


@router.get("/households")
async def list_households() -> dict:
    """Returns all households and their current pantry item counts."""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT h.id, h.household_name, COUNT(p.id) AS item_count "
                "FROM households h "
                "LEFT JOIN pantry_items p ON p.household_id = h.id "
                "GROUP BY h.id"
            )
            rows = cursor.fetchall()
        return {
            "households": [
                {"id": r[0], "name": r[1], "pantry_items": r[2]} for r in rows
            ]
        }
    except Exception as exc:
        logger.error("Error listing households: %s", exc)
        return {"households": [], "error": str(exc)}
