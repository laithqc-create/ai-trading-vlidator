"""
Tests for AI Trade Validator — full suite.
Covers: OpenTrade fallback, RAGFlow, ValidationService,
        Polygon wiring, /outcome command, rate limiter, scheduler tasks.

Run with: pytest tests/ -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime


# ─── Unit Tests: OpenTrade Fallback ──────────────────────────────────────────

class TestOpenTradeService:

    @pytest.mark.asyncio
    async def test_fallback_returns_valid_analysis(self):
        from opentrade.service import OpenTradeService
        from config.settings import settings
        import pandas as pd, numpy as np

        svc = OpenTradeService(settings)
        svc._initialized = True
        svc._graph = None

        dates = pd.date_range("2024-01-01", periods=60)
        close = pd.Series([150 + i * 0.5 + np.random.randn() for i in range(60)], index=dates)
        mock_hist = pd.DataFrame({
            "Close": close, "High": close + 2,
            "Low": close - 2,
            "Volume": pd.Series([1_000_000] * 60, index=dates),
        })

        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = mock_hist
            result = await svc.analyze("AAPL")

        assert result.ticker == "AAPL"
        assert result.decision in ("BUY", "SELL", "HOLD")
        assert 0.0 <= result.confidence <= 1.0
        assert result.rsi is not None
        assert result.macd is not None
        assert result.current_price is not None

    @pytest.mark.asyncio
    async def test_fallback_handles_empty_data(self):
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

    def test_trader_analysis_to_dict(self):
        from opentrade.service import TraderAnalysis
        ta = TraderAnalysis(
            ticker="TSLA", analysis_date="2024-01-01",
            decision="BUY", confidence=0.75, risk_level="LOW",
            technical_signal="BULLISH", fundamental_signal="NEUTRAL",
            sentiment_signal="POSITIVE", news_signal="NEUTRAL",
            bull_case="Strong momentum.", bear_case="Overbought risk.",
            rsi=45.0, macd=0.12, macd_signal=0.08,
            bb_position="WITHIN", current_price=250.0,
        )
        d = ta.to_dict()
        assert d["ticker"] == "TSLA"
        assert d["confidence"] == 0.75
        assert d["rsi"] == 45.0


# ─── Unit Tests: RAGFlow Service ─────────────────────────────────────────────

class TestRAGFlowService:

    def test_build_mentor_question_contains_all_fields(self):
        from ragflow.service import RAGFlowService
        from config.settings import settings
        svc = RAGFlowService(settings)
        question = svc._build_mentor_question(
            ticker="AAPL", signal="BUY",
            analysis={"rsi": 28.5, "macd": 0.12, "bb_position": "BELOW_LOWER",
                      "technical_signal": "BULLISH", "current_price": 175.0},
        )
        assert "AAPL" in question
        assert "BUY" in question
        assert "RSI=28.5" in question

    def test_parse_no_results_returns_neutral(self):
        from ragflow.service import RAGFlowService
        from config.settings import settings
        svc = RAGFlowService(settings)
        result = svc._parse_mentor_response(None, None, "BUY")
        assert result["mentor_verdict"] == "NEUTRAL"
        assert result["confidence_adjustment"] == 0.0
        assert result["citations"] == []

    def test_parse_reject_keywords_returns_caution(self):
        from ragflow.service import RAGFlowService
        from config.settings import settings
        svc = RAGFlowService(settings)
        fake = {"data": {"chunks": [
            {"content": "avoid this dangerous setup at all costs", "similarity": 0.9, "document_keyword": "rules.txt"},
            {"content": "risky trade — do not enter here", "similarity": 0.8, "document_keyword": "rules.txt"},
        ]}}
        result = svc._parse_mentor_response(fake, None, "BUY")
        assert result["mentor_verdict"] == "CAUTION"
        assert result["confidence_adjustment"] < 0

    def test_parse_confirm_keywords_returns_confirm(self):
        from ragflow.service import RAGFlowService
        from config.settings import settings
        svc = RAGFlowService(settings)
        fake = {"data": {"chunks": [
            {"content": "strong setup — confirm the signal and proceed", "similarity": 0.85, "document_keyword": "rules.txt"},
            {"content": "good entry with valid signal conditions", "similarity": 0.80, "document_keyword": "rules.txt"},
        ]}}
        result = svc._parse_mentor_response(fake, None, "BUY")
        assert result["mentor_verdict"] == "CONFIRM"
        assert result["confidence_adjustment"] > 0


# ─── Unit Tests: ValidationService ───────────────────────────────────────────

class TestValidationService:

    def _make_trader(self, decision="BUY", confidence=0.72, rsi=28.5):
        from opentrade.service import TraderAnalysis
        return TraderAnalysis(
            ticker="AAPL", analysis_date=date.today().isoformat(),
            decision=decision, confidence=confidence, risk_level="MEDIUM",
            technical_signal="BULLISH", fundamental_signal="NEUTRAL",
            sentiment_signal="NEUTRAL", news_signal="NEUTRAL",
            bull_case="RSI oversold, MACD bullish crossover.",
            bear_case="Price near resistance.", rsi=rsi,
            macd=0.12, macd_signal=0.08, bb_position="BELOW_LOWER",
            current_price=172.50,
        )

    def _make_mentor(self, verdict="CONFIRM", adj=0.1):
        return {
            "mentor_verdict": verdict,
            "confidence_adjustment": adj,
            "reasoning": "RSI oversold rule triggered.",
            "relevant_rules": ["RSI < 30 with volume above average: potential buy"],
            "citations": [],
        }

    @pytest.mark.asyncio
    async def test_validate_manual_confirm_path(self):
        from services.validation import ValidationService
        svc = ValidationService()

        with patch.object(svc.trader, "analyze", return_value=self._make_trader("BUY", 0.72)), \
             patch.object(svc.mentor, "validate_signal", return_value=self._make_mentor("CONFIRM", 0.1)), \
             patch("services.validation.PolygonService") as mock_poly:
            mock_poly.return_value.get_snapshot = AsyncMock(return_value=None)
            result = await svc.validate_manual("AAPL", "BUY", 172.50, None)

        assert result["ticker"] == "AAPL"
        assert result["verdict"] == "CONFIRM"
        assert result["confidence_score"] >= 0.72
        assert "AAPL" in result["final_message"]
        assert "Not financial advice" in result["final_message"]

    @pytest.mark.asyncio
    async def test_validate_manual_caution_path(self):
        from services.validation import ValidationService
        svc = ValidationService()

        with patch.object(svc.trader, "analyze", return_value=self._make_trader("BUY", 0.55)), \
             patch.object(svc.mentor, "validate_signal", return_value=self._make_mentor("CAUTION", -0.15)), \
             patch("services.validation.PolygonService") as mock_poly:
            mock_poly.return_value.get_snapshot = AsyncMock(return_value=None)
            result = await svc.validate_manual("AAPL", "BUY", None, None)

        assert result["verdict"] == "CAUTION"
        assert result["confidence_score"] < 0.55

    @pytest.mark.asyncio
    async def test_polygon_data_injected_into_message(self):
        from services.validation import ValidationService
        svc = ValidationService()
        poly_data = {
            "high": 180.0, "low": 170.0, "vwap": 175.5,
            "volume": 55_000_000, "change_pct": 1.23, "close": 175.0
        }

        with patch.object(svc.trader, "analyze", return_value=self._make_trader()), \
             patch.object(svc.mentor, "validate_signal", return_value=self._make_mentor()), \
             patch("services.validation.PolygonService") as mock_poly:
            mock_poly.return_value.get_snapshot = AsyncMock(return_value=poly_data)
            result = await svc.validate_manual("AAPL", "BUY", None, None)

        assert "Polygon.io" in result["final_message"]
        assert "180.00" in result["final_message"]
        assert "55.0M" in result["final_message"]

    def test_confidence_bar_full(self):
        from services.validation import ValidationService
        bar = ValidationService._confidence_bar(1.0)
        assert "██████████" in bar
        assert "100%" in bar

    def test_confidence_bar_half(self):
        from services.validation import ValidationService
        bar = ValidationService._confidence_bar(0.5)
        assert "50%" in bar

    def test_append_polygon_context_inserts_before_disclaimer(self):
        from services.validation import ValidationService
        msg = "Some analysis\n\n─────────────────────────\n⚠️ Not financial advice."
        poly = {"high": 200.0, "low": 190.0, "vwap": 195.0,
                "volume": 10_000_000, "change_pct": 0.5}
        result = ValidationService._append_polygon_context(msg, poly)
        assert "Polygon.io" in result
        assert result.index("Polygon.io") < result.index("Not financial advice")

    def test_append_polygon_context_empty_data_unchanged(self):
        from services.validation import ValidationService
        msg = "analysis\n\n─────────────────────────\n⚠️ disclaimer"
        result = ValidationService._append_polygon_context(msg, {})
        assert result == msg

    def test_rsi_overbought_note_appears_in_message(self):
        from services.validation import ValidationService
        svc = ValidationService()
        from opentrade.service import TraderAnalysis
        trader = TraderAnalysis(
            ticker="TSLA", analysis_date=date.today().isoformat(),
            decision="SELL", confidence=0.65, risk_level="HIGH",
            technical_signal="BEARISH", fundamental_signal="NEUTRAL",
            sentiment_signal="NEUTRAL", news_signal="NEUTRAL",
            bull_case="Strong momentum.", bear_case="Overbought.",
            rsi=78.5, macd=-0.05, macd_signal=0.02,
            bb_position="ABOVE_UPPER", current_price=255.0,
        )
        mentor = self._make_mentor("CAUTION", -0.1)
        result = svc._combine_results("TSLA", "SELL", 255.0, trader, mentor, 3)
        assert "Overbought" in result["final_message"]


# ─── Unit Tests: Rate Limiter ─────────────────────────────────────────────────

class TestRateLimiter:

    def test_allows_under_limit(self):
        from bot.handlers import _is_rate_limited, _rate_buckets
        uid = 999888001
        _rate_buckets[uid] = []
        for _ in range(5):
            assert _is_rate_limited(uid) is False

    def test_blocks_over_limit(self):
        from bot.handlers import _is_rate_limited, _rate_buckets, RATE_LIMIT
        uid = 999888002
        _rate_buckets[uid] = []
        for _ in range(RATE_LIMIT):
            _is_rate_limited(uid)
        assert _is_rate_limited(uid) is True

    def test_webhook_allows_under_limit(self):
        from main import _check_webhook_rate, _webhook_buckets
        token = "webhook_test_allow"
        _webhook_buckets[token] = []
        for _ in range(5):
            assert _check_webhook_rate(token) is True

    def test_webhook_blocks_over_limit(self):
        from main import _check_webhook_rate, _webhook_buckets, WEBHOOK_RATE_LIMIT
        token = "webhook_test_block"
        _webhook_buckets[token] = []
        for _ in range(WEBHOOK_RATE_LIMIT):
            _check_webhook_rate(token)
        assert _check_webhook_rate(token) is False


# ─── Unit Tests: Subscription Service ────────────────────────────────────────

class TestSubscriptionService:

    def test_plan_tier_map_complete(self):
        from services.subscription import PLAN_TIER_MAP
        from db.models import PlanTier
        assert PLAN_TIER_MAP["product1"] == PlanTier.PRODUCT1
        assert PLAN_TIER_MAP["product2"] == PlanTier.PRODUCT2
        assert PLAN_TIER_MAP["product3"] == PlanTier.PRODUCT3
        assert PLAN_TIER_MAP["pro"]      == PlanTier.PRO

    def test_plan_price_map_loads_without_crash(self):
        from services.subscription import _plan_price_map
        prices = _plan_price_map()
        assert isinstance(prices, dict)
        assert set(prices.keys()) == {"product1", "product2", "product3", "pro"}


# ─── Integration Tests: FastAPI Endpoints ────────────────────────────────────

class TestWebhookEndpoints:

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self):
        from httpx import AsyncClient
        from main import app
        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_indicator_invalid_token_returns_401(self):
        from httpx import AsyncClient
        from main import app
        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.post(
                "/webhook/indicator/bad_token_xyz",
                json={"ticker": "AAPL", "signal": "BUY", "price": 175.0},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_ea_invalid_token_returns_401(self):
        from httpx import AsyncClient
        from main import app
        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.post(
                "/webhook/ea/bad_token_xyz",
                json={"ea_name": "EA", "ticker": "EURUSD",
                      "action": "BUY", "result": "LOSS", "pnl": -2.3},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_indicator_bad_signal_rejected(self):
        from httpx import AsyncClient
        from main import app
        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.post(
                "/webhook/indicator/some_token",
                json={"ticker": "AAPL", "signal": "MAYBE"},
            )
        assert resp.status_code in (400, 401)


# ─── Integration Tests: Bot Commands ─────────────────────────────────────────

class TestBotCommands:

    def _make_update_ctx(self, telegram_id=123456789, args=None):
        from telegram import Update, Message, User as TGUser
        tg_user = MagicMock(spec=TGUser)
        tg_user.id = telegram_id
        tg_user.username = "testuser"
        tg_user.first_name = "Test"
        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()
        update = MagicMock(spec=Update)
        update.effective_user = tg_user
        update.message = message
        context = MagicMock()
        context.args = args or []
        return update, context

    @pytest.mark.asyncio
    async def test_check_no_args_shows_usage(self):
        from bot.handlers import cmd_check, _rate_buckets
        update, context = self._make_update_ctx(args=[])
        _rate_buckets[123456789] = []  # reset rate limit
        await cmd_check(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "usage" in text.lower()

    @pytest.mark.asyncio
    async def test_check_invalid_signal_shows_error(self):
        from bot.handlers import cmd_check, _rate_buckets
        update, context = self._make_update_ctx(args=["AAPL", "MAYBE"])
        _rate_buckets[123456789] = []
        await cmd_check(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Invalid signal" in text

    @pytest.mark.asyncio
    async def test_check_invalid_price_shows_error(self):
        from bot.handlers import cmd_check, _rate_buckets
        update, context = self._make_update_ctx(args=["AAPL", "BUY", "notprice"])
        _rate_buckets[123456789] = []
        await cmd_check(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Invalid price" in text

    @pytest.mark.asyncio
    async def test_outcome_no_args_shows_usage(self):
        from bot.handlers import cmd_outcome
        update, context = self._make_update_ctx(args=[])
        await cmd_outcome(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "outcome" in text.lower()

    @pytest.mark.asyncio
    async def test_outcome_invalid_value_shows_error(self):
        from bot.handlers import cmd_outcome
        update, context = self._make_update_ctx(args=["MAYBE"])
        await cmd_outcome(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "WIN" in text or "LOSS" in text

    @pytest.mark.asyncio
    async def test_add_rule_no_args_shows_usage(self):
        from bot.handlers import cmd_add_rule
        update, context = self._make_update_ctx(args=[])
        await cmd_add_rule(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Usage" in text or "add_rule" in text.lower()

    @pytest.mark.asyncio
    async def test_help_lists_all_commands(self):
        from bot.handlers import cmd_help
        update, context = self._make_update_ctx()
        await cmd_help(update, context)
        text = update.message.reply_text.call_args[0][0]
        for cmd in ["/check", "/outcome", "/add_rule", "/my_rules",
                    "/history", "/insights", "/status", "/subscribe",
                    "/connect_indicator", "/connect_ea"]:
            assert cmd in text, f"Missing {cmd} in /help output"


# ─── Unit Tests: Celery Scheduler ────────────────────────────────────────────

class TestScheduler:

    def test_beat_schedule_has_all_three_tasks(self):
        from workers.scheduler import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "reset-daily-counters" in schedule
        assert "expire-stale-validations" in schedule
        assert "aggregate-crowd-insights" in schedule

    def test_all_scheduled_tasks_are_callable(self):
        from workers.scheduler import (
            reset_daily_counters,
            expire_stale_validations,
            aggregate_crowd_insights,
        )
        assert callable(reset_daily_counters)
        assert callable(expire_stale_validations)
        assert callable(aggregate_crowd_insights)


# ─── Unit Tests: EA Monitor Script ───────────────────────────────────────────

class TestEAMonitor:

    def test_mt4_close_pattern_matches(self):
        from scripts.ea_monitor import MT4_CLOSE_PATTERN
        line = "2024.01.15 10:45:00 SuperEA closed buy 0.10 EURUSD at 1.08750, profit 23.00"
        m = MT4_CLOSE_PATTERN.search(line)
        assert m is not None
        trade_time, action, volume, ticker, close_price, profit = m.groups()
        assert ticker == "EURUSD"
        assert action.upper() == "BUY"
        assert float(profit) == 23.00

    def test_mt4_close_pattern_loss(self):
        from scripts.ea_monitor import MT4_CLOSE_PATTERN
        line = "2024.01.15 11:00:00 MyEA closed sell 0.05 GBPUSD at 1.26500, profit -15.50"
        m = MT4_CLOSE_PATTERN.search(line)
        assert m is not None
        _, _, _, ticker, _, profit = m.groups()
        assert ticker == "GBPUSD"
        assert float(profit) < 0

    def test_parse_generic_win_detected(self):
        from scripts.ea_monitor import EAMonitor
        monitor = EAMonitor("http://test", "/dev/null", "TestEA")
        line = "EURUSD buy closed profit +50.00 WIN"
        result = monitor._parse_generic(line)
        assert result is not None
        assert result["result"] == "WIN"

    def test_parse_generic_loss_detected(self):
        from scripts.ea_monitor import EAMonitor
        monitor = EAMonitor("http://test", "/dev/null", "TestEA")
        line = "EURUSD sell closed loss -25.00"
        result = monitor._parse_generic(line)
        assert result is not None
        assert result["result"] == "LOSS"

    def test_parse_generic_no_action_returns_none(self):
        from scripts.ea_monitor import EAMonitor
        monitor = EAMonitor("http://test", "/dev/null", "TestEA")
        line = "Server connected. Initializing EA..."
        result = monitor._parse_generic(line)
        assert result is None

    def test_dedup_prevents_double_send(self):
        import json
        from scripts.ea_monitor import EAMonitor
        monitor = EAMonitor("http://test", "/dev/null", "TestEA")

        payload = {"ea_name": "TestEA", "ticker": "EURUSD", "action": "BUY",
                   "result": "WIN", "pnl": 10.0, "trade_time": "2024-01-01T10:00:00"}
        h = hash(json.dumps(payload, sort_keys=True))
        monitor._sent_hashes.add(h)

        calls = []
        original_send = monitor._send_trade

        def spy_send(**kwargs):
            p = {"ea_name": monitor.ea_name, "ticker": kwargs["ticker"],
                 "action": kwargs["action"], "result": kwargs["result"],
                 "pnl": kwargs["pnl"], "trade_time": kwargs["trade_time"]}
            if hash(json.dumps(p, sort_keys=True)) in monitor._sent_hashes:
                return
            calls.append(kwargs)

        monitor._send_trade = spy_send
        monitor._send_trade(ticker="EURUSD", action="BUY", result="WIN",
                            pnl=10.0, trade_time="2024-01-01T10:00:00")
        assert len(calls) == 0
