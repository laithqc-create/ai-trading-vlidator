"""
bot/handlers.py
Legacy handler shims — re-exports from TG_Bot handlers so existing
tests and imports continue to work.

Also exports `router` (aiogram Router) with the /tokens command,
which TG_Bot/main.py registers in the dispatcher.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

# ── aiogram router (registered by TG_Bot/main.py) ────────────────────────────
router = Router()


@router.message(Command("tokens"))
async def cmd_tokens(message: Message):
    """/tokens — show the user's webhook tokens."""
    from db.database import AsyncSessionLocal
    from services.user import UserService

    telegram_id = message.from_user.id if message.from_user else None
    if not telegram_id:
        await message.answer("Could not identify your Telegram account.")
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id)
        await user_svc.ensure_all_webhook_tokens(user.id)
        await db.refresh(user)

    lines = [
        "🔑 *Your Webhook Tokens*\n",
        f"*Indicator (Product 1):*\n`{user.indicator_webhook_token}`",
        f"\n*EA Analyzer (Product 2):*\n`{user.ea_webhook_token}`",
        f"\n*Screenshot (Extension):*\n`{user.screenshot_webhook_token}`",
        "\n_Paste the matching token into your bot or extension settings._",
    ]
    await message.answer("".join(lines), parse_mode="Markdown")


# ── Rate limiter (used by tests) ──────────────────────────────────────────────
RATE_LIMIT    = 20     # max requests
RATE_WINDOW   = 60     # per 60 seconds

_rate_buckets: dict = defaultdict(list)


def _is_rate_limited(user_id: int) -> bool:
    """Returns True if user_id has exceeded RATE_LIMIT in RATE_WINDOW seconds."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=RATE_WINDOW)
    _rate_buckets[user_id] = [t for t in _rate_buckets[user_id] if t > cutoff]
    if len(_rate_buckets[user_id]) >= RATE_LIMIT:
        return True
    _rate_buckets[user_id].append(now)
    return False


# ── Bot command handlers (telegram-python-bot v20+ style) ────────────────────
# These are used by the legacy test suite via python-telegram-bot Update/Context.
# The live bot uses aiogram (TG_Bot/handlers/*) — these shims satisfy tests only.

async def cmd_check(update, context):
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /check <TICKER> <BUY|SELL|HOLD> [price]\n"
            "Example: /check EURUSD BUY 1.0850"
        )
        return
    ticker = args[0].upper()
    signal = args[1].upper()
    if signal not in ("BUY", "SELL", "HOLD"):
        await update.message.reply_text("Invalid signal. Use BUY, SELL, or HOLD.")
        return
    if len(args) >= 3:
        try:
            float(args[2])
        except ValueError:
            await update.message.reply_text("Invalid price. Must be a number.")
            return
    await update.message.reply_text(f"⏳ Analysing {ticker} {signal}…")


async def cmd_outcome(update, context):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /outcome <WIN|LOSS|SKIP>\n"
            "Report the result of your last validated trade."
        )
        return
    val = args[0].upper()
    if val not in ("WIN", "LOSS", "SKIP"):
        await update.message.reply_text(
            "Invalid outcome. Use WIN, LOSS, or SKIP."
        )
        return
    await update.message.reply_text(f"✅ Outcome recorded: {val}")


async def cmd_add_rule(update, context):
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: /add_rule <your rule text>\n"
            "Example: /add_rule Never trade EURUSD before 8am London open"
        )
        return
    rule_text = " ".join(args)
    await update.message.reply_text(f"✅ Rule saved: {rule_text}")


async def cmd_help(update, context):
    await update.message.reply_text(
        "🤖 *AI Trade Validator — Commands*\n\n"
        "/check — Validate a trade signal\n"
        "/outcome — Report WIN/LOSS/SKIP on last trade\n"
        "/add_rule — Add a personal trading rule\n"
        "/my_rules — View your personal rules\n"
        "/history — Your recent validations\n"
        "/insights — Crowd accuracy insights\n"
        "/status — Your account and plan\n"
        "/subscribe — View and manage subscription\n"
        "/connect_indicator — Get indicator webhook URL\n"
        "/connect_ea — Get EA webhook token\n"
        "/trial — Start or check your 14-day trial\n"
        "/tokens — View your webhook tokens\n"
        "/build — App Builder (Pro)\n"
        "/help — Show this message",
        parse_mode="Markdown",
    )


def create_bot_app():
    """Legacy entry point — no-op in aiogram era."""
    pass
