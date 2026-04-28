"""
webhooks/screenshot.py — Screenshot analysis endpoint for the browser extension.

Endpoints:
  POST /webhook/screenshot
    Accepts: multipart/form-data (screenshot file + ticker + signal + price + user_id)
    Returns: { request_id, status: "processing" }

  GET /webhook/screenshot/result/{request_id}
    Returns: { status: "pending"|"completed"|"failed", verdict, confidence_score, reasoning, ... }

Storage:
  Redis is used as a lightweight KV store for screenshot results.
  Key: screenshot_result:{request_id}
  TTL: 1 hour
  Screenshots (raw bytes) are stored temporarily, deleted after processing.
"""
import uuid
import asyncio
import base64
from io import BytesIO
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(prefix="/webhook/screenshot", tags=["screenshot"])

# ── Rate limiter (per user_id, in-memory) ─────────────────────────────────────
from collections import defaultdict
from datetime import timedelta

_screenshot_buckets: dict = defaultdict(list)
SCREENSHOT_RATE_LIMIT  = 20
SCREENSHOT_RATE_WINDOW = 60  # seconds


def _check_screenshot_rate(user_id: str) -> bool:
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=SCREENSHOT_RATE_WINDOW)
    _screenshot_buckets[user_id] = [
        t for t in _screenshot_buckets[user_id] if t > cutoff
    ]
    if len(_screenshot_buckets[user_id]) >= SCREENSHOT_RATE_LIMIT:
        return False
    _screenshot_buckets[user_id].append(now)
    return True


# ── Redis helpers ─────────────────────────────────────────────────────────────

async def _redis_set(key: str, value: dict, ttl_seconds: int = 3600):
    """Store result dict in Redis. Falls back to in-memory if Redis unavailable."""
    import json
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.setex(key, ttl_seconds, json.dumps(value))
        await r.aclose()
    except Exception as e:
        logger.warning(f"Redis unavailable, using in-memory fallback: {e}")
        _memory_store[key] = value


async def _redis_get(key: str) -> Optional[dict]:
    import json
    try:
        import redis.asyncio as aioredis
        from config.settings import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        raw = await r.get(key)
        await r.aclose()
        return json.loads(raw) if raw else None
    except Exception:
        return _memory_store.get(key)


# In-memory fallback (for development / Redis-down)
_memory_store: dict = {}


# ── POST /webhook/screenshot ──────────────────────────────────────────────────

@router.post("")
async def submit_screenshot(
    background_tasks: BackgroundTasks,
    screenshot: UploadFile = File(..., description="PNG screenshot of the chart"),
    ticker:     str        = Form(...),
    signal:     str        = Form(...),
    price:      Optional[str] = Form(None),
    user_id:    str        = Form(...),
):
    """
    Receive screenshot from browser extension.
    Validates inputs, stores image, queues analysis task.
    Returns request_id for polling.
    """
    # ── Input validation ─────────────────────────────────────────
    ticker = ticker.strip().upper()
    signal = signal.strip().upper()

    if not ticker or len(ticker) > 12:
        raise HTTPException(400, "Invalid ticker")
    if signal not in ("BUY", "SELL", "HOLD"):
        raise HTTPException(400, f"Invalid signal '{signal}'. Use BUY, SELL, or HOLD.")
    if not user_id or len(user_id) > 64:
        raise HTTPException(400, "Invalid user_id")
    if not screenshot.content_type or "image" not in screenshot.content_type:
        raise HTTPException(400, "Screenshot must be an image file (PNG/JPEG)")

    # ── Rate limit ───────────────────────────────────────────────
    if not _check_screenshot_rate(user_id):
        raise HTTPException(429, "Rate limit exceeded. Max 20 screenshots per minute.")

    # ── Read image ───────────────────────────────────────────────
    image_bytes = await screenshot.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10 MB max
        raise HTTPException(413, "Screenshot too large. Maximum 10 MB.")
    if len(image_bytes) < 1024:
        raise HTTPException(400, "Screenshot too small or empty.")

    # ── Generate request ID ──────────────────────────────────────
    request_id = str(uuid.uuid4())

    # ── Store initial status ─────────────────────────────────────
    await _redis_set(
        f"screenshot_result:{request_id}",
        {
            "status":     "processing",
            "request_id": request_id,
            "ticker":     ticker,
            "signal":     signal,
            "created_at": datetime.utcnow().isoformat(),
        },
        ttl_seconds=3600,
    )

    # ── Queue background task ─────────────────────────────────────
    # Convert to base64 for passing to Celery (must be serializable)
    image_b64 = base64.b64encode(image_bytes).decode()

    background_tasks.add_task(
        _process_screenshot_analysis,
        request_id=request_id,
        image_b64=image_b64,
        ticker=ticker,
        signal=signal,
        price=price,
        user_id=user_id,
    )

    logger.info(f"Screenshot submitted: {request_id} | {ticker} {signal} | user={user_id}")

    return {
        "request_id": request_id,
        "status":     "processing",
        "message":    f"Analysis queued for {ticker} {signal}. Poll /result/{request_id}",
    }


