#!/usr/bin/env python3
"""
Setup script — run once after deployment:
  1. Sets the Telegram webhook URL
  2. Creates and seeds the system RAGFlow knowledge base
  3. Tests all API connections

Usage:
    python scripts/setup.py
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from loguru import logger


async def set_telegram_webhook():
    """Register the webhook URL with Telegram."""
    from telegram import Bot
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    me = await bot.get_me()
    logger.info(f"Bot: @{me.username} ({me.first_name})")

    if not settings.TELEGRAM_WEBHOOK_URL:
        logger.warning("TELEGRAM_WEBHOOK_URL not set. Skipping webhook registration.")
        return

    result = await bot.set_webhook(
        url=settings.TELEGRAM_WEBHOOK_URL,
        drop_pending_updates=True,
    )
    logger.info(f"Webhook set: {result} → {settings.TELEGRAM_WEBHOOK_URL}")

    info = await bot.get_webhook_info()
    logger.info(f"Webhook info: {info}")


async def seed_ragflow_system_kb():
    """Create and populate the system RAGFlow knowledge base."""
    from ragflow.service import RAGFlowService

    if not settings.RAGFLOW_API_KEY:
        logger.warning("RAGFLOW_API_KEY not set. Skipping RAGFlow setup.")
        return

    ragflow = RAGFlowService(settings)
    logger.info("Setting up RAGFlow system knowledge base...")

    # Check if system KB already exists
    existing_id = await ragflow.get_dataset_id_by_name("system_trading_rules")
    if existing_id:
        logger.info(f"System KB already exists: {existing_id}")
        return

    # Create system KB
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.RAGFLOW_BASE_URL}/api/v1/dataset",
            headers={
                "Authorization": f"Bearer {settings.RAGFLOW_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "name": "system_trading_rules",
                "description": "System-level trading rules and patterns",
                "permission": "me",
            },
        )
        data = resp.json()
        dataset_id = data.get("data", {}).get("id")

    if dataset_id:
        logger.info(f"Created system KB: {dataset_id}")
        await ragflow.seed_system_knowledge_base(dataset_id)
        logger.success("System knowledge base seeded with 13 base trading rules.")
    else:
        logger.error(f"Failed to create system KB: {data}")


async def test_connections():
    """Test all API connections."""
    import httpx

    logger.info("\n=== Testing Connections ===")

    # Test Ollama
    if settings.LLM_PROVIDER == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                models = resp.json().get("models", [])
                logger.info(f"✅ Ollama: {len(models)} models available")
                for m in models[:3]:
                    logger.info(f"   - {m.get('name')}")
        except Exception as e:
            logger.warning(f"❌ Ollama not reachable: {e}")
            logger.warning("   Run: ollama serve && ollama pull llama3")

    # Test RAGFlow
    if settings.RAGFLOW_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{settings.RAGFLOW_BASE_URL}/api/v1/dataset",
                    headers={"Authorization": f"Bearer {settings.RAGFLOW_API_KEY}"},
                )
                logger.info(f"✅ RAGFlow: Connected ({resp.status_code})")
        except Exception as e:
            logger.warning(f"❌ RAGFlow not reachable: {e}")
            logger.warning("   Run: docker compose --profile full up ragflow")

    # Test Polygon.io
    if settings.POLYGON_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"https://api.polygon.io/v2/aggs/ticker/AAPL/prev",
                    params={"apiKey": settings.POLYGON_API_KEY},
                )
                logger.info(f"✅ Polygon.io: Connected ({resp.status_code})")
        except Exception as e:
            logger.warning(f"❌ Polygon.io not reachable: {e}")

    # Test Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        logger.info("✅ Redis: Connected")
    except Exception as e:
        logger.warning(f"❌ Redis not reachable: {e}")

    # Test PostgreSQL
    try:
        from db.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ PostgreSQL: Connected")
    except Exception as e:
        logger.warning(f"❌ PostgreSQL not reachable: {e}")


async def main():
    logger.info("=== AI Trade Validator Setup ===\n")
    await test_connections()
    await set_telegram_webhook()
    await seed_ragflow_system_kb()
    logger.info("\n✅ Setup complete! Start the app with: docker compose up -d")


if __name__ == "__main__":
    asyncio.run(main())
