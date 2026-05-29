"""Application settings — loaded from environment / .env file."""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "dev-secret-change-me"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = "placeholder"
    TELEGRAM_WEBHOOK_URL: str = "https://example.com/webhook/telegram"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://trader:trader_pass@localhost:5432/tradevalidator"
    REDIS_URL: str = "redis://localhost:6379/0"

    # DeepSeek AI
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_COST_PER_GEN: float = 0.002

    # Polygon.io market data
    POLYGON_API_KEY: str = ""

    # Whop Payments
    WHOP_API_KEY: str = ""
    WHOP_WEBHOOK_SECRET: str = ""
    WHOP_PRODUCT_ID_PRODUCT1: str = ""
    WHOP_PRODUCT_ID_PRODUCT2: str = ""
    WHOP_PRODUCT_ID_PRODUCT3: str = ""
    WHOP_PRODUCT_ID_PRO: str = ""

    # Whop Checkout URLs (injected into Mini App + Extension upgrade buttons)
    WHOP_PRODUCT1_URL: str = "https://whop.com/checkout/placeholder1"
    WHOP_PRODUCT2_URL: str = "https://whop.com/checkout/placeholder2"
    WHOP_PRODUCT3_URL: str = "https://whop.com/checkout/placeholder3"
    WHOP_PRO_URL: str = "https://whop.com/checkout/placeholderpro"
    WHOP_AFFILIATE_URL: str = "https://whop.com/affiliate/placeholder"

    # RAGFlow
    RAGFLOW_BASE_URL: str = "http://localhost:9380"
    RAGFLOW_API_KEY: str = ""

    # Bot download URLs
    MT4_DOWNLOAD_URL: str = "https://example.com/bots/ATV_Analyzer.mq4"
    MT5_DOWNLOAD_URL: str = "https://example.com/bots/ATV_Analyzer.mq5"
    CTRADER_DOWNLOAD_URL: str = "https://example.com/bots/ATV_Analyzer.cs"

    # Mini App serving
    MINIAPP_BASE_URL: str = "https://example.com"
    API_BASE_URL: str = "https://example.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
