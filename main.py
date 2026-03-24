from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(override=True)

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api.webhook import router as webhook_router
from api.admin_router import router as admin_router
from services.database import init_db, health_check
from services.scheduler_service import generate_daily_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Starts and cleans up background services."""
    logger.info("Starting up PantryPilot services...")
    init_db()
    if not health_check():
        logger.critical("Database health check failed on startup — aborting.")
        raise RuntimeError("Database unavailable")
    scheduler.add_job(generate_daily_summary, "cron", hour=16, minute=0)
    scheduler.start()
    yield
    logger.info("Shutting down PantryPilot services...")
    scheduler.shutdown()


app = FastAPI(
    title="PantryPilot",
    description="WhatsApp-based household pantry management",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "message": "PantryPilot v2.0 is running"}


app.include_router(webhook_router)
app.include_router(admin_router, prefix="/admin")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
