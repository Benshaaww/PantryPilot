import logging
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

VISION_PROMPT = """You are an expert OCR and grocery analyst. Analyze this image. Extract a list of food items. Return ONLY a comma-separated list of items (e.g., 'Milk, Eggs, Bread'). If it is a receipt, extract the items, not the prices. If you see no food/groceries, return 'NONE'."""

async def analyze_image(base64_string: str) -> str:
    """
    Passes a base64 encoded image to the LangChain GPT-4o Vision model.
    Strictly constrained to output a comma-separated list or 'NONE'.
    """
    logger.info("Triggering LangChain Vision OCR processing...")
    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
        
        messages = [
            SystemMessage(content=VISION_PROMPT),
            HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_string}"
                        }
                    }
                ]
            )
        ]
        
        # Protective timeout matching recipe agent constraints
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=15.0
        )
        
        return response.content.strip()
        
    except asyncio.TimeoutError:
        logger.error("LangChain Vision Agent timed out after 15 seconds.")
        return "NONE"
    except Exception as e:
        logger.error(f"Error executing Vision Agent OCR: {e}")
        return "NONE"
