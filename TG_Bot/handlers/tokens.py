"""
TG_Bot/handlers/tokens.py
/tokens command — shows user's three webhook tokens.
Registered in TG_Bot/main.py dispatcher.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from db.database import AsyncSessionLocal
from services.user import UserService

router = Router()


@router.message(Command("tokens"))
async def cmd_tokens(message: Message):
    """Show the user's three webhook tokens with copy-ready formatting."""
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id)
        await user_svc.ensure_all_webhook_tokens(user.id)
        await db.refresh(user)

        ind_token  = user.indicator_webhook_token  or "—"
        ea_token   = user.ea_webhook_token         or "—"
        ss_token   = user.screenshot_webhook_token or "—"

    text = (
        "🔑 *Your Webhook Tokens*\n\n"
        "Use these tokens to connect your platform to AI Trade Validator.\n\n"
        "📊 *Indicator Validator (Product 1)*\n"
        f"`{ind_token}`\n\n"
        "🤖 *EA Analyzer (Product 2)*\n"
        f"`{ea_token}`\n\n"
        "📸 *Screenshot / Live Analysis*\n"
        f"`{ss_token}`\n\n"
        "⚠️ Keep these tokens private — they authenticate all signals "
        "sent to your account.\n\n"
        "Paste a token into the webhook URL on your platform:\n"
        "`https://your-domain.com/webhook/indicator/<TOKEN>`"
    )

    await message.answer(text, parse_mode="Markdown")
