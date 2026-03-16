from dotenv import load_dotenv
load_dotenv(override=True)

import logging
from fastapi import FastAPI
from api.webhook import router as webhook_router
from api.admin_router import router as admin_router
from services.scheduler_service import generate_daily_summary
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Configure basic logging for the application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

scheduler = AsyncIOScheduler()

# Define lifespan manager for background services
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts and cleans up background services."""
    logger.info("Starting up Household OS services...")
    # Production mode: run daily at 4:00 PM
    scheduler.add_job(generate_daily_summary, 'cron', hour=16, minute=0)
    scheduler.start()
    yield
    logger.info("Shutting down Household OS services...")
    scheduler.shutdown()

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Household OS",
    description="WhatsApp-based family management SaaS",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Health check endpoint to verify server is running."""
    return {"status": "ok", "message": "Household OS is running"}

if __name__ == "__main__":
    import uvicorn
    # Run the server locally using Uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
