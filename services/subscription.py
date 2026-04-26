"""Stripe subscription service."""
from typing import Optional
from loguru import logger
from db.models import PlanTier

# Tier map is static — safe at import time
PLAN_TIER_MAP = {
    "product1": PlanTier.PRODUCT1,
    "product2": PlanTier.PRODUCT2,
    "product3": PlanTier.PRODUCT3,
    "pro": PlanTier.PRO,
}


def _plan_price_map() -> dict:
    """Lazy-load price IDs — only reads settings when actually called."""
    from config.settings import settings
    return {
        "product1": settings.STRIPE_PRICE_PRODUCT1,
        "product2": settings.STRIPE_PRICE_PRODUCT2,
        "product3": settings.STRIPE_PRICE_PRODUCT3,
        "pro":      settings.STRIPE_PRICE_PRO,
    }


class SubscriptionService:
    async def create_checkout_session(
        self, telegram_id: int, plan: str
    ) -> Optional[str]:
        """Create a Stripe checkout session. Returns the checkout URL."""
        try:
            import stripe
            from config.settings import settings
            stripe.api_key = settings.STRIPE_SECRET_KEY

            price_id = _plan_price_map().get(plan)
            if not price_id:
                logger.error(f"Unknown plan: {plan}")
                return None

            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=f"https://t.me/{(await self._get_bot_username())}?start=subscribed",
                cancel_url=f"https://t.me/{(await self._get_bot_username())}?start=cancelled",
                metadata={"telegram_id": str(telegram_id), "plan": plan},
                subscription_data={
                    "metadata": {"telegram_id": str(telegram_id), "plan": plan}
                },
            )
            return session.url
        except Exception as e:
            logger.error(f"Stripe checkout session error: {e}")
            return None

    async def _get_bot_username(self) -> str:
        try:
            from telegram import Bot
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            me = await bot.get_me()
            return me.username or "tradevalidator_bot"
        except Exception:
            return "tradevalidator_bot"

    def handle_webhook_event(self, payload: bytes, sig_header: str) -> Optional[dict]:
        """Parse and verify a Stripe webhook event."""
        try:
            import stripe
            from config.settings import settings
            stripe.api_key = settings.STRIPE_SECRET_KEY
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except Exception as e:
            logger.error(f"Stripe webhook verification failed: {e}")
            return None
