from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_VISION_PROMPT = """You are a high-precision Grocery Scanner. Analyze the image.

1. If it's a receipt: extract the food/grocery item names only — not prices, quantities, or store names.
2. If it's a single product, can, or box: identify the specific brand and item name (e.g., 'Coca-Cola', 'Heinz Baked Beans', 'Kellogg's Corn Flakes').

Return ONLY a comma-separated list of the items found (e.g., 'Milk, Eggs, Heinz Baked Beans').
If you are unsure, provide your best guess of the item name.
If there are genuinely no food or grocery items, return 'NONE'.
No conversational filler."""


async def analyze_image(base64_string: str) -> str:
    """
    Passes a base64-encoded image to GPT-4o Vision with high-detail processing.
    Returns a comma-separated list of grocery items, or 'NONE'.
    Never raises — returns 'NONE' on timeout or error.
    """
    logger.info("Starting Vision OCR analysis (high-detail mode).")
    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
        messages = [
            SystemMessage(content=_VISION_PROMPT),
            HumanMessage(content=[{
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_string}",
                    "detail": "high",  # Max resolution tile processing for label recognition
                },
            }]),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=20.0)
        return str(response.content).strip()

    except asyncio.TimeoutError:
        logger.error("Vision agent timed out after 20 seconds.")
        return "NONE"
    except Exception as exc:
        logger.error("Vision agent error: %s", exc)
        return "NONE"
