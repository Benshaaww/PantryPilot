import logging
import sys
import os
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

# Allow direct execution of this file (e.g. via VS Code "Run" button) by adding the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the strict schemas and integration services
from schemas.intent_schemas import HouseholdIntentPayload
from services import calendar_service, recipe_scraper

logger = logging.getLogger(__name__)

# --- Tool Definitions ---

@tool
def check_upcoming_events(days: int = 7) -> str:
    """Checks the family Google Calendar for upcoming events."""
    events = calendar_service.fetch_upcoming_events(days)
    if not events:
        return "No upcoming events found."
    return str(events)

@tool
def extract_recipe_from_url(url: str) -> str:
    """Downloads and extracts the text content from a recipe URL."""
    raw_text = recipe_scraper.scrape_recipe_text(url)
    return raw_text

@tool
def search_recipes(theme: str) -> str:
    """Searches for 2 distinct recipes based on the current pantry or a theme. Returns recipes scored by Difficulty and Rating."""
    # Mock search tool returning highly formatted options
    return (
        f"1. [Spicy {theme.capitalize()} Bowl] | 🏆 Rating: 4.8/5 | 👨‍🍳 Difficulty: Easy\n"
        f"2. [Classic {theme.capitalize()} Bake] | 🏆 Rating: 4.5/5 | 👨‍🍳 Difficulty: Medium"
    )

# --- Agent System Prompt ---

SYSTEM_PROMPT = """You are the Lead Family Manager for "Household OS" (PantryPilot). 
You proactively manage the family's pantry, household supplies, and grocery needs.
You receive direct messages or audio transcriptions from family members via WhatsApp.

--- INTENT CLASSIFICATION ---
Before anything else, classify the user's message into one of three intents:

1. "add_items" - The user is requesting to ADD grocery items, sharing a recipe URL, or 
   mentioning an upcoming event that implies grocery needs. This is the DEFAULT intent.
2. "read_list" - The user wants to VIEW, SEE, or CHECK their current grocery list.
   Example phrases: "show me my list", "what do we need?", "what's on the list?"
3. "checkout_sixty60" - The user wants to ORDER, CHECKOUT, BUY, or DELIVER their groceries 
   via Checkers Sixty60. Example phrases: "order everything", "checkout on sixty60", 
   "deliver my groceries", "let's buy these".
4. "recommend_recipes" - The user wants dinner ideas, recipe recommendations, or meals based on a theme.
5. "settings" - The user wants to change their settings, such as scheduling a "Reminder Day".

Set the "intent" field accordingly in your response.

--- RULES PER INTENT ---
- For "add_items": Populate the grocery/recipe/calendar fields as described below.
- For "read_list": Set intent to "read_list", provide a summary, and leave all 
  grocery/recipe/calendar fields as null (the system will fetch the list from the database).
- For "checkout_sixty60": Set intent to "checkout_sixty60", provide a summary, and leave all 
  grocery/recipe/calendar fields as null (the system will handle the e-commerce flow).
- For "recommend_recipes": Use the 'search_recipes' tool to find 2 distinct recipes. Set intent to "recommend_recipes", summarize the options, and leave grocery fields null.
- For "settings": The user wants to set a reminder day (e.g., "Thursday"). Capture the requested day in the summary. Set intent to "settings", leave grocery fields null.

--- ADD_ITEMS RESPONSIBILITIES ---
1. Extract standard grocery requests and categorize them accurately by supermarket aisle.
2. Determine urgency. If they say "we are out of X", urgency is High.
3. If a shared URL is detected, use the 'extract_recipe_from_url' tool to read the recipe. Then, extract the ingredients needed.
4. If they mention upcoming events (e.g., "guests this weekend"), use the 'check_upcoming_events' tool to see the context, then predict the groceries or supplies needed.
5. You MUST prepend a contextually accurate emoji to every single extracted grocery item name (e.g., "🥛 Milk", "🥚 Eggs"). If an item doesn't have an obvious matching emoji, you MUST default to the shopping cart emoji ("🛒 ").

You MUST always return a structured JSON object matching the `HouseholdIntentPayload` schema.
Think step-by-step. Use the provided tools if you need missing context. 
"""

def create_household_agent(user_name: str, user_role: str):
    """Initializes the modern LangChain Agent Graph."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    tools = [check_upcoming_events, extract_recipe_from_url, search_recipes]
    
    dynamic_prompt = SYSTEM_PROMPT + f"\n\n--- USER CONTEXT ---\nThe current user is {user_name}, role: {user_role.upper()}."
    if user_role.lower() == "requester":
        dynamic_prompt += "\nThis user is a Requester and CANNOT authorize checkouts. If they try to checkout, DO NOT classify as checkout_sixty60 (fallback to chat or a polite decline, or let the router catch it)."
        
    agent_graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=dynamic_prompt
    )
    return agent_graph

async def process_user_intent(message: str, user_name: str = "Unknown", user_role: str = "requester") -> Optional[HouseholdIntentPayload]:
    """The main entrypoint for the Intent Engine using async invocation."""
    logger.info(f"Processing user intent for message: {message} (User: {user_name}, Role: {user_role})")
    print(f"\n[TRACE] household_agent.process_user_intent starting for: '{message}' [TRACE]")
    try:
        agent_graph = create_household_agent(user_name, user_role)
        structured_llm = ChatOpenAI(model="gpt-4o", temperature=0.0).with_structured_output(HouseholdIntentPayload)
        
        # Async invocation with LangGraph message state
        print(f"[TRACE] Invoking LangGraph agent... [TRACE]")
        inputs = {"messages": [{"role": "user", "content": message}]}
        agent_response = await agent_graph.ainvoke(inputs)
        print(f"[TRACE] LangGraph agent responded! [TRACE]")
        
        # Extract the final AI message content holding tool context
        tool_gathered_context = agent_response["messages"][-1].content
        
        print(f"[TRACE] Invoking structured LLM for final extraction... [TRACE]")
        final_prompt = f"Original user message: '{message}'\nContext gathered by tools: '{tool_gathered_context}'\nExtract the requested struct."
        result = await structured_llm.ainvoke(final_prompt)
        print(f"[TRACE] Structured LLM extracted result! [TRACE]")
        
        if isinstance(result, HouseholdIntentPayload):
            return result
        else:
            logger.error("Failed to parse LLM output into HouseholdIntentPayload.")
            return None
            
    except Exception as e:
        logger.error(f"Error in Intent Engine: {e}")
        print(f"\n[TRACE FATAL ERROR] Exception in process_user_intent: {e} [TRACE FATAL ERROR]\n")
        import traceback
        traceback.print_exc()
        return None