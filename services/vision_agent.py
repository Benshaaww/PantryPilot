import asyncio
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_VISION_PROMPT = (
    "You are an expert OCR and grocery analyst. Analyze this image. "
    "Extract a list of food items. Return ONLY a comma-separated list "
    "(e.g. 'Milk, Eggs, Bread'). If it is a receipt, extract item names "
    "only — not prices. If you see no food or groceries, return 'NONE'."
)


async def analyze_image(base64_string: str) -> str:
    """
    Passes a base64-encoded image to GPT-4o Vision.
    Returns a comma-separated list of grocery items, or 'NONE'.
    Never raises — returns 'NONE' on timeout or error.
    """
    logger.info("Starting Vision OCR analysis.")
    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
        messages = [
            SystemMessage(content=_VISION_PROMPT),
            HumanMessage(content=[{
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_string}"},
            }]),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=15.0)
        return str(response.content).strip()

    except asyncio.TimeoutError:
        logger.error("Vision agent timed out after 15 seconds.")
        return "NONE"
    except Exception as exc:
        logger.error("Vision agent error: %s", exc)
        return "NONE"
