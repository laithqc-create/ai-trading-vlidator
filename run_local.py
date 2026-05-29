"""
run_local.py
============
Single-command local development runner.

Usage:
    python run_local.py

What it does:
    1. Loads local_dev.env (SQLite, your Telegram + DeepSeek keys)
    2. Creates all SQLite tables automatically (no alembic needed)
    3. Patches Celery .delay() → asyncio background tasks
    4. Starts the Telegram bot in POLLING mode (no public URL needed)
    5. Starts uvicorn on http://localhost:8000

After starting:
    - Mini app:  http://localhost:8000/app
    - API docs:  http://localhost:8000/docs
    - Telegram:  open your bot, send /start
"""

import asyncio
import os
import sys
from pathlib import Path

# ── 1. Load local_dev.env BEFORE importing anything else ──────────────────────
env_file = Path(__file__).parent / "local_dev.env"
if not env_file.exists():
    print("ERROR: local_dev.env not found.")
    print("Copy local_dev.env and fill in TELEGRAM_BOT_TOKEN and DEEPSEEK_API_KEY")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(env_file, override=True)

# Check required keys
missing = []
if not os.getenv("TELEGRAM_BOT_TOKEN") or "PASTE" in os.getenv("TELEGRAM_BOT_TOKEN", ""):
    missing.append("TELEGRAM_BOT_TOKEN")
if not os.getenv("DEEPSEEK_API_KEY") or "PASTE" in os.getenv("DEEPSEEK_API_KEY", ""):
    missing.append("DEEPSEEK_API_KEY")

if missing:
    print(f"\nERROR: Fill in these values in local_dev.env first:")
    for m in missing:
        print(f"  {m}=your_value_here")
    sys.exit(1)

print("✓ Environment loaded")

# ── 2. Patch Celery tasks → inline async background tasks ─────────────────────
# This lets main.py call task.delay(...) without Redis being installed.
# The task runs as an asyncio.create_task() in the same event loop.

class _InlineTask:
    """Wraps an async function so .delay(**kwargs) runs it as a background task."""
    def __init__(self, fn, name=""):
        self._fn = fn
        self._name = name

    def delay(self, **kwargs):
        async def _run():
            try:
                await self._fn(**kwargs)
            except Exception as e:
                print(f"[task:{self._name}] error: {e}")
        # Schedule on the running event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_run())
            else:
                loop.run_until_complete(_run())
        except Exception as e:
            print(f"[task:{self._name}] schedule error: {e}")

# Import the real async implementations, wrap them
from workers.tasks import (
    _validate_indicator_async,
    _analyze_ea_async,
    _send_telegram_message,
)

_validate_task = _InlineTask(_validate_indicator_async, "validate_indicator")
_analyze_task  = _InlineTask(_analyze_ea_async, "analyze_ea")

# Patch into the modules that import them
import workers.tasks as _wt
import main as _main_module

_wt.validate_indicator_task   = _validate_task
_wt.analyze_ea_task           = _analyze_task
_main_module.validate_indicator_task = _validate_task
_main_module.analyze_ea_task  = _analyze_task

print("✓ Celery tasks patched → inline async")

# ── 3. Create SQLite tables ────────────────────────────────────────────────────
async def _create_tables():
    from db.database import engine
    from db.models import Base
    from db.models_appbuilder import Base as AppBase
    from db.models_marketplace import Base as MktBase
    from db.models_pattern_rules import Base as RulesBase

    # Merge all metadata
    for b in (AppBase, MktBase, RulesBase):
        for table in b.metadata.tables.values():
            if table.name not in Base.metadata.tables:
                table.tometadata(Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✓ SQLite tables created (local_dev.db)")

asyncio.run(_create_tables())

# ── 4. Telegram bot polling ────────────────────────────────────────────────────
async def _run_bot():
    """Run Telegram bot in polling mode — no public URL needed."""
    try:
        from TG_Bot.main import get_bot, get_dispatcher
        bot = get_bot()
        dp  = get_dispatcher()
        print("✓ Telegram bot started (polling mode)")
        print(f"  Open Telegram → find your bot → send /start")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    except Exception as e:
        print(f"⚠  Bot polling error: {e}")
        print("   The API will still work — bot notifications won't be sent")

# ── 5. Start everything ───────────────────────────────────────────────────────
async def _main():
    import uvicorn
    from main import app

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(config)

    print("\n" + "═"*50)
    print("  AI Trade Validator — Local Dev")
    print("═"*50)
    print(f"  API + Mini App: http://localhost:8000/app")
    print(f"  API docs:       http://localhost:8000/docs")
    print(f"  Health check:   http://localhost:8000/health")
    print("═"*50 + "\n")

    # Run bot polling + uvicorn concurrently
    await asyncio.gather(
        _run_bot(),
        server.serve(),
    )

if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\n\nStopped.")
