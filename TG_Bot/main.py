"""
TG_Bot/main.py
==============
Runnable directly:  python TG_Bot/main.py

- Loads .env from repo root
- Creates SQLite tables if they don't exist
- Starts bot in POLLING mode (no public URL needed)
- Works alongside uvicorn running in a separate terminal

CMD 1: cloudflared.exe tunnel --url http://localhost:8000
CMD 2: uvicorn main:app --port 8000
CMD 3: python TG_Bot/main.py
"""
import asyncio
import os
import sys
from pathlib import Path

# ── Load .env from repo root ───────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
env_path = ROOT / ".env"
if not env_path.exists():
    # Fall back to local_dev.env
    env_path = ROOT / "local_dev.env"

if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
    print(f"✓ Loaded env from {env_path.name}")
else:
    print("WARNING: no .env or local_dev.env found — using system environment")

# Add repo root to path so imports work when run from any directory
sys.path.insert(0, str(ROOT))

from config.settings import settings
from aiogram import Bot, Dispatcher
from loguru import logger

# ── Bot + Dispatcher singletons ───────────────────────────────────────────────
_bot: Bot | None = None
_dp: Dispatcher | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return _bot


def get_dispatcher() -> Dispatcher:
    global _dp
    if _dp is None:
        _dp = Dispatcher()
        _register_handlers(_dp)
    return _dp


def _register_handlers(dp: Dispatcher):
    from TG_Bot.handlers import trial, appbuilder, core
    from bot.handlers import router as tokens_router
    dp.include_router(core.router)       # /start /help /status /subscribe /history /connect_* /my_rules /add_rule
    dp.include_router(trial.router)      # /trial + trial_start callback
    dp.include_router(appbuilder.router) # /build FSM
    dp.include_router(tokens_router)     # /tokens


async def on_startup(bot: Bot):
    """Called when running as webhook (uvicorn mode)."""
    await bot.set_webhook(settings.TELEGRAM_WEBHOOK_URL)


# ── Table creation ────────────────────────────────────────────────────────────
async def _ensure_tables():
    """Create DB tables if they don't exist yet (SQLite safe, Postgres safe)."""
    from db.database import engine
    from db.models import Base
    from db.models_appbuilder import Base as AppBase
    from db.models_marketplace import Base as MktBase
    from db.models_pattern_rules import Base as RulesBase

    for b in (AppBase, MktBase, RulesBase):
        for table in b.metadata.tables.values():
            if table.name not in Base.metadata.tables:
                table.tometadata(Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✓ Database tables ready")


# ── Entry point ───────────────────────────────────────────────────────────────
async def _run_polling():
    await _ensure_tables()

    bot = get_bot()
    dp  = get_dispatcher()

    # Delete any existing webhook so polling works cleanly
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    print(f"\n✓ Bot started: @{me.username}")
    print(f"  Send /start to @{me.username} in Telegram to get your tokens\n")

    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    try:
        asyncio.run(_run_polling())
    except KeyboardInterrupt:
        print("\nBot stopped.")
