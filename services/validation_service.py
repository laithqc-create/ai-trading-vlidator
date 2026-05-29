"""
services/validation_service.py
Validates indicator signals using market data and pattern detection.

Used by workers/tasks.py validate_indicator_task.
"""
from typing import Optional
from services.market_data import PolygonService
from services.pattern_engine import PatternEngine, PatternRule


class ValidationService:
    """Orchestrates signal validation: fetch data → detect patterns → verdict."""

    def __init__(self, polygon: Optional[PolygonService] = None):
        # Injected so tests can mock easily
        self.polygon = polygon or PolygonService()
        self.engine = PatternEngine()

    async def validate_signal(
        self,
        ticker: str,
        signal: str,
        price: float,
        personal_rules: Optional[list[PatternRule]] = None,
    ) -> dict:
        """
        Validate a BUY/SELL signal against live market data.

        Returns a dict with keys:
            verdict       str  CONFIRMED | REJECTED | NEUTRAL
            confidence    float  0–1
            patterns      list[str]  detected pattern names
            reason        str  human-readable explanation
        """
        try:
            bars = await self.polygon.get_bars(ticker, timespan="day", limit=50)
        except Exception as exc:
            return {
                "verdict": "NEUTRAL",
                "confidence": 0.0,
                "patterns": [],
                "reason": f"Market data unavailable: {exc}",
            }

        if not bars:
            return {
                "verdict": "NEUTRAL",
                "confidence": 0.0,
                "patterns": [],
                "reason": "No market data returned",
            }

        # Convert Polygon bars (already dicts) — PatternEngine expects dict with o/h/l/c keys
        candles = [
            {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
            for b in bars
        ]

        matches = self.engine.detect(candles, personal_rules or [])

        if not matches:
            return {
                "verdict": "NEUTRAL",
                "confidence": 0.0,
                "patterns": [],
                "reason": "No candle patterns detected",
            }

        # Determine if patterns agree with the signal
        bullish_patterns = [m for m in matches if m["bullish"]]
        bearish_patterns = [m for m in matches if not m["bullish"]]

        if signal == "BUY":
            agreeing = bullish_patterns
        elif signal == "SELL":
            agreeing = bearish_patterns
        else:
            agreeing = matches

        if agreeing:
            top = agreeing[0]
            verdict = "CONFIRMED"
            confidence = top["confidence"]
            reason = f"Pattern {top['name']} agrees with {signal} signal (confidence {confidence:.0%})"
        else:
            verdict = "REJECTED"
            confidence = 0.1
            reason = f"Detected patterns do not support {signal}"

        return {
            "verdict": verdict,
            "confidence": confidence,
            "patterns": [m["name"] for m in matches],
            "reason": reason,
        }
