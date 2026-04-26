"""
TG_Bot/middleware/subscription.py

Aiogram middleware that:
1. Ensures every user exists in the database (auto-creates on first message)
2. Injects user object into handler data so handlers don't repeat DB lookups
3. Checks subscription status and injects plan info
4. Handles rate limiting (20 requests/minute per user)

Usage in main.py:
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
"""
from typing import Callable, Awaitable, Any
from datetime import datetime, timedelta
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from loguru import logger

from db.database import AsyncSessionLocal
from db.models import User, PlanTier

# In-memory rate limiter
_rate_buckets: dict = defaultdict(list)
RATE_LIMIT = 20
RATE_WINDOW = 60  # seconds


def _is_rate_limited(telegram_id: int) -> bool:
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=RATE_WINDOW)
    _rate_buckets[telegram_id] = [t for t in _rate_buckets[telegram_id] if t > cutoff]
    if len(_rate_buckets[telegram_id]) >= RATE_LIMIT:
        return True
    _rate_buckets[telegram_id].append(now)
    return False


class SubscriptionMiddleware(BaseMiddleware):
    """
    Runs before every message and callback query.
    Injects 'user' and 'user_plan' into handler data.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:

        # Extract Telegram user from event
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if not tg_user:
            return await handler(event, data)

        telegram_id = tg_user.id

        # Rate limiting
        if _is_rate_limited(telegram_id):
            if isinstance(event, Message):
                await event.answer("⏱ Slow down! Max 20 requests/minute.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏱ Rate limit hit. Wait a moment.", show_alert=True)
            return

        # Fetch or create user in DB — inject into handler data
        async with AsyncSessionLocal() as db:
            from services.user import UserService
            user_svc = UserService(db)
            user = await user_svc.get_or_create_user(
                telegram_id=telegram_id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            # Inject into handler kwargs
            data["user"]      = user
            data["user_plan"] = user.plan
            data["db"]        = db

        return await handler(event, data)
