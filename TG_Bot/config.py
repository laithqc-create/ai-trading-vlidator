"""
TG_Bot/config.py — Load all environment variables for the bot layer.
Reads from the root .env file.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str

    # Database / Redis
    DATABASE_URL: str
    REDIS_URL: str

    # Whop
    WHOP_API_KEY: str
    WHOP_WEBHOOK_SECRET: str
    WHOP_PRODUCT_ID_PRODUCT1: str
    WHOP_PRODUCT_ID_PRODUCT2: str
    WHOP_PRODUCT_ID_PRODUCT3: str
    WHOP_PRODUCT_ID_PRO: str

    # DeepSeek
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str
    DEEPSEEK_MODEL: str
    DEEPSEEK_COST_PER_GEN: float
    DEEPSEEK_FREE_CAP: float

    # RAGFlow
    RAGFLOW_BASE_URL: str
    RAGFLOW_API_KEY: str
    RAGFLOW_SYSTEM_KB_ID: str

    # Market Data
    POLYGON_API_KEY: str

    # App
    FREE_TIER_DAILY_LIMIT: int
    APP_ENV: str


def load_config() -> Config:
    return Config(
        BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        WHOP_API_KEY=os.getenv("WHOP_API_KEY", ""),
        WHOP_WEBHOOK_SECRET=os.getenv("WHOP_WEBHOOK_SECRET", ""),
        WHOP_PRODUCT_ID_PRODUCT1=os.getenv("WHOP_PRODUCT_ID_PRODUCT1", ""),
        WHOP_PRODUCT_ID_PRODUCT2=os.getenv("WHOP_PRODUCT_ID_PRODUCT2", ""),
        WHOP_PRODUCT_ID_PRODUCT3=os.getenv("WHOP_PRODUCT_ID_PRODUCT3", ""),
        WHOP_PRODUCT_ID_PRO=os.getenv("WHOP_PRODUCT_ID_PRO", ""),
        DEEPSEEK_API_KEY=os.getenv("DEEPSEEK_API_KEY", ""),
        DEEPSEEK_BASE_URL=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        DEEPSEEK_MODEL=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        DEEPSEEK_COST_PER_GEN=float(os.getenv("DEEPSEEK_COST_PER_GEN", "0.002")),
        DEEPSEEK_FREE_CAP=float(os.getenv("DEEPSEEK_FREE_CAP", "5.0")),
        RAGFLOW_BASE_URL=os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380"),
        RAGFLOW_API_KEY=os.getenv("RAGFLOW_API_KEY", ""),
        RAGFLOW_SYSTEM_KB_ID=os.getenv("RAGFLOW_SYSTEM_KB_ID", ""),
        POLYGON_API_KEY=os.getenv("POLYGON_API_KEY", ""),
        FREE_TIER_DAILY_LIMIT=int(os.getenv("FREE_TIER_DAILY_LIMIT", "5")),
        APP_ENV=os.getenv("APP_ENV", "development"),
    )


config = load_config()
