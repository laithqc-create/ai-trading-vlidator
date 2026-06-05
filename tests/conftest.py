"""
Shared test fixtures.

- SQLite in-memory DB so tests never need live Postgres.
- Overrides DATABASE_URL before any module imports the engine.
- Provides `db_session`, `test_user`, and `test_client` fixtures.
"""
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch

# ── Override DB URL to SQLite before any engine is created ──────────────────
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:test")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """In-memory SQLite session — creates all tables fresh per test."""
    from db.models import Base
    from db.models_appbuilder import Base as AppBase  # noqa
    from db.models_marketplace import Base as MktBase  # noqa
    from db.models_pattern_rules import Base as RulesBase  # noqa
    try:
        from db.models_indicator_prefs import Base as IndBase  # noqa
    except ImportError:
        pass

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session):
    """A fresh User with a TRIAL plan and all webhook tokens set."""
    from db.models import User, PlanTier
    from datetime import datetime, timedelta

    user = User(
        telegram_id=123456789,
        username="testuser",
        plan=PlanTier.TRIAL,
        trial_started_at=datetime.utcnow(),
        trial_expires_at=datetime.utcnow() + timedelta(days=14),
        indicator_webhook_token="test-indicator-token-abcdef1234567890",
        ea_webhook_token="test-ea-token-abcdef1234567890123",
        screenshot_webhook_token="test-screenshot-token-abcdef12345",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_client():
    """FastAPI TestClient with the DB overridden to SQLite in-memory."""
    from fastapi.testclient import TestClient
    from db.database import AsyncSessionLocal
    import main as app_module

    # Patch AsyncSessionLocal used inside endpoint handlers
    with patch("db.database.AsyncSessionLocal", TestSessionLocal):
        with patch("main.AsyncSessionLocal", TestSessionLocal):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            yield client
