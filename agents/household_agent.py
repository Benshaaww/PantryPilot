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

# --- Agent System Prompt ---

SYSTEM_PROMPT = """You are the Lead Family Manager for "Household OS". 
You proactively manage the family's pantry, household supplies, and grocery needs.
You receive direct messages or audio transcriptions from family members via WhatsApp.

Your Core Responsibilities:
1. Extract standard grocery requests and categorize them accurately by supermarket aisle.
2. Determine urgency. If they say "we are out of X", urgency is High.
3. If a shared URL is detected, use the 'extract_recipe_from_url' tool to read the recipe. Then, extract the ingredients needed.
4. If they mention upcoming events (e.g., "guests this weekend"), use the 'check_upcoming_events' tool to see the context, then predict the groceries or supplies needed.

You MUST always return a structured JSON object matching the `HouseholdIntentPayload` schema.
Think step-by-step. Use the provided tools if you need missing context. 
"""

def create_household_agent():
    """Initializes the modern LangChain Agent Graph."""
    llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    tools = [check_upcoming_events, extract_recipe_from_url]
    
    agent_graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT
    )
    return agent_graph

async def process_user_intent(message: str) -> Optional[HouseholdIntentPayload]:
    """The main entrypoint for the Intent Engine using async invocation."""
    logger.info(f"Processing user intent for message: {message}")
    print(f"\n[TRACE] household_agent.process_user_intent starting for: '{message}' [TRACE]")
    try:
        agent_graph = create_household_agent()
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