"""Whop payment service."""
import hmac, hashlib
from db.models import PlanTier

PLAN_TIER_MAP = {
    "product1": PlanTier.PRODUCT1,
    "product2": PlanTier.PRODUCT2,
    "product3": PlanTier.PRODUCT3,
    "pro":      PlanTier.PRO,
}


class WhopService:
    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify Whop HMAC-SHA256 webhook signature."""
        try:
            from config.settings import settings
            secret = settings.WHOP_WEBHOOK_SECRET.encode()
            if not secret:
                return True  # Skip verification if no secret configured
            expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature.removeprefix("sha256="))
        except Exception:
            return False

    async def get_checkout_url(self, plan: str, telegram_id: int) -> str:
        from config.settings import settings
        urls = {
            "product1": settings.WHOP_PRODUCT1_URL,
            "product2": settings.WHOP_PRODUCT2_URL,
            "product3": settings.WHOP_PRODUCT3_URL,
            "pro":      settings.WHOP_PRO_URL,
        }
        base = urls.get(plan, settings.WHOP_PRO_URL)
        return f"{base}?ref={telegram_id}"

    async def handle_membership_went_valid(self, data: dict):
        pass

    async def handle_membership_was_cancelled(self, data: dict):
        pass
