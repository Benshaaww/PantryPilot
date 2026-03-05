# Household OS

A highly scalable, Domain-Driven WhatsApp-based family management SaaS. 
Household OS acts as a proactive family manager, intercepting natural language requests via WhatsApp, deciphering intent using LangChain/ReAct, managing inventory in MongoDB, and physically executing approved orders via Playwright headless browser automation.

## Tech Stack Overview
- **Routing/API**: Python 3.11+, FastAPI, Uvicorn
- **AI Integration**: `openai` SDK (gpt-4o, whisper), `langchain` (ReAct Tool-Calling Agents)
- **Data & Validation**: `motor` (Async MongoDB), `pydantic` (Strict Schema typing)
- **Automation**: `playwright` (Headless browser fulfillment), `apscheduler` (Background tasks)

---

## MVP Local Testing Runbook

Follow these steps to successfully run the End-to-End local testing environment.

### 1. Environment Setup
1. Copy the environment template to activate it:
   ```bash
   cp .env.example .env
   ```
2. Populate `.env` with your actual keys (MongoDB URI, OpenAI API Key).

### 2. Dependency Installation
Create a virtual environment (optional but recommended) and install exactly what the system needs:
```bash
pip install -r requirements.txt
```

### 3. Playwright Initialization
Because Phase 4 utilizes headless Chromium, you must instruct Playwright to download the required browser binaries locally:
```bash
playwright install chromium
```

### 4. Boot the FastAPI Server
Start the core application engine. This will spin up the asynchronous webhook routers and the APScheduler background tasks.
```bash
python -m uvicorn main:app --reload
```
You should see: `Household OS services started...` and `Uvicorn running on http://127.0.0.1:8000`

### 5. Execute the Simulator (End-to-End Test)
In a *separate* terminal window, simulate an incoming WhatsApp message from a family member. 
This script bypasses Meta's API and directly POSTs the complex JSON structure to your local `/api/webhook` route.

```bash
python tests/simulate_whatsapp.py
```

**What to watch for in the Server Terminal:**
1. You will see `main.py` receive the webhook.
2. The `household_agent` will boot up and process the natural language.
3. You will see the LangChain agent extract the `GroceryItem` Pydantic models.
4. You will see the `grocery_repo` execute async motor updates, logging that it is inserting or `$inc`rementing the exact items in MongoDB with status `pending`.

### 6. Verify Admin Orchestration
You can trigger the Phase 4 Playwright checkout sequence by simulating the Admin's "Approve All" command:

```bash
curl -X POST http://localhost:8000/api/admin/command \
     -H "Content-Type: application/json" \
     -d '{"command": "Approve All"}'
```

Watch the server logs as it flips the MongoDB items to `ordered` and initiates the headless `playwright_service`.
