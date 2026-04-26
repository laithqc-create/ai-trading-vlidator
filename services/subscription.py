"""
Whop Payments integration — replaces Stripe entirely.

Whop supports 241 territories, multi-processor routing, instant payouts,
and has a built-in affiliate system for future use.

API docs: https://dev.whop.com
"""
import httpx
from typing import Optional
from loguru import logger
from db.models import PlanTier

# Static tier map — safe at import time
PLAN_TIER_MAP = {
    "product1": PlanTier.PRODUCT1,
    "product2": PlanTier.PRODUCT2,
    "product3": PlanTier.PRODUCT3,
    "pro":      PlanTier.PRO,
}

PLAN_NAMES = {
    "product1": "Indicator Validator ($19/mo)",
    "product2": "EA Analyzer ($49/mo)",
    "product3": "Manual Validator ($19/mo)",
    "pro":      "Pro Bundle ($79/mo)",
}


def _product_id_map() -> dict:
    """Lazy-load Whop product IDs from settings."""
    from config.settings import settings
    return {
        "product1": settings.WHOP_PRODUCT_ID_PRODUCT1,
        "product2": settings.WHOP_PRODUCT_ID_PRODUCT2,
        "product3": settings.WHOP_PRODUCT_ID_PRODUCT3,
        "pro":      settings.WHOP_PRODUCT_ID_PRO,
    }


class WhopService:
    """
    Whop payment service.

    Checkout: redirect user to Whop checkout link (per product).
    Webhooks: Whop POSTs to /webhook/whop on subscription events.
    Verification: call Whop API to confirm subscription status.
    """

    BASE_URL = "https://api.whop.com/api/v2"

    def __init__(self):
        from config.settings import settings
        self.api_key = settings.WHOP_API_KEY
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_checkout_url(self, plan: str, telegram_id: int) -> Optional[str]:
        """
        Build a Whop checkout URL for a given plan.

        Whop checkout links are pre-built per product in the Whop dashboard.
        We append metadata (telegram_id) as a query param so the webhook
        can match payment to the user.

        Format: https://whop.com/checkout/<product_id>/?telegram_id=<id>
        """
        from config.settings import settings
        product_id = _product_id_map().get(plan)
        if not product_id:
            logger.error(f"No Whop product ID configured for plan: {plan}")
            return None
        return f"https://whop.com/checkout/{product_id}/?d2c=true&metadata[telegram_id]={telegram_id}&metadata[plan]={plan}"

    async def verify_subscription(self, whop_user_id: str) -> Optional[dict]:
        """
        Verify a user's active subscription via Whop API.
        Returns subscription data or None if no active sub.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/memberships",
                    headers=self._headers,
                    params={"user_id": whop_user_id, "status": "active"},
                )
                resp.raise_for_status()
                data = resp.json()
                memberships = data.get("data", [])
                return memberships[0] if memberships else None
            except Exception as e:
                logger.error(f"Whop verify_subscription error: {e}")
                return None

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Whop webhook HMAC signature.
        Whop signs with HMAC-SHA256 using your webhook secret.
        """
        import hmac, hashlib
        from config.settings import settings

        expected = hmac.new(
            settings.WHOP_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_plan_from_product_id(self, product_id: str) -> Optional[str]:
        """Map a Whop product ID back to our internal plan key."""
        id_map = _product_id_map()
        for plan_key, pid in id_map.items():
            if pid == product_id:
                return plan_key
        return None
