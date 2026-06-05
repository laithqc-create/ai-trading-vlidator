"""
webhooks/ohlc.py — Unified OHLC analysis endpoint.
Handles data from ALL sources:
  - MT4/MT5/cTrader EA   → candle-close data
  - Browser extension    → screenshot + candle data
  - Indicator webhook    → indicator fire data
Runs: pattern detection + all indicators + AI verdict
Returns: structured report for Mini App, Telegram, extension, and chart drawing
"""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger
from db.database import AsyncSessionLocal
from db.models import AnalysisReport
from services.user import UserService
from services.deepseek import DeepSeekService
from services.pattern_engine import PatternEngine
from services.indicator_engine import IndicatorEngine

router = APIRouter(prefix="/api/ohlc", tags=["ohlc"])


class Candle(BaseModel):
    t: int; o: float; h: float; l: float; c: float; v: int = 0


class OHLCRequest(BaseModel):
    token: str
    symbol: str
    timeframe: str
    candles: List[Candle]
    source: str = "ea"              # ea | extension | indicator
    platform: str = "mt5"          # mt4 | mt5 | ctrader | extension
    enabled_indicators: Optional[List[str]] = None
    indicator_settings: Optional[dict] = None
    # EA analyser trade context
    trade_direction: Optional[str] = None   # buy | sell
    trade_price: Optional[float] = None
    trade_context: Optional[str] = None     # open | close | sl | tp


@router.post("/analyze")
async def analyze_ohlc(req: OHLCRequest):
    if len(req.candles) < 5:
        raise HTTPException(400, "Need at least 5 candles")

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_webhook_token(req.token, "any")
        if user is None:
            raise HTTPException(401, "Invalid token")
        if not (user.has_product_access(1) or user.has_product_access(2)):
            raise HTTPException(403, "Requires Signal Validator, EA Analyser, Pro, or active trial")

        personal_rules     = await user_svc.get_personal_rules(user.id)
        enabled_indicators = await user_svc.get_enabled_indicators(user.id)
        indicator_settings = await user_svc.get_indicator_settings(user.id)

    # Request-level overrides
    if req.enabled_indicators is not None:
        enabled_indicators = req.enabled_indicators
    if req.indicator_settings:
        indicator_settings = {**(indicator_settings or {}), **req.indicator_settings}

    candles_raw = [c.model_dump() for c in req.candles]

    # 1 — Pattern detection
    patterns = PatternEngine().detect(req.candles, personal_rules)

    # 2 — Indicator calculation
    ind_report = IndicatorEngine().calculate_for_report(
        candles_raw,
        enabled=enabled_indicators,
        user_settings=indicator_settings,
    )

    # 3 — AI verdict
    ds = DeepSeekService()
    trade_ctx = {"direction": req.trade_direction, "price": req.trade_price,
                 "event": req.trade_context} if req.trade_direction else None

    ai = await ds.analyze_ohlc(
        symbol=req.symbol, timeframe=req.timeframe,
        candles=candles_raw[-20:],
        indicators=_flatten(ind_report),
        detected_patterns=patterns,
        personal_rules=personal_rules,
        trade_context=trade_ctx,
    )

    # 4 — Structured report
    report = {
        "symbol": req.symbol, "timeframe": req.timeframe, "source": req.source,
        "signal": ai.get("signal", "NEUTRAL"),
        "pattern": ai.get("pattern", ""),
        "reason": ai.get("reason", ""),
        "confidence": round(ai.get("confidence", 0) * 100),
        "patterns": patterns,
        "indicators": ind_report,
        "levels": ai.get("levels", []),
    }
    if req.trade_direction:
        report["trade"] = {
            "direction": req.trade_direction, "price": req.trade_price,
            "event": req.trade_context,
            "verdict":    ai.get("trade_verdict", ""),
            "why_entry":  ai.get("why_entry", ""),
            "why_result": ai.get("why_result", ""),
        }

    # 5 — Drawing instructions (MT bots only)
    drawing = None
    if req.source == "ea" and req.candles:
        last = req.candles[-1]
        sig = ai.get("signal", "NEUTRAL")
        drawing = {
            "arrow": {
                "time": last.t,
                "direction": "up" if sig == "BUY" else ("down" if sig == "SELL" else "none"),
                "color": "lime" if sig == "BUY" else ("red" if sig == "SELL" else "yellow"),
                "label": f"{sig} | {ai.get('pattern','')}",
                "tooltip": ai.get("reason", ""),
            },
            "lines": ai.get("levels", []),
        }

    logger.info(f"OHLC [{req.source}] {req.symbol} {req.timeframe} → {ai.get('signal','?')} ({ai.get('pattern','?')})")

    # Persist report for /api/user/last-report
    async with AsyncSessionLocal() as db:
        db.add(AnalysisReport(
            user_id=user.id,
            source=req.source,
            symbol=req.symbol,
            timeframe=req.timeframe,
            report=report,
        ))
        await db.commit()

    return {"ok": True, "signal": ai.get("signal","NEUTRAL"), "pattern": ai.get("pattern",""),
            "reason": ai.get("reason",""), "confidence": ai.get("confidence",0),
            "report": report, "drawing": drawing}


def _flatten(ind_report: dict) -> dict:
    flat = {}
    for group in ind_report.get("groups", {}).values():
        for name, data in group.items():
            if data.get("value") is not None:
                flat[name] = data["value"]
    return flat
