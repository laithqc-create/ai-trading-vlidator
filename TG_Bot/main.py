"""
TG_Bot/main.py — Aiogram 3.x bot entry point.

Architecture:
  Bot + Dispatcher
    ↓
  SubscriptionMiddleware (runs before every handler)
    ↓
  Routers: start | generate | validate | subscription
    ↓
  FSM Storage: Redis (persistent across restarts)

Run modes:
  Polling  (development): python TG_Bot/main.py
  Webhook  (production):  Handled by FastAPI in main.py at root
"""
import asyncio
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from TG_Bot.config import config
from TG_Bot.middleware.subscription import SubscriptionMiddleware
from TG_Bot.handlers import start, generate, validate, subscription as sub_handler
from db.database import init_db


def create_dispatcher(use_redis: bool = True) -> Dispatcher:
    """
    Create and configure the aiogram Dispatcher.

    Uses Redis FSM storage in production so state survives restarts.
    Falls back to MemoryStorage in development.
    """
    if use_redis and config.REDIS_URL:
        try:
            storage = RedisStorage.from_url(config.REDIS_URL)
            logger.info("FSM storage: Redis")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), using MemoryStorage")
            storage = MemoryStorage()
    else:
        storage = MemoryStorage()
        logger.info("FSM storage: Memory")

    dp = Dispatcher(storage=storage)

    # ── Middleware ────────────────────────────────────────────
    # Runs before every message and callback — injects user object
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # ── Routers ───────────────────────────────────────────────
    # Order matters: more specific routers first
    dp.include_router(generate.router)       # /generate, /generate_ea, /share_code
    dp.include_router(validate.router)       # /check, /outcome, /history
    dp.include_router(sub_handler.router)    # /subscribe, /insights
    dp.include_router(start.router)          # /start, menu buttons, /help (catch-all last)

    return dp


def create_bot() -> Bot:
    """Create the Bot instance with HTML parse mode default."""
    return Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


async def on_startup(bot: Bot):
    """Called when bot starts — set commands menu."""
    from aiogram.types import BotCommand, BotCommandScopeDefault

    commands = [
        BotCommand(command="start",              description="🏠 Main menu"),
        BotCommand(command="generate",           description="🆓 English → Pine Script"),
        BotCommand(command="generate_ea",        description="🆓 English → MQL5 EA"),
        BotCommand(command="share_code",         description="📄 Share Pine Script source"),
        BotCommand(command="my_usage",           description="📊 Free generation budget"),
        BotCommand(command="check",              description="🔍 Validate a trade (paid)"),
        BotCommand(command="outcome",            description="📝 Report trade result"),
        BotCommand(command="add_rule",           description="📚 Add personal trading rule"),
        BotCommand(command="my_rules",           description="📋 List your rules"),
        BotCommand(command="history",            description="📜 Last 10 validations"),
        BotCommand(command="insights",           description="⭐ Crowd stats (Pro)"),
        BotCommand(command="connect_indicator",  description="🔌 TradingView webhook"),
        BotCommand(command="connect_ea",         description="⚙️ EA monitor setup"),
        BotCommand(command="subscribe",          description="💳 Upgrade plan (Whop)"),
        BotCommand(command="status",             description="👤 My account"),
        BotCommand(command="link",              description="🔗 Link browser extension"),
        BotCommand(command="help",               description="❓ All commands"),
    ]

    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logger.info(f"Bot @{(await bot.get_me()).username} started. {len(commands)} commands registered.")


async def on_shutdown(bot: Bot):
    """Cleanup on shutdown."""
    logger.info("Bot shutting down...")
    await bot.session.close()


async def run_polling():
    """Run the bot in polling mode (development)."""
    await init_db()

    bot = create_bot()
    dp  = create_dispatcher(use_redis=True)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting polling mode...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )


# ── Integration with FastAPI webhook (production) ────────────────────────────
# In production the FastAPI server in root main.py handles the webhook.
# It creates the bot and dispatcher using these factories.

_bot_instance: Bot | None = None
_dp_instance: Dispatcher | None = None


def get_bot() -> Bot:
    """Singleton bot instance for use in FastAPI webhook handler."""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = create_bot()
    return _bot_instance


def get_dispatcher() -> Dispatcher:
    """Singleton dispatcher instance for use in FastAPI webhook handler."""
    global _dp_instance
    if _dp_instance is None:
        _dp_instance = create_dispatcher(use_redis=True)
    return _dp_instance


if __name__ == "__main__":
    logger.remove()
    logger.add(
        sys.stderr,
        level=config.APP_ENV == "production" and "INFO" or "DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    asyncio.run(run_polling())
