import logging
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from httpx import ReadTimeout, ConnectTimeout

logger = logging.getLogger(__name__)

# Strict System Prompt confining the LLM to text-in, text-out purely
CHEF_PROMPT = """You are PantryPilot's culinary engine. The user has the following ingredients in their pantry: 
{inventory_list}

Generate a single, highly concise recipe using ONLY some or all of these ingredients. 
Do not ask follow-up questions. Format with bold headers and bullet points. 
Keep it under 800 characters for WhatsApp readability. Do not hallucinate buttons."""

async def generate_recipe(inventory_list: list[str]) -> str:
    """
    Calls the LLM safely to generate a strictly formatted recipe using current ingredients.
    Returns a clean string. Handles LLM timeouts cleanly to prevent webhook crashes.
    """
    if not inventory_list:
        return "I can't cook without ingredients! Add some items to your pantry first."
    
    formatted_inventory = ", ".join(inventory_list)
    logger.info(f"Generating recipe for items: {formatted_inventory}")
    
    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
        prompt = ChatPromptTemplate.from_messages([
            ("system", CHEF_PROMPT)
        ])
        
        chain = prompt | llm
        
        # Protect gateway from LangChain hanging infinitely
        response = await asyncio.wait_for(
            chain.ainvoke({"inventory_list": formatted_inventory}),
            timeout=15.0
        )
        
        return response.content.strip()
        
    except (asyncio.TimeoutError, ReadTimeout, ConnectTimeout):
        logger.error("LangChain recipe generation timed out.")
        return "👨‍🍳 I'm moving a little slow in the kitchen today! (Timeout). Please try again later."
    except Exception as e:
        logger.error(f"Error generating recipe via LangChain: {e}")
        return "👨‍🍳 Spilled something in the kitchen! An error occurred generating your recipe."
