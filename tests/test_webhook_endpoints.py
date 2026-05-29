"""
tests/test_webhook_endpoints.py

Integration tests for /webhook/indicator/{token} and /webhook/ea/{token}.
Uses SQLite in-memory DB via conftest fixtures — no live Postgres or Redis required.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import TestSessionLocal


# ── Helpers ──────────────────────────────────────────────────────────────────

class _FakeAsyncResult:
    id = "test-task-id"


def _make_task_mock():
    """Return a mock Celery task where .delay() is a no-op."""
    m = MagicMock()
    m.delay = MagicMock(return_value=_FakeAsyncResult())
    return m


# ── TestWebhookEndpoints ──────────────────────────────────────────────────────

class TestWebhookEndpoints:

    def _client(self):
        """Build a TestClient with DB + Celery tasks both mocked."""
        from fastapi.testclient import TestClient
        import main as app_module

        patches = [
            patch("main.AsyncSessionLocal", TestSessionLocal),
            patch("main.validate_indicator_task", _make_task_mock()),
            patch("main.analyze_ea_task", _make_task_mock()),
        ]
        return patches, TestClient(app_module.app, raise_server_exceptions=False)

    @pytest.mark.asyncio
    async def test_indicator_webhook_valid_token_returns_200(self, db_session, test_user):
        """Valid token + BUY signal → 200 ok."""
        patches, client = self._client()
        with patches[0], patches[1], patches[2]:
            resp = client.post(
                f"/webhook/indicator/{test_user.indicator_webhook_token}",
                json={"ticker": "AAPL", "signal": "BUY", "price": 175.0, "indicator": "RSI"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "AAPL" in data["message"]
        assert "validation_id" in data

    @pytest.mark.asyncio
    async def test_indicator_webhook_invalid_token_returns_401(self, db_session):
        """Unknown token → 401."""
        patches, client = self._client()
        with patches[0], patches[1], patches[2]:
            resp = client.post(
                "/webhook/indicator/totally-invalid-token-xyz",
                json={"ticker": "AAPL", "signal": "BUY"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_indicator_webhook_bad_signal_returns_400(self, db_session, test_user):
        """Signal not in BUY/SELL/HOLD → 400."""
        patches, client = self._client()
        with patches[0], patches[1], patches[2]:
            resp = client.post(
                f"/webhook/indicator/{test_user.indicator_webhook_token}",
                json={"ticker": "AAPL", "signal": "MAYBE"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_ea_webhook_valid_token_returns_200(self, db_session, test_user):
        """Valid EA token + trade data → 200."""
        patches, client = self._client()
        with patches[0], patches[1], patches[2]:
            resp = client.post(
                f"/webhook/ea/{test_user.ea_webhook_token}",
                json={
                    "ea_name": "TestEA",
                    "ticker": "EURUSD",
                    "action": "BUY",
                    "result": "WIN",
                    "pnl": 2.5,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_ea_webhook_invalid_token_returns_401(self, db_session):
        """Invalid EA token → 401."""
        patches, client = self._client()
        with patches[0], patches[1], patches[2]:
            resp = client.post(
                "/webhook/ea/bad-token-xyz",
                json={"ea_name": "EA", "ticker": "EURUSD", "action": "BUY"},
            )
        assert resp.status_code == 401