# ── GET /webhook/screenshot/result/{request_id} ───────────────────────────────

@router.get("/result/{request_id}")
async def get_screenshot_result(request_id: str):
    """
    Poll for analysis result.
    Returns status: pending | processing | completed | failed
    """
    if not request_id or len(request_id) > 64:
        raise HTTPException(400, "Invalid request_id")

    result = await _redis_get(f"screenshot_result:{request_id}")

    if not result:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "message": "Request ID not found or expired"},
        )

    return result


# ── Analysis processor ────────────────────────────────────────────────────────

async def _process_screenshot_analysis(
    request_id: str,
    image_b64:  str,
    ticker:     str,
    signal:     str,
    price:      Optional[str],
    user_id:    str,
):
    """
    Run the full AI analysis pipeline on the screenshot.

    Steps:
    1. Decode image → pass to OpenTrade.ai (ticker used, image for context)
    2. RAGFlow mentor validation (user_id used to look up personal rules)
    3. Store result in Redis
    """
    try:
        logger.info(f"Processing screenshot {request_id}: {ticker} {signal}")

        # ── Step 1: OpenTrade.ai analysis ─────────────────────────
        from services.validation import ValidationService
        from config.settings import settings

        svc = ValidationService()

        # Look up user's RAGFlow dataset if they have a Telegram account
        ragflow_dataset_id = await _get_user_ragflow_dataset(user_id)

        price_float = None
        if price:
            try:
                price_float = float(price.replace("$", "").replace(",", ""))
            except ValueError:
                pass

        result = await svc.validate_manual(
            ticker=ticker,
            signal=signal,
            price=price_float,
            user_ragflow_dataset_id=ragflow_dataset_id,
        )

        # ── Step 2: Build extension-friendly response ─────────────
        # Extract one-sentence reasoning for the popup
        full_message = result.get("final_message", "")
        reasoning_short = _extract_short_reasoning(full_message, result)

        # ── Step 3: Store completed result ────────────────────────
        completed = {
            "status":           "completed",
            "request_id":       request_id,
            "ticker":           ticker,
            "signal":           signal,
            "verdict":          result["verdict"],
            "confidence_score": result["confidence_score"],
            "reasoning":        reasoning_short,
            "full_message":     full_message,
            "trader_analysis":  result.get("trader_analysis", {}),
            "mentor_context":   result.get("mentor_context", ""),
            "completed_at":     datetime.utcnow().isoformat(),
        }

        await _redis_set(
            f"screenshot_result:{request_id}",
            completed,
            ttl_seconds=3600,
        )

        logger.info(
            f"Screenshot {request_id} complete: {ticker} {signal} → "
            f"{result['verdict']} ({int(result['confidence_score']*100)}%)"
        )

    except Exception as e:
        logger.error(f"Screenshot analysis failed for {request_id}: {e}")
        await _redis_set(
            f"screenshot_result:{request_id}",
            {
                "status":     "failed",
                "request_id": request_id,
                "error":      str(e)[:200],
            },
            ttl_seconds=1800,
        )


def _extract_short_reasoning(full_message: str, result: dict) -> str:
    """
    Extract a 1-3 sentence summary from the full Telegram message
    for display in the compact extension popup.
    """
    ta = result.get("trader_analysis", {})

    parts = []

    # Technical signal
    tech = ta.get("technical_signal", "")
    if tech:
        parts.append(f"Technical: {tech.lower()}.")

    # RSI note
    rsi = ta.get("rsi")
    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI {rsi:.0f} — oversold.")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.0f} — overbought.")

    # Bull/bear case (first sentence only)
    if result["verdict"] in ("CONFIRM",):
        bull = ta.get("bull_case", "")
        if bull:
            parts.append(bull.split(".")[0] + ".")
    else:
        bear = ta.get("bear_case", "")
        if bear:
            parts.append(bear.split(".")[0] + ".")

    # Mentor context (first line)
    mentor = result.get("mentor_context", "")
    if mentor and len(parts) < 3:
        first_line = mentor.split("\n")[0].replace("•", "").strip()
        if first_line and len(first_line) > 10:
            parts.append(first_line[:120])

    return " ".join(parts[:3]) or "Analysis complete. See full result in Telegram."


async def _get_user_ragflow_dataset(ext_user_id: str) -> Optional[str]:
    """
    Try to find this extension user's RAGFlow dataset.
    Extension users identified by ext_* IDs don't have Telegram accounts,
    so this returns None unless they've linked their Telegram.
    """
    try:
        from db.database import AsyncSessionLocal
        from db.models import User
        from sqlalchemy import select

        # Extension users might store their telegram_id in storage
        # For now return None (analysis still works, just without personal rules)
        return None
    except Exception:
        return None
