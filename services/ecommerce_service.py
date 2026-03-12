import logging
import random

logger = logging.getLogger(__name__)


async def push_to_sixty60(items: list[dict]) -> dict:
    """
    Mock: simulates staging items in a Checkers Sixty60 cart.
    Assigns a random per-item price in ZAR and returns the summary.

    Returns:
        {"item_count": N, "estimated_total_zar": float, "items": list}
    """
    if not items:
        return {"item_count": 0, "estimated_total_zar": 0.0, "items": []}

    total = 0.0
    detailed_items = []
    
    for item in items:
        price = round(random.uniform(15.0, 120.0), 2)
        total += price
        
        detailed_items.append({
            "name": item.get('item_name', 'Unknown'),
            "requested_by": item.get('requested_by', 'System'),
            "price": price
        })
        
        logger.info(
            f"Sixty60 cart: {item.get('item_name', 'Unknown')} -> R{price:.2f} (Requested by: {item.get('requested_by', 'System')})"
        )

    total = round(total, 2)
    logger.info(
        f"Checkers Sixty60 mock order staged: {len(items)} items, R{total:.2f}"
    )

    return {
        "item_count": len(items),
        "estimated_total_zar": total,
        "items": detailed_items
    }
