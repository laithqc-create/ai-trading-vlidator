"""User service — database operations for users."""
import secrets
from datetime import date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import User, PlanTier
from ragflow.service import RAGFlowService
from config.settings import settings
from loguru import logger


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

            # Auto-create RAGFlow dataset for new user
            ragflow = RAGFlowService(settings)
            dataset_id = await ragflow.create_user_dataset(telegram_id)
            if dataset_id:
                user.ragflow_dataset_id = dataset_id

        else:
            # Update name if changed
            if username and user.username != username:
                user.username = username

        return user

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_webhook_token(
        self, token: str, webhook_type: str
    ) -> Optional[User]:
        if webhook_type == "indicator":
            result = await self.db.execute(
                select(User).where(User.indicator_webhook_token == token)
            )
        else:
            result = await self.db.execute(
                select(User).where(User.ea_webhook_token == token)
            )
        return result.scalar_one_or_none()

    async def get_or_create_webhook_token(
        self, user: User, webhook_type: str
    ) -> str:
        if webhook_type == "indicator":
            if not user.indicator_webhook_token:
                user.indicator_webhook_token = secrets.token_urlsafe(32)
            return user.indicator_webhook_token
        else:
            if not user.ea_webhook_token:
                user.ea_webhook_token = secrets.token_urlsafe(32)
            return user.ea_webhook_token

    async def increment_daily_count(self, user: User):
        today = date.today()
        if user.daily_validation_date != today:
            user.daily_validation_count = 1
            user.daily_validation_date = today
        else:
            user.daily_validation_count = (user.daily_validation_count or 0) + 1

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

    async def increment_generation_cost(self, user: User, cost: float):
        """Track DeepSeek API usage against the free cap."""
        user.total_generations = (user.total_generations or 0) + 1
        user.total_generation_cost = round((user.total_generation_cost or 0.0) + cost, 4)

    def generation_budget_remaining(self, user: User) -> float:
        """Returns remaining free generation budget in USD."""
        from config.settings import settings
        spent = user.total_generation_cost or 0.0
        return max(0.0, settings.DEEPSEEK_FREE_CAP - spent)

    def is_over_generation_cap(self, user: User) -> bool:
        from config.settings import settings
        return (user.total_generation_cost or 0.0) >= settings.DEEPSEEK_FREE_CAP
