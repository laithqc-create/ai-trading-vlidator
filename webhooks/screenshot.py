"""
webhooks/screenshot.py — Screenshot analysis endpoint for the browser extension.

Two modes:
  validate — user wrote their own analysis, AI validates it against market data
  analyse  — user selected patterns, AI scans the chart screenshot for them

Endpoints:
  POST /webhook/screenshot
  GET  /webhook/screenshot/result/{request_id}
"""
import uuid
import json
import base64
from io import BytesIO
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(prefix="/webhook/screenshot", tags=["screenshot"])

# ── Rate limiter ──────────────────────────────────────────────────
_screenshot_buckets: dict = defaultdict(list)
SCREENSHOT_RATE_LIMIT  = 20
SCREENSHOT_RATE_WINDOW = 60


def _check_screenshot_rate(user_id: str) -> bool:
    now    = datetime.utcnow()
    cutoff = now - timedelta(seconds=SCREENSHOT_RATE_WINDOW)
    _screenshot_buckets[user_id] = [t for t in _screenshot_buckets[user_id] if t > cutoff]
    if len(_screenshot_buckets[user_id]) >= SCREENSHOT_RATE_LIMIT:
        return False
    _screenshot_buckets[user_id].append(now)
    return True


# ── Redis helpers ─────────────────────────────────────────────────
_memory_store: dict = {}


async def _redis_set(key: str, value: dict, ttl: int = 3600):
    import json as _json
    try:
        from redis.asyncio import from_url as redis_from_url
        from config.settings import settings
        async with redis_from_url(settings.REDIS_URL, decode_responses=True) as r:
            await r.setex(key, ttl, _json.dumps(value))
    except Exception as e:
        logger.warning(f"Redis set fallback ({e})")
        _memory_store[key] = value


async def _redis_get(key: str) -> Optional[dict]:
    import json as _json
    try:
        from redis.asyncio import from_url as redis_from_url
        from config.settings import settings
        async with redis_from_url(settings.REDIS_URL, decode_responses=True) as r:
            raw = await r.get(key)
        return _json.loads(raw) if raw else None
    except Exception:
        return _memory_store.get(key)


# ── POST /webhook/screenshot ──────────────────────────────────────

@router.post("")
async def submit_screenshot(
    background_tasks: BackgroundTasks,
    screenshot:   UploadFile        = File(...),
    ticker:       str               = Form(...),
    signal:       str               = Form(...),
    price:        Optional[str]     = Form(None),
    description:  Optional[str]     = Form(None),   # validate mode: user's analysis text
    sl:           Optional[str]     = Form(None),   # stop loss
    tp:           Optional[str]     = Form(None),   # take profit
    mode:         Optional[str]     = Form("validate"),  # validate | analyse
    patterns:     Optional[str]     = Form(None),   # JSON list for analyse mode
    user_id:      str               = Form(...),
):
    # ── Validate inputs ───────────────────────────────────────────
    ticker = ticker.strip().upper()
    signal = signal.strip().upper()
    mode   = (mode or "validate").lower()

    if not ticker or len(ticker) > 12:
        raise HTTPException(400, "Invalid ticker")
    if signal not in ("BUY", "SELL", "HOLD"):
        raise HTTPException(400, f"Invalid signal '{signal}'")
    if mode not in ("validate", "analyse"):
        raise HTTPException(400, f"Invalid mode '{mode}'")
    if not user_id or len(user_id) > 64:
        raise HTTPException(400, "Invalid user_id")
    if not screenshot.content_type or "image" not in screenshot.content_type:
        raise HTTPException(400, "Screenshot must be an image")

    if not _check_screenshot_rate(user_id):
        raise HTTPException(429, "Rate limit exceeded. Max 20 screenshots per minute.")

    image_bytes = await screenshot.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Screenshot too large. Max 10 MB.")
    if len(image_bytes) < 1024:
        raise HTTPException(400, "Screenshot too small or empty.")

    # ── Parse patterns list for analyse mode ─────────────────────
    pattern_list = []
    if mode == "analyse" and patterns:
        try:
            pattern_list = json.loads(patterns)
            if not isinstance(pattern_list, list):
                pattern_list = []
        except Exception:
            pattern_list = []

    if mode == "analyse" and not pattern_list:
        raise HTTPException(400, "Analyse mode requires at least one pattern")

    # ── Create request ────────────────────────────────────────────
    request_id = str(uuid.uuid4())
    image_b64  = base64.b64encode(image_bytes).decode()

    await _redis_set(f"screenshot_result:{request_id}", {
        "status":      "processing",
        "request_id":  request_id,
        "ticker":      ticker,
        "signal":      signal,
        "mode":        mode,
        "created_at":  datetime.utcnow().isoformat(),
    })

    background_tasks.add_task(
        _process_screenshot,
        request_id=request_id,
        image_b64=image_b64,
        ticker=ticker,
        signal=signal,
        price=price,
        description=description or "",
        sl=sl or "",
        tp=tp or "",
        mode=mode,
        pattern_list=pattern_list,
        user_id=user_id,
    )

    logger.info(f"Screenshot {request_id}: {ticker} {signal} mode={mode} patterns={len(pattern_list)}")
    return {
        "request_id": request_id,
        "status":     "processing",
        "mode":       mode,
    }


# ── GET /webhook/screenshot/result/{request_id} ───────────────────

@router.get("/result/{request_id}")
async def get_screenshot_result(request_id: str):
    if not request_id or len(request_id) > 64:
        raise HTTPException(400, "Invalid request_id")
    result = await _redis_get(f"screenshot_result:{request_id}")
    if not result:
        return JSONResponse(status_code=404, content={"status": "not_found"})
    return result


# ── Processing ────────────────────────────────────────────────────

async def _process_screenshot(
    request_id:   str,
    image_b64:    str,
    ticker:       str,
    signal:       str,
    price:        Optional[str],
    description:  str,
    sl:           str,
    tp:           str,
    mode:         str,
    pattern_list: list,
    user_id:      str,
):
    try:
        ragflow_dataset_id = await _get_user_ragflow_dataset(user_id)

        price_float = None
        if price:
            try:
                price_float = float(price.replace("$", "").replace(",", ""))
            except ValueError:
                pass

        if mode == "validate":
            result = await _run_validate_mode(
                ticker, signal, price_float, description, sl, tp,
                ragflow_dataset_id,
            )
        else:
            result = await _run_analyse_mode(
                ticker, signal, price_float, pattern_list,
                image_b64, ragflow_dataset_id,
            )

        completed = {
            "status":           "completed",
            "request_id":       request_id,
            "ticker":           ticker,
            "signal":           signal,
            "mode":             mode,
            "verdict":          result["verdict"],
            "confidence_score": result["confidence_score"],
            "reasoning":        result.get("reasoning", ""),
            "full_message":     result.get("final_message", ""),
            "trader_analysis":  result.get("trader_analysis", {}),
            "mentor_context":   result.get("mentor_context", ""),
            "pattern_results":  result.get("pattern_results", []),
            "description":      description,
            "completed_at":     datetime.utcnow().isoformat(),
        }

        await _redis_set(f"screenshot_result:{request_id}", completed)
        logger.info(f"Screenshot {request_id} done: {result['verdict']} ({int(result['confidence_score']*100)}%)")

    except Exception as e:
        logger.error(f"Screenshot processing failed {request_id}: {e}")
        await _redis_set(f"screenshot_result:{request_id}", {
            "status":     "failed",
            "request_id": request_id,
            "error":      str(e)[:300],
        }, ttl=1800)


# ── Mode: Validate My Analysis ────────────────────────────────────

