"""
Tests for AI Trade Validator.

Run with: pytest tests/ -v
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

# ─── Unit Tests: OpenTrade Fallback ──────────────────────────────────────────

class TestOpenTradeService:

    @pytest.mark.asyncio
    async def test_fallback_analysis_returns_trader_analysis(self):
        """Fallback analysis should always return a valid TraderAnalysis."""
        from opentrade.service import OpenTradeService
        from config.settings import settings

        svc = OpenTradeService(settings)
        svc._initialized = True     # skip LangGraph init
        svc._graph = None           # force fallback

        with patch("yfinance.Ticker") as mock_ticker:
            import pandas as pd
            import numpy as np

            # Build fake OHLCV data
            dates = pd.date_range("2024-01-01", periods=60)
            close = pd.Series(
                [150 + i * 0.5 + np.random.randn() for i in range(60)], index=dates
            )
            high = close + 2
            low = close - 2
            volume = pd.Series([1_000_000] * 60, index=dates)

            mock_hist = pd.DataFrame({"Close": close, "High": high, "Low": low, "Volume": volume})
            mock_ticker.return_value.history.return_value = mock_hist

            result = await svc.analyze("AAPL")

        assert result.ticker == "AAPL"
        assert result.decision in ("BUY", "SELL", "HOLD")
        assert 0.0 <= result.confidence <= 1.0
        assert result.rsi is not None
        assert result.macd is not None

    @pytest.mark.asyncio
    async def test_fallback_handles_bad_ticker(self):
        """Fallback should return HOLD with low confidence for unknown tickers."""
        from opentrade.service import OpenTradeService
        from config.settings import settings
        import pandas as pd

        svc = OpenTradeService(settings)
        svc._initialized = True
        svc._graph = None

        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = pd.DataFrame()
            result = await svc.analyze("FAKEXYZ99")

        assert result.decision == "HOLD"
        assert result.confidence == 0.5


# ─── Unit Tests: RAGFlow Service ─────────────────────────────────────────────

class TestRAGFlowService:

    def test_build_mentor_question_contains_ticker(self):
        from ragflow.service import RAGFlowService
        from config.settings import settings

        svc = RAGFlowService(settings)
        question = svc._build_mentor_question(
            ticker="AAPL",
            signal="BUY",
            analysis={"rsi": 28.5, "macd": 0.12, "bb_position": "BELOW_LOWER", "technical_signal": "BULLISH"},
        )
        assert "AAPL" in question
        assert "BUY" in question
        assert "RSI=28.5" in question

    def test_parse_mentor_response_no_results(self):
        """No chunks → neutral verdict, zero confidence adjustment."""
        from ragflow.service import RAGFlowService
        from config.settings import settings

        svc = RAGFlowService(settings)
        result = svc._parse_mentor_response(None, None, "BUY")

        assert result["mentor_verdict"] == "NEUTRAL"
        assert result["confidence_adjustment"] == 0.0

    def test_parse_mentor_response_with_reject_keywords(self):
        """Chunks containing reject keywords should return CAUTION verdict."""
        from ragflow.service import RAGFlowService
        from config.settings import settings

        svc = RAGFlowService(settings)

        fake_result = {
            "data": {
                "chunks": [
                    {"content": "avoid trading in this overbought condition", "similarity": 0.85, "document_keyword": "rules.txt"},
                    {"content": "this is a dangerous setup with high risk", "similarity": 0.75, "document_keyword": "rules.txt"},
                ]
            }
        }

        result = svc._parse_mentor_response(fake_result, None, "BUY")
        assert result["mentor_verdict"] == "CAUTION"
        assert result["confidence_adjustment"] < 0


# ─── Unit Tests: Validation Service ──────────────────────────────────────────

class TestValidationService:

    @pytest.mark.asyncio
    async def test_validate_manual_returns_verdict(self):
        from services.validation import ValidationService
        from opentrade.service import TraderAnalysis
        from datetime import date

        svc = ValidationService()

        mock_trader = TraderAnalysis(
            ticker="AAPL",
            analysis_date=date.today().isoformat(),
            decision="BUY",
            confidence=0.72,
            risk_level="MEDIUM",
            technical_signal="BULLISH",
            fundamental_signal="NEUTRAL",
            sentiment_signal="NEUTRAL",
            news_signal="NEUTRAL",
            bull_case="RSI is oversold, MACD bullish crossover.",
            bear_case="Price near resistance.",
            rsi=28.5,
            macd=0.12,
            macd_signal=0.08,
            bb_position="BELOW_LOWER",
            current_price=172.50,
        )

        mock_mentor = {
            "mentor_verdict": "CONFIRM",
            "confidence_adjustment": 0.1,
            "reasoning": "RSI oversold rule triggered. Volume confirms.",
            "relevant_rules": ["RSI below 30 with volume above average: potential buy"],
            "citations": [],
        }

        with patch.object(svc.trader, "analyze", return_value=mock_trader), \
             patch.object(svc.mentor, "validate_signal", return_value=mock_mentor):

            result = await svc.validate_manual(
                ticker="AAPL",
                signal="BUY",
                price=172.50,
                user_ragflow_dataset_id=None,
            )

        assert result["ticker"] == "AAPL"
        assert result["verdict"] in ("CONFIRM", "CAUTION", "REJECT")
        assert 0.0 <= result["confidence_score"] <= 1.0
        assert "AAPL" in result["final_message"]
        assert "Not financial advice" in result["final_message"]

    def test_confidence_bar_output(self):
        from services.validation import ValidationService
        bar = ValidationService._confidence_bar(0.78)
        assert "█" in bar
        assert "78%" in bar

    def test_format_rsi_overbought_note(self):
        """RSI > 70 should show overbought note in message."""
        from services.validation import ValidationService
        from opentrade.service import TraderAnalysis
        from datetime import date

        svc = ValidationService()
        trader = TraderAnalysis(
            ticker="TSLA",
            analysis_date=date.today().isoformat(),
            decision="SELL",
            confidence=0.65,
            risk_level="HIGH",
            technical_signal="BEARISH",
            fundamental_signal="NEUTRAL",
            sentiment_signal="NEUTRAL",
            news_signal="NEUTRAL",
            bull_case="Strong momentum.",
            bear_case="Overbought.",
            rsi=78.5,
            macd=-0.05,
            macd_signal=0.02,
            bb_position="ABOVE_UPPER",
            current_price=255.00,
        )
        mentor = {
            "mentor_verdict": "CAUTION",
            "confidence_adjustment": -0.1,
            "reasoning": "RSI overbought.",
            "relevant_rules": [],
            "citations": [],
        }

        result = svc._combine_results("TSLA", "SELL", 255.0, trader, mentor, product=3)
        assert "Overbought" in result["final_message"]


# ─── Integration Tests: FastAPI Endpoints ────────────────────────────────────

class TestWebhookEndpoints:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_indicator_webhook_invalid_token(self):
        """Request with invalid token should return 401."""
        from httpx import AsyncClient
        from main import app

        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.post(
                "/webhook/indicator/invalid_token_xyz",
                json={"ticker": "AAPL", "signal": "BUY", "price": 175.0},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_ea_webhook_invalid_token(self):
        """EA webhook with invalid token should return 401."""
        from httpx import AsyncClient
        from main import app

        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.post(
                "/webhook/ea/invalid_token_xyz",
                json={
                    "ea_name": "TestEA",
                    "ticker": "EURUSD",
                    "action": "BUY",
                    "result": "LOSS",
                    "pnl": -2.3,
                },
            )
        assert resp.status_code == 401


# ─── Integration Tests: Bot Commands ─────────────────────────────────────────

class TestBotCommands:

    @pytest.mark.asyncio
    async def test_check_command_requires_args(self):
        """
        /check with no arguments should reply with usage instructions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from telegram import Update, Message, User as TGUser, Chat
        from bot.handlers import cmd_check

        # Build mock Telegram objects
        tg_user = MagicMock(spec=TGUser)
        tg_user.id = 123456789
        tg_user.username = "testuser"
        tg_user.first_name = "Test"

        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = tg_user
        update.message = message

        context = MagicMock()
        context.args = []   # No args

        with patch("bot.handlers.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("bot.handlers.UserService") as mock_svc:
                mock_user_instance = MagicMock()
                mock_user_instance.get_or_create_user = AsyncMock(return_value=MagicMock())
                mock_svc.return_value = mock_user_instance

                await cmd_check(update, context)

        # Should have replied with usage info
        message.reply_text.assert_called_once()
        call_text = message.reply_text.call_args[0][0]
        assert "Usage" in call_text or "usage" in call_text.lower()

    @pytest.mark.asyncio
    async def test_check_command_invalid_signal(self):
        """
        /check AAPL INVALID should reply with error.
        """
        from unittest.mock import AsyncMock, MagicMock
        from telegram import Update, Message, User as TGUser
        from bot.handlers import cmd_check

        tg_user = MagicMock()
        tg_user.id = 123456789

        message = MagicMock()
        message.reply_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = tg_user
        update.message = message

        context = MagicMock()
        context.args = ["AAPL", "INVALID"]

        await cmd_check(update, context)

        message.reply_text.assert_called_once()
        assert "Invalid signal" in message.reply_text.call_args[0][0]
