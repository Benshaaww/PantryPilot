import asyncio
import sys
import os
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force load the environment variables before importing anything else
load_dotenv(override=True)

from services.playwright_service import automate_grocery_cart

if __name__ == "__main__":
    print("Executing Playwright MongoDB Integration Test...")
    asyncio.run(automate_grocery_cart())