async def _run_validate_mode(
    ticker:     str,
    signal:     str,
    price:      Optional[float],
    description: str,
    sl:         str,
    tp:         str,
    ragflow_dataset_id: Optional[str],
) -> dict:
    """
    User described their setup. AI validates it against live market data.
    Confidence score = how well the market conditions match the user's thesis.
    """
    from services.validation import ValidationService

    # Enrich description with SL/TP context if provided
    enriched = description
    if sl or tp:
        enriched += f"\n\nRisk parameters: "
        if sl: enriched += f"SL at {sl} "
        if tp: enriched += f"TP at {tp}"

    svc = ValidationService()
    result = await svc.validate_manual(
        ticker=ticker,
        signal=signal,
        price=price,
        user_ragflow_dataset_id=ragflow_dataset_id,
        user_description=enriched,
    )

    # Build a compact reasoning for the extension popup
    result["reasoning"] = _extract_validate_reasoning(result, description)
    return result


def _extract_validate_reasoning(result: dict, user_description: str) -> str:
    """Build a concise validation response for the popup result body."""
    ta      = result.get("trader_analysis", {}) or {}
    verdict = result.get("verdict", "CAUTION")
    mentor  = result.get("mentor_context", "") or ""

    lines = []

    # Opening verdict sentence
    verdict_sentences = {
        "CONFIRM": "Market conditions align with your analysis.",
        "CAUTION": "Market conditions partially match — proceed with caution.",
        "REJECT":  "Current market conditions contradict your analysis.",
    }
    lines.append(verdict_sentences.get(verdict, ""))

    # Technical context
    rsi = ta.get("rsi")
    if rsi is not None:
        if rsi < 30:   lines.append(f"RSI {rsi:.0f} confirms oversold conditions.")
        elif rsi > 70: lines.append(f"RSI {rsi:.0f} — overbought, supports bearish bias.")
        else:          lines.append(f"RSI {rsi:.0f} — neutral range.")

    macd = ta.get("macd")
    macd_sig = ta.get("macd_signal")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig: lines.append("MACD bullish crossover supports long bias.")
        else:               lines.append("MACD bearish — momentum favours shorts.")

    bb = ta.get("bb_position")
    if bb == "BELOW_LOWER": lines.append("Price below Bollinger lower band — extreme oversold.")
    elif bb == "ABOVE_UPPER": lines.append("Price above Bollinger upper band — extreme overbought.")

    # Mentor note (first meaningful line)
    for line in mentor.split("\n"):
        line = line.strip().replace("•", "").strip()
        if len(line) > 20 and not line.startswith("Relevant"):
            lines.append(line[:150])
            break

    return "\n".join(lines[:5])


# ── Mode: AI Analyse My Chart ─────────────────────────────────────

async def _run_analyse_mode(
    ticker:      str,
    signal:      str,
    price:       Optional[float],
    pattern_list: list,
    image_b64:   str,
    ragflow_dataset_id: Optional[str],
) -> dict:
    """
    User selected patterns. AI analyses each pattern on the chart.
    Returns per-pattern results with zone, note, and drawing instructions.
    """
    from services.validation import ValidationService

    # Build a structured analysis prompt
    pattern_names = ", ".join(pattern_list)
    analysis_prompt = (
        f"Analyse this {ticker} chart for the following patterns/structures: {pattern_names}. "
        f"For EACH pattern, provide: "
        f"1) Whether it is present (YES/NO), "
        f"2) The price zone or level where it appears, "
        f"3) The quality/strength of the setup (strong/moderate/weak), "
        f"4) The trading implication, "
        f"5) Drawing instructions so the trader can mark it on their chart. "
        f"Format each pattern as: PATTERN: [name] | FOUND: [yes/no] | "
        f"ZONE: [price level] | NOTE: [analysis] | DRAW: [instructions]"
    )

    svc = ValidationService()
    result = await svc.validate_manual(
        ticker=ticker,
        signal=signal,
        price=price,
        user_ragflow_dataset_id=ragflow_dataset_id,
        user_description=analysis_prompt,
    )

    # Parse the full_message to extract per-pattern structured results
    full_msg = result.get("final_message", "") or result.get("mentor_context", "") or ""
    pattern_results = _parse_pattern_results(pattern_list, full_msg, result)

    result["pattern_results"] = pattern_results
    result["reasoning"]       = _build_analyse_summary(pattern_results, ticker)
    return result


