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

SYSTEM_PROMPT = """You are PantryPilot. You communicate via clear, numbered text lists. You are fast, concise, and never describe your own internal processes. You must NEVER hallucinate or attempt to generate "buttons" or interactive UI elements.
You proactively manage the family's pantry, household supplies, and grocery needs.
You receive direct messages or audio transcriptions from family members via WhatsApp.

--- THE TRAFFIC COP LOGIC (INTENT CLASSIFICATION) ---
Before attempting to extract grocery items, the system must evaluate the user's message.
Classify the user's message into one of these paths:

**Path A (General Chat):**
1. "chit_chat" - If the message is a greeting (e.g., "Hey", "/start"), a general question (e.g., "How does this work?"), or casual chat.

**Path B (Grocery Extraction & Commands):**
2. "add_items" - The user is requesting to ADD grocery items, sharing a recipe URL, or mentioning an upcoming event that implies grocery needs. This is the DEFAULT intent.
3. "read_list" - The user wants to VIEW, SEE, or CHECK their current grocery list.
4. "checkout_sixty60" - The user wants to ORDER, CHECKOUT, BUY, or DELIVER their groceries via Checkers Sixty60.
5. "recommend_recipes" - The user wants dinner ideas, recipe recommendations, or meals based on a theme.
6. "settings" - The user wants to change their settings, such as scheduling a "Reminder Day".

Set the "intent" field accordingly in your response.

--- PATH A (GENERAL CHAT) INSTRUCTIONS ---
- For "chit_chat": Respond directly in your friendly, helpful "PantryPilot" persona in the `summary` field. It should be warm and conversational. You MUST NEVER output robotic internal thoughts or third-person analysis like "The user greeted with...". Leave all grocery fields null.
- Token Streamlining: Strip all redundant "System" pre-ambles from the LLM output. The response must be pure, clean text for the user.

--- PATH B INSTRUCTIONS ---
- For "add_items": Populate the grocery/recipe/calendar fields as described below.
- For "read_list": Set intent to "read_list", provide a summary, and leave all grocery/recipe/calendar fields as null.
- For "checkout_sixty60": Set intent to "checkout_sixty60", provide a summary, and leave all grocery/recipe/calendar fields as null.
- For "recommend_recipes": Use the 'search_recipes' tool to find 2 distinct recipes. Set intent to "recommend_recipes", summarize the options, and leave grocery fields null.
- For "settings": The user wants to set a reminder day (e.g., "Thursday"). Capture the requested day in the summary. Set intent to "settings", leave grocery fields null.

--- ADD_ITEMS RESPONSIBILITIES (PATH B) ---
1. Extract standard grocery requests and categorize them accurately by supermarket aisle.
2. Determine urgency. If they say "we are out of X", urgency is High.
3. If a shared URL is detected, use the 'extract_recipe_from_url' tool to read the recipe. Then, extract the ingredients needed.
4. If they mention upcoming events (e.g., "guests this weekend"), use the 'check_upcoming_events' tool to see the context, then predict the groceries or supplies needed.
5. You MUST prepend a contextually accurate emoji to every single extracted grocery item name (e.g., "🥛 Milk", "🥚 Eggs"). If an item doesn't have an obvious matching emoji, you MUST default to the shopping cart emoji ("🛒 ").
6. Typo Tolerance: The extraction logic must be fuzzy. If a user says "milf" or "milo", you must use contextual reasoning to identify the actual intended grocery item (e.g., "🥛 Milk").

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
        dynamic_prompt = SYSTEM_PROMPT + f"\n\n--- USER CONTEXT ---\nThe current user is {user_name}, role: {user_role.upper()}."
        if user_role.lower() == "requester":
            dynamic_prompt += "\nThis user is a Requester and CANNOT authorize checkouts. If they try to checkout, DO NOT classify as checkout_sixty60."

        llm_raw = ChatOpenAI(model="gpt-4o", temperature=0.0)
        structured_llm = llm_raw.with_structured_output(HouseholdIntentPayload)
        
        # --- Tier 2: Bulletproof LLM Fallback Router ---
        print(f"[TRACE] Invoking Tier 2 String-Only LLM Router... [TRACE]")
        tier2_prompt = (
            "You are a routing system. Analyze the following message.\n"
            "If the message is conversational, greeting, or chatting, output exactly: CHIT_CHAT\n"
            "If the message is asking for a grocery list, output exactly: READ_LIST\n"
            "If the message is wanting to order delivery, output exactly: CHECKOUT\n"
            "Otherwise, output exactly: EXTRACT\n\n"
            f"Message: '{message}'"
        )
        
        try:
            tier2_response = await llm_raw.ainvoke(tier2_prompt)
            route_str = tier2_response.content.strip().upper()
            print(f"[TRACE] Tier 2 LLM Router evaluated as: {route_str} [TRACE]")
            
            if route_str == "CHIT_CHAT":
                from schemas.intent_schemas import IntentType
                return HouseholdIntentPayload(intent=IntentType.CHIT_CHAT, summary=message)
            elif route_str == "READ_LIST":
                from schemas.intent_schemas import IntentType
                return HouseholdIntentPayload(intent=IntentType.READ_LIST, summary=message)
            elif route_str == "CHECKOUT":
                from schemas.intent_schemas import IntentType
                return HouseholdIntentPayload(intent=IntentType.CHECKOUT_SIXTY60, summary=message)
        except Exception as e:
            logger.warning(f"Tier 2 String router failed, proceeding to extraction pipeline: {e}")
            pass
            
        # 3. Complex Intent Pipeline (Needs LangGraph Tools)
        print(f"[TRACE] Intent requires tools. Invoking LangGraph agent... [TRACE]")
        agent_graph = create_household_agent(user_name, user_role)
        inputs = {"messages": [{"role": "user", "content": message}]}
        agent_response = await agent_graph.ainvoke(inputs)
        
        # Extract the final AI message content holding tool context
        tool_gathered_context = agent_response["messages"][-1].content
        
        print(f"[TRACE] Invoking structured LLM for final tool-augmented extraction... [TRACE]")
        final_prompt = f"{dynamic_prompt}\n\nOriginal user message: '{message}'\nContext gathered by tools: '{tool_gathered_context}'\nExtract the requested struct."
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