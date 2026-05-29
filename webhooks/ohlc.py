"""
webhooks/ohlc.py
OHLC analysis endpoint — receives candle data from MT4/MT5/cTrader bots,
runs DeepSeek pattern detection against user's rules, returns drawing instructions.

Mount in main.py:
  from webhooks.ohlc import router as ohlc_router
  app.include_router(ohlc_router)
"""

from __future__ import annotations
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from db.database import AsyncSessionLocal
from services.user import UserService
from services.deepseek import DeepSeekService
from services.pattern_engine import PatternEngine

router = APIRouter(prefix="/api/ohlc", tags=["ohlc"])


class Candle(BaseModel):
    t: int          # unix timestamp
    o: float        # open
    h: float        # high
    l: float        # low
    c: float        # close
    v: int = 0      # tick volume


class OHLCAnalysisRequest(BaseModel):
    token: str
    symbol: str
    timeframe: str
    candles: List[Candle]
    indicators: Optional[dict] = {}
    platform: str = "mt5"   # mt4 | mt5 | ctrader


@router.post("/analyze")
async def analyze_ohlc(req: OHLCAnalysisRequest):
    """
    Receive OHLC candles from MT4/MT5/cTrader bots.
    Run AI pattern detection + user rule check.
    Return drawing instructions.
    """
    if len(req.candles) < 3:
        raise HTTPException(400, "Need at least 3 candles")

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_webhook_token(req.token, "ea")
        if user is None:
            user = await user_svc.get_user_by_webhook_token(req.token, "indicator")
        if user is None:
            raise HTTPException(401, "Invalid token")

        if not user.has_product_access(2) and not user.has_product_access(1):
            raise HTTPException(403, "OHLC analysis requires an active plan or trial")

        # Load user's personal pattern rules from RAGFlow / DB
        personal_rules = await user_svc.get_personal_rules(user.id)
        ragflow_id = user.ragflow_dataset_id

    # Run pattern detection
    engine = PatternEngine()
    pattern_results = engine.detect(req.candles, personal_rules)

    # Run AI analysis via DeepSeek
    ds = DeepSeekService()
    ai_result = await ds.analyze_ohlc(
        symbol=req.symbol,
        timeframe=req.timeframe,
        candles=[c.dict() for c in req.candles[-20:]],   # last 20 candles
        indicators=req.indicators or {},
        detected_patterns=pattern_results,
        personal_rules=personal_rules,
    )

    # Build drawing instructions for the bot
    drawing = _build_drawing_instructions(
        ai_result=ai_result,
        candles=req.candles,
        platform=req.platform,
    )

    logger.info(f"OHLC analysis: {req.symbol} {req.timeframe} → {ai_result.get('signal')} "
                f"({ai_result.get('pattern')}) for user {user.telegram_id}")

    return {
        "ok": True,
        "signal":   ai_result.get("signal", "NEUTRAL"),
        "pattern":  ai_result.get("pattern", ""),
        "reason":   ai_result.get("reason", ""),
        "confidence": ai_result.get("confidence", 0),
        "drawing":  drawing,
    }


def _build_drawing_instructions(ai_result: dict, candles: list, platform: str) -> dict:
    """
    Build platform-specific drawing instructions.
    The bot uses these to draw arrows, lines, labels on the chart.
    """
    signal  = ai_result.get("signal", "NEUTRAL")
    pattern = ai_result.get("pattern", "")
    reason  = ai_result.get("reason", "")

    last_candle = candles[-1] if candles else None
    last_ts = last_candle.t if last_candle else 0

    return {
        "arrow": {
            "time":      last_ts,
            "direction": "up" if signal == "BUY" else ("down" if signal == "SELL" else "none"),
            "color":     "lime" if signal == "BUY" else ("red" if signal == "SELL" else "yellow"),
            "label":     f"{signal} | {pattern}",
            "tooltip":   reason,
        },
        # Future: add horizontal lines for SR levels, Fibonacci, etc.
        "lines": ai_result.get("levels", []),
    }
