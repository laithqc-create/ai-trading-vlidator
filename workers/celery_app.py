"""
Celery application for async task processing.

Why async? Telegram has a 30-second timeout for webhook responses.
OpenTrade.ai LangGraph pipeline can take 60-120 seconds with a local LLM.
Solution: Acknowledge the webhook immediately, process in background, push result to user.
"""
import asyncio
from celery import Celery
from loguru import logger
from config.settings import settings

# Create Celery app
celery_app = Celery(
    "trade_validator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                # Ack only after completion
    worker_prefetch_multiplier=1,       # One task at a time per worker
    task_soft_time_limit=180,           # 3 min soft limit
    task_time_limit=300,                # 5 min hard limit
    result_expires=3600,                # Keep results for 1 hour
)


def run_async(coro):
    """Helper to run async code in a Celery (sync) task."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
