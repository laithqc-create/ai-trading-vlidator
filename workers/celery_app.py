"""Celery application factory."""
import asyncio
from celery import Celery
from config.settings import settings

celery_app = Celery(
    "trade_validator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.tasks", "workers.scheduler"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


def run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
