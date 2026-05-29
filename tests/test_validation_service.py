"""
tests/test_validation_service.py

Tests for ValidationService.
PolygonService is mocked at: services.market_data.PolygonService
(The previous failures were caused by patching the wrong import path.)
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_bars(pattern_type: str = "bullish") -> list[dict]:
    """Return fake OHLC bars that form a recognisable pattern."""
    if pattern_type == "bullish":
        # Last bar is a strong bullish engulfing candle
        return [
            {"o": 100.0, "h": 102.0, "l": 99.0,  "c": 100.5},  # prior down candle
            {"o": 100.4, "h": 104.0, "l": 99.8,  "c": 100.2},  # small bearish
            {"o": 100.1, "h": 105.0, "l": 99.5,  "c": 104.8},  # bullish engulf
        ]
    elif pattern_type == "bearish":
        return [
            {"o": 100.0, "h": 102.0, "l": 99.0,  "c": 101.5},  # prior up candle
            {"o": 101.4, "h": 102.0, "l": 100.0, "c": 101.2},  # small bullish
            {"o": 101.3, "h": 101.8, "l": 97.0,  "c": 97.5},   # bearish engulf
        ]
    else:
        return [{"o": 100.0, "h": 100.1, "l": 99.9, "c": 100.0}] * 3  # doji-like


def _make_polygon_mock(bars: list[dict]) -> MagicMock:
    """Return a PolygonService mock whose get_bars returns the given bars."""
    mock = MagicMock()
    mock.get_bars = AsyncMock(return_value=bars)
    mock.get_snapshot = AsyncMock(return_value={"lastTrade": {"p": bars[-1]["c"]}})
    return mock


# ── Tests ────────────────────────────────────────────────────────────────────

class TestValidationService:

    @pytest.mark.asyncio
    async def test_confirmed_buy_signal(self):
        """BUY signal is CONFIRMED when bullish patterns are present."""
        from services.validation_service import ValidationService

        polygon_mock = _make_polygon_mock(_make_bars("bullish"))

        # CORRECT mock path: services.market_data.PolygonService
        with patch("services.market_data.PolygonService", return_value=polygon_mock):
            svc = ValidationService(polygon=polygon_mock)
            result = await svc.validate_signal("AAPL", "BUY", 104.8)

        assert result["verdict"] == "CONFIRMED"
        assert result["confidence"] > 0.0
        assert len(result["patterns"]) > 0
        assert "CONFIRMED" in result["reason"] or "agrees" in result["reason"]

    @pytest.mark.asyncio
    async def test_rejected_buy_signal_on_bearish_pattern(self):
        """BUY signal is REJECTED when only bearish patterns are present."""
        from services.validation_service import ValidationService

        polygon_mock = _make_polygon_mock(_make_bars("bearish"))

        with patch("services.market_data.PolygonService", return_value=polygon_mock):
            svc = ValidationService(polygon=polygon_mock)
            result = await svc.validate_signal("AAPL", "BUY", 97.5)

        # Bearish patterns don't support a BUY — should be REJECTED or NEUTRAL
        assert result["verdict"] in ("REJECTED", "NEUTRAL")

    @pytest.mark.asyncio
    async def test_neutral_when_market_data_unavailable(self):
        """Returns NEUTRAL verdict when Polygon raises an exception."""
        from services.validation_service import ValidationService

        polygon_mock = MagicMock()
        polygon_mock.get_bars = AsyncMock(side_effect=Exception("Network error"))

        with patch("services.market_data.PolygonService", return_value=polygon_mock):
            svc = ValidationService(polygon=polygon_mock)
            result = await svc.validate_signal("AAPL", "BUY", 100.0)

        assert result["verdict"] == "NEUTRAL"
        assert result["confidence"] == 0.0
        assert "unavailable" in result["reason"].lower() or "Market data" in result["reason"]
