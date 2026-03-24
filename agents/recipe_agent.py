import asyncio
import logging

from httpx import ConnectTimeout, ReadTimeout
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

_CHEF_PROMPT = """You are PantryPilot's culinary engine. The user has the following ingredients:
{inventory_list}

Generate one concise recipe using only some or all of these ingredients.
Do not ask follow-up questions. Format with bold headers and bullet points.
Keep it under 800 characters for WhatsApp readability. Do not hallucinate buttons."""


async def generate_recipe(inventory_list: list[str]) -> str:
    """
    Calls GPT-4o to generate a recipe from the household's current inventory.
    Returns a plain string; never raises — timeouts and errors return a
    user-friendly fallback message.
    """
    if not inventory_list:
        return "I can't cook without ingredients! Add some items to your pantry first."

    formatted = ", ".join(inventory_list)
    logger.info("Generating recipe for: %s", formatted)

    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
        chain = ChatPromptTemplate.from_messages([("system", _CHEF_PROMPT)]) | llm
        response = await asyncio.wait_for(
            chain.ainvoke({"inventory_list": formatted}),
            timeout=15.0,
        )
        return str(response.content).strip()

    except (asyncio.TimeoutError, ReadTimeout, ConnectTimeout):
        logger.error("Recipe generation timed out.")
        return "👨‍🍳 I'm moving a little slow in the kitchen today! (Timeout). Please try again."
    except Exception as exc:
        logger.error("Error generating recipe: %s", exc)
        return "👨‍🍳 Spilled something in the kitchen! An error occurred generating your recipe."
