"""User service — all database operations for users."""
import secrets
from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, delete, update
from db.models import User, PlanTier
from ragflow.service import RAGFlowService
from config.settings import settings
from loguru import logger

TRIAL_DURATION_DAYS = 14

_TOKEN_COLUMN = {
    "indicator":  "indicator_webhook_token",
    "ea":         "ea_webhook_token",
    "screenshot": "screenshot_webhook_token",
}


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Core ──────────────────────────────────────────────────────────────────

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                plan=PlanTier.FREE,
            )
            self.db.add(user)
            await self.db.flush()
            logger.info(f"New user created: telegram_id={telegram_id}")

            try:
                ragflow = RAGFlowService(settings)
                dataset_id = await ragflow.create_user_dataset(telegram_id)
                if dataset_id:
                    user.ragflow_dataset_id = dataset_id
            except Exception as e:
                logger.warning(f"RAGFlow dataset creation skipped: {e}")
        else:
            if username and user.username != username:
                user.username = username

        return user

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    # ── Webhook tokens ────────────────────────────────────────────────────────

    async def get_user_by_webhook_token(
        self, token: str, token_type: str = "any"
    ) -> Optional[User]:
        """
        Resolve a user from any webhook token.
        token_type: "indicator" | "ea" | "screenshot" | "any"
        """
        if not token or len(token) < 8:
            return None

        if token_type == "any":
            result = await self.db.execute(
                select(User).where(
                    or_(
                        User.indicator_webhook_token  == token,
                        User.ea_webhook_token         == token,
                        User.screenshot_webhook_token == token,
                    )
                ).limit(1)
            )
        else:
            col = _TOKEN_COLUMN.get(token_type)
            if not col:
                raise ValueError(f"Unknown token_type '{token_type}'")
            result = await self.db.execute(
                select(User).where(getattr(User, col) == token).limit(1)
            )

        return result.scalar_one_or_none()

    async def generate_webhook_token(
        self, user_id: int, token_type: str, force: bool = False
    ) -> str:
        col = _TOKEN_COLUMN.get(token_type)
        if not col:
            raise ValueError(f"Unknown token_type '{token_type}'")

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        existing = getattr(user, col, None)
        if existing and not force:
            return existing

        token = secrets.token_hex(16)
        setattr(user, col, token)
        self.db.add(user)
        await self.db.flush()
        return token

    async def ensure_all_webhook_tokens(self, user_id: int) -> dict:
        """Create tokens for all 3 products if not present. Returns all three."""
        tokens = {}
        for t in ("indicator", "ea", "screenshot"):
            tokens[t] = await self.generate_webhook_token(user_id, t, force=False)
        return tokens

    # Legacy alias used by old main.py code
    async def get_or_create_webhook_token(self, user: User, webhook_type: str) -> str:
        return await self.generate_webhook_token(user.id, webhook_type)

    # ── Trial system ──────────────────────────────────────────────────────────

    async def start_trial(self, telegram_id: int) -> User:
        """Start a 14-day trial for a FREE user who has never trialled."""
        user = await self.get_or_create_user(telegram_id=telegram_id)
        if user.plan != PlanTier.FREE or user.trial_started_at is not None:
            return user
        now = datetime.utcnow()
        user.plan             = PlanTier.TRIAL
        user.trial_started_at = now
        user.trial_expires_at = now + timedelta(days=TRIAL_DURATION_DAYS)
        self.db.add(user)
        await self.db.flush()
        return user

    async def expire_trials(self) -> int:
        """Downgrade expired trials to FREE. Called by nightly Celery beat."""
        now = datetime.utcnow()
        result = await self.db.execute(
            update(User)
            .where(User.plan == PlanTier.TRIAL)
            .where(User.trial_expires_at <= now)
            .values(plan=PlanTier.FREE)
            .returning(User.id)
        )
        ids = result.fetchall()
        await self.db.flush()
        return len(ids)

    async def get_trial_status(self, telegram_id: int) -> dict:
        user = await self.get_user_by_telegram_id(telegram_id)
        if user is None:
            return {"has_trial": False, "active": False, "days_remaining": 0, "used": False}

        if user.plan == PlanTier.TRIAL and user.is_trial_active():
            return {
                "has_trial": True, "active": True,
                "days_remaining": user.trial_days_remaining(),
                "used": True,
                "expires_at": user.trial_expires_at.isoformat(),
            }
        if user.trial_started_at is not None:
            return {"has_trial": True, "active": False, "days_remaining": 0, "used": True}
        return {"has_trial": False, "active": False, "days_remaining": 0, "used": False}

    # ── Pattern rules ─────────────────────────────────────────────────────────

    async def get_personal_rules_structured(self, user_id: int) -> dict:
        from db.models_pattern_rules import UserPatternRule
        result = await self.db.execute(
            select(UserPatternRule).where(UserPatternRule.user_id == user_id)
        )
        rules = result.scalars().all()
        return {
            r.pattern_name: {
                "enabled":          r.enabled,
                "min_body_ratio":   r.min_body_ratio,
                "max_wick_ratio":   r.max_wick_ratio,
                "min_engulf_ratio": r.min_engulf_ratio,
            }
            for r in rules
        }

    async def get_personal_rules(self, user_id: int) -> list:
        structured = await self.get_personal_rules_structured(user_id)
        return [{"name": k, **v} for k, v in structured.items()]

    async def upsert_pattern_rule(self, user_id: int, pattern_name: str, update_dict: dict):
        from db.models_pattern_rules import UserPatternRule
        result = await self.db.execute(
            select(UserPatternRule).where(
                UserPatternRule.user_id == user_id,
                UserPatternRule.pattern_name == pattern_name,
            )
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            rule = UserPatternRule(user_id=user_id, pattern_name=pattern_name)
            self.db.add(rule)
        for k, v in update_dict.items():
            if hasattr(rule, k):
                setattr(rule, k, v)
        await self.db.flush()

    async def add_personal_rule(self, user_id: int, rule_text: str):
        """Save a free-text rule override from chat (used by chart chat endpoint)."""
        from db.models import UserRule
        rule = UserRule(user_id=user_id, rule_text=rule_text, is_active=True)
        self.db.add(rule)
        await self.db.flush()

    async def delete_pattern_rule(self, user_id: int, pattern_name: str):
        from db.models_pattern_rules import UserPatternRule
        await self.db.execute(
            delete(UserPatternRule).where(
                UserPatternRule.user_id == user_id,
                UserPatternRule.pattern_name == pattern_name,
            )
        )
        await self.db.flush()

    async def delete_all_pattern_rules(self, user_id: int):
        from db.models_pattern_rules import UserPatternRule
        await self.db.execute(
            delete(UserPatternRule).where(UserPatternRule.user_id == user_id)
        )
        await self.db.flush()

    # ── Plan / subscription ───────────────────────────────────────────────────

    async def update_plan(
        self,
        telegram_id: int,
        plan: PlanTier,
        whop_user_id: Optional[str] = None,
        whop_membership_id: Optional[str] = None,
        expires_at=None,
    ) -> Optional[User]:
        user = await self.get_user_by_telegram_id(telegram_id)
        if user:
            user.plan = plan
            if whop_user_id:
                user.whop_user_id = whop_user_id
            if whop_membership_id:
                user.whop_membership_id = whop_membership_id
            if expires_at:
                user.plan_expires_at = expires_at
        return user

    # ── Usage / generation tracking ───────────────────────────────────────────

    async def increment_daily_count(self, user: User):
        today = date.today()
        if user.daily_validation_date != today:
            user.daily_validation_count = 1
            user.daily_validation_date = today
        else:
            user.daily_validation_count = (user.daily_validation_count or 0) + 1

    async def increment_generation_cost(self, user: User, cost: float):
        user.total_generations     = (user.total_generations or 0) + 1
        user.total_generation_cost = round((user.total_generation_cost or 0.0) + cost, 4)

    def generation_budget_remaining(self, user: User) -> float:
        spent = user.total_generation_cost or 0.0
        return max(0.0, settings.DEEPSEEK_FREE_CAP - spent)

    def is_over_generation_cap(self, user: User) -> bool:
        return (user.total_generation_cost or 0.0) >= settings.DEEPSEEK_FREE_CAP
