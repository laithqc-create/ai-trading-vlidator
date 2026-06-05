"""
tests/test_validation_service.py
Tests for ValidationService. PolygonService mocked at services.market_data.PolygonService.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_bars(pattern_type: str = "bullish") -> list[dict]:
    if pattern_type == "bullish":
        # Strong bullish engulfing: prior candle bearish, current candle fully engulfs it
        return [
            {"o": 102.0, "h": 102.5, "l": 99.0, "c": 100.0, "v": 1000},  # bearish prior
            {"o": 102.0, "h": 102.5, "l": 99.0, "c": 100.0, "v": 1000},  # bearish prior
            {"o": 99.5,  "h": 103.5, "l": 99.0, "c": 103.0, "v": 2000},  # bull engulf
        ]
    elif pattern_type == "bearish":
        # Strong bearish engulfing: prior candle bullish, current candle fully engulfs it
        return [
            {"o": 99.0, "h": 103.0, "l": 98.5, "c": 102.0, "v": 1000},  # bullish prior
            {"o": 99.0, "h": 103.0, "l": 98.5, "c": 102.0, "v": 1000},  # bullish prior
            {"o": 102.5, "h": 103.0, "l": 98.0, "c": 98.5, "v": 2000},  # bear engulf
        ]
    else:
        return [{"o": 100.0, "h": 100.05, "l": 99.95, "c": 100.0, "v": 500}] * 5


def _make_polygon_mock(bars):
    mock = MagicMock()
    mock.get_bars = AsyncMock(return_value=bars)
    mock.get_snapshot = AsyncMock(return_value={"lastTrade": {"p": bars[-1]["c"]}})
    return mock


class TestValidationService:

    @pytest.mark.asyncio
    async def test_confirmed_buy_signal(self):
        """BUY signal CONFIRMED when bullish patterns present."""
        from services.validation_service import ValidationService
        polygon_mock = _make_polygon_mock(_make_bars("bullish"))
        with patch("services.market_data.PolygonService", return_value=polygon_mock):
            svc = ValidationService(polygon=polygon_mock)
            result = await svc.validate_signal("AAPL", "BUY", 103.0)
        assert result["verdict"] == "CONFIRMED"
        assert result["confidence"] > 0.0
        assert len(result["patterns"]) > 0

    @pytest.mark.asyncio
    async def test_rejected_buy_signal_on_bearish_pattern(self):
        """BUY signal REJECTED when only bearish patterns present."""
        from services.validation_service import ValidationService
        polygon_mock = _make_polygon_mock(_make_bars("bearish"))
        with patch("services.market_data.PolygonService", return_value=polygon_mock):
            svc = ValidationService(polygon=polygon_mock)
            result = await svc.validate_signal("AAPL", "BUY", 98.5)
        assert result["verdict"] in ("REJECTED", "NEUTRAL")

    @pytest.mark.asyncio
    async def test_neutral_when_market_data_unavailable(self):
        """Returns NEUTRAL when data fetch raises exception."""
        from services.validation_service import ValidationService
        polygon_mock = MagicMock()
        polygon_mock.get_bars = AsyncMock(side_effect=Exception("Network error"))
        with patch("services.market_data.PolygonService", return_value=polygon_mock):
            svc = ValidationService(polygon=polygon_mock)
            result = await svc.validate_signal("AAPL", "BUY", 100.0)
        assert result["verdict"] == "NEUTRAL"
        assert result["confidence"] == 0.0