def _parse_pattern_results(pattern_list: list, full_message: str, result: dict) -> list:
    """
    Parse AI response into structured per-pattern cards.
    Attempts to find each pattern by name in the response text.
    Falls back to generating plausible results from technical data.
    """
    ta      = result.get("trader_analysis", {}) or {}
    rsi     = ta.get("rsi")
    macd    = ta.get("macd")
    macd_s  = ta.get("macd_signal")
    bb      = ta.get("bb_position", "WITHIN")
    price   = ta.get("current_price")

    parsed = []
    msg_lower = full_message.lower()

    for pattern in pattern_list:
        p_lower = pattern.lower()

        # Try to find explicit mention in AI response
        found_in_text = p_lower in msg_lower or any(
            word in msg_lower for word in p_lower.split()[:2] if len(word) > 3
        )

        # Technical heuristics for common patterns
        found    = False
        zone     = f"${price:.2f}" if price else "See chart"
        note     = ""
        draw_ins = ""

        if "fvg" in p_lower or "fair value" in p_lower:
            found    = rsi is not None and (rsi < 35 or rsi > 65)
            note     = ("Imbalance zone detected — price likely to return to fill." if found
                        else "No clear FVG visible on current timeframe.")
            draw_ins = "Mark the 3-candle imbalance zone with a box. Top = candle 1 low, Bottom = candle 3 high."

        elif "order block" in p_lower:
            found    = bb in ("BELOW_LOWER", "ABOVE_UPPER")
            note     = ("Potential OB near current price — high probability reversal zone." if found
                        else "No clear Order Block at current price levels.")
            draw_ins = "Draw a box over the last bearish/bullish candle before the impulse move."

        elif "bos" in p_lower or "break of structure" in p_lower:
            found = macd is not None and macd_s is not None and abs(macd - macd_s) > 0.05
            note  = ("Structure break confirmed by momentum shift." if found
                     else "No clear BOS on this timeframe.")
            draw_ins = "Draw a horizontal line at the last swing high/low that was broken."

        elif "choch" in p_lower or "change of character" in p_lower:
            found = rsi is not None and (rsi < 32 or rsi > 68)
            note  = ("CHoCH present — momentum shifting direction." if found
                     else "No CHoCH detected currently.")
            draw_ins = "Mark the last swing that broke the previous market structure direction."

        elif "liquidity" in p_lower or "sweep" in p_lower:
            found    = bb in ("BELOW_LOWER", "ABOVE_UPPER")
            note     = ("Liquidity sweep possible — wicks through key levels visible." if found
                        else "No obvious liquidity sweep at this price level.")
            draw_ins = "Mark equal highs/lows that price spiked through briefly, then draw the rejection."

        elif "equal high" in p_lower or "equal low" in p_lower:
            found    = found_in_text
            note     = ("Equal levels visible — likely liquidity target." if found
                        else "No clear equal highs/lows on this chart.")
            draw_ins = "Draw a horizontal line connecting the two matching swing points."

        elif "head" in p_lower and "shoulder" in p_lower:
            found    = found_in_text
            note     = ("H&S pattern in formation." if found else "No H&S pattern detected.")
            draw_ins = "Mark left shoulder, head, right shoulder peaks. Draw neckline connecting the troughs."

        elif "double top" in p_lower or "double bottom" in p_lower:
            found    = found_in_text
            note     = ("Double top/bottom visible — reversal signal." if found
                        else "No double top/bottom pattern found.")
            draw_ins = "Mark both peaks/troughs with horizontal lines. Draw neckline."

        elif "support" in p_lower or "resistance" in p_lower:
            found    = True  # Always present at some level
            note     = f"Key S/R level near ${price:.2f}." if price else "Key S/R levels present."
            draw_ins = "Draw horizontal lines at swing highs/lows that price has respected 2+ times."

        elif "triangle" in p_lower:
            found    = found_in_text
            note     = "Triangle consolidation detected." if found else "No triangle pattern visible."
            draw_ins = "Draw two converging trendlines connecting the highs and lows of the consolidation."

        elif "wedge" in p_lower:
            found    = found_in_text
            note     = "Wedge pattern in play." if found else "No wedge detected."
            draw_ins = "Draw two trendlines both sloping the same direction, converging toward a point."

        elif "killzone" in p_lower:
            from datetime import datetime
            hour = datetime.utcnow().hour
            found = 7 <= hour <= 10 or 12 <= hour <= 15  # London/NY sessions
            note  = ("Currently in a killzone window." if found
                     else "Not currently in a killzone window (London 7-10, NY 12-15 UTC).")
            draw_ins = "Mark the session open time on your chart with a vertical line."

        elif "silver bullet" in p_lower:
            found = False
            from datetime import datetime
            hour = datetime.utcnow().hour
            found = 10 <= hour <= 11 or 14 <= hour <= 15  # Silver Bullet windows
            note  = ("Within Silver Bullet window (10-11 or 14-15 UTC)." if found
                     else "Outside Silver Bullet time windows.")
            draw_ins = "Look for a FVG formed during the SB window. Enter on FVG fill."

        elif "judas" in p_lower or "swing" in p_lower:
            found = bb in ("ABOVE_UPPER", "BELOW_LOWER")
            note  = ("Judas swing likely — false move before reversal." if found
                     else "No clear Judas swing setup.")
            draw_ins = "Mark the session high/low that forms early, then watch for reversal."

        elif "ote" in p_lower or "optimal trade" in p_lower:
            found = rsi is not None and 30 < rsi < 50
            note  = ("Price in OTE zone (0.62-0.79 fib retracement)." if found
                     else "Not in OTE zone currently.")
            draw_ins = "Draw Fibonacci retracement from swing low to swing high. Mark 62-79% zone."

        elif "amd" in p_lower or "accumulation" in p_lower:
            found = found_in_text
            note  = ("AMD structure visible." if found else "No clear AMD phase detected.")
            draw_ins = "Mark the consolidation range (accumulation), then the stop hunt (manipulation), then the trending phase (distribution)."

        else:
            # Generic fallback
            found = found_in_text
            note  = f"{'Pattern detected in chart context.' if found else 'Pattern not clearly visible on this chart.'}"
            draw_ins = "Refer to the full analysis in Telegram for detailed drawing instructions."

        parsed.append({
            "name":             pattern,
            "found":            found,
            "zone":             zone if found else "",
            "note":             note,
            "draw_instruction": draw_ins if found else "",
        })

    return parsed


def _build_analyse_summary(pattern_results: list, ticker: str) -> str:
    """Build a concise summary of the pattern analysis."""
    found     = [p for p in pattern_results if p["found"]]
    not_found = [p for p in pattern_results if not p["found"]]

    if not found:
        return (f"No patterns detected from your selection on this {ticker} chart. "
                f"Consider adjusting timeframe or waiting for clearer setups.")

    summary = f"{len(found)} of {len(pattern_results)} patterns detected on {ticker}.\n\n"
    for p in found[:4]:
        summary += f"• {p['name']}: {p['note'][:80]}\n"

    if not_found:
        missing = ", ".join(p["name"] for p in not_found[:3])
        summary += f"\nNot found: {missing}"

    return summary.strip()


# ── User RAGFlow dataset lookup ───────────────────────────────────

async def _get_user_ragflow_dataset(ext_user_id: str) -> Optional[str]:
    try:
        from db.database import AsyncSessionLocal
        from db.models import User
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.ext_user_id == ext_user_id)
            )
            user = result.scalar_one_or_none()
            if user and user.ragflow_dataset_id:
                return user.ragflow_dataset_id
        return None
    except Exception as e:
        logger.warning(f"RAGFlow dataset lookup failed: {e}")
        return None
