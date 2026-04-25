"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"
    LOG_LEVEL: str = "INFO"
    FREE_TIER_DAILY_LIMIT: int = 5

    # ─── Telegram ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: str = ""

    # ─── Database ─────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://trader:trader_pass@localhost:5432/tradevalidator"
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── LLM (OpenTrade.ai) ───────────────────────────────
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "llama3"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LMSTUDIO_BASE_URL: str = "http://localhost:1234/v1"
    OPENAI_API_KEY: Optional[str] = None

    # ─── RAGFlow ──────────────────────────────────────────
    RAGFLOW_BASE_URL: str = "http://localhost:9380"
    RAGFLOW_API_KEY: str = ""
    RAGFLOW_SYSTEM_KB_ID: str = "system_knowledge_base"
    RAGFLOW_USER_KB_PREFIX: str = "user_"

    # ─── Market Data ──────────────────────────────────────
    POLYGON_API_KEY: Optional[str] = None

    # ─── Stripe ───────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_PRODUCT1: str = ""   # $29/mo
    STRIPE_PRICE_PRODUCT2: str = ""   # $49/mo
    STRIPE_PRICE_PRODUCT3: str = ""   # $19/mo
    STRIPE_PRICE_PRO: str = ""        # $79/mo

    # ─── Webhook Secrets ──────────────────────────────────
    INDICATOR_WEBHOOK_SECRET: str = "change-me-indicator"
    EA_WEBHOOK_SECRET: str = "change-me-ea"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()
