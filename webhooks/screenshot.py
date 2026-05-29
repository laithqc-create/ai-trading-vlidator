"""
webhooks/screenshot.py
Screenshot analysis endpoint — receives images from browser extension,
runs DeepSeek vision analysis, stores session for follow-up chat.

Endpoints:
  POST /webhook/screenshot/{token}  — receive screenshot, return analysis
  POST /api/chart/chat              — follow-up chat on a previous screenshot
  POST /api/news/analyze            — highlight text → historic impact analysis
  GET  /api/user/plan               — plan info for extension banner
  GET  /api/trial/status            — trial info for extension banner
"""
from __future__ import annotations
import base64, json, re, uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

router = APIRouter()

# In-memory screenshot session store (production: use Redis with TTL)
_screenshot_sessions: dict[str, dict] = {}


# ─── Screenshot receive + analyse ─────────────────────────────────────────────

@router.post("/webhook/screenshot/{token}")
async def receive_screenshot(
    token: str,
    request: Request,
    screenshot: UploadFile = File(...),
    symbol: str = Form(""),
    timeframe: str = Form("1h"),
    is_auto: str = Form("false"),
    chat_history: str = Form("[]"),
):
    """
    Called by the browser extension background.js on every candle close
    (auto-monitoring) or manual screenshot.

    Steps:
      1. Verify token → user
      2. Encode image to base64
      3. Send to DeepSeek vision with pattern rules context
      4. Store session (screenshot_id + image + analysis) for follow-up chat
      5. Return signal + reason + pattern
    """
    from db.database import AsyncSessionLocal
    from services.user import UserService
    from services.deepseek import DeepSeekService

    # Auth
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_webhook_token(token, "screenshot")
        if not user:
            raise HTTPException(401, "Invalid screenshot token")
        if not user.has_product_access(2) and not user.has_product_access(1):
            raise HTTPException(403, "Live Analysis requires an active plan or trial")

        personal_rules = await user_svc.get_personal_rules(user.id)
        telegram_id = user.telegram_id

    # Read and encode image
    img_bytes = await screenshot.read()
    if len(img_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Screenshot too large (max 10MB)")

    img_b64 = base64.b64encode(img_bytes).decode()

    # Build vision prompt
    rule_summary = (
        "\n".join(f"- {r.get('name','?')}: enabled={r.get('enabled', True)}" for r in personal_rules[:5])
        or "Using system defaults"
    )
    history = json.loads(chat_history) if chat_history else []

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert technical analyst. "
                "Analyse the provided chart screenshot and identify candle patterns.\n"
                "User rules:\n" + rule_summary + "\n\n"
                "Respond ONLY with valid JSON (no markdown):\n"
                '{"signal":"BUY|SELL|NEUTRAL","pattern":"pattern name","confidence":0.0,'
                '"reason":"2-3 sentences explaining the decision",'
                '"candles_used":["list the specific candles that formed the pattern"],'
                '"key_levels":[{"type":"support|resistance","approx_price":"description"}]}'
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
                {
                    "type": "text",
                    "text": f"Analyse this {timeframe} chart for {symbol or 'the instrument shown'}. "
                            "What is the signal and why?",
                },
            ],
        },
    ]

    # Call DeepSeek
    try:
        ds = DeepSeekService()
        raw = await ds.chat(messages, max_tokens=600)
        clean = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(clean)
    except json.JSONDecodeError:
        result = {
            "signal": "NEUTRAL",
            "pattern": "",
            "confidence": 0.0,
            "reason": raw[:400] if "raw" in dir() else "Analysis failed",
            "candles_used": [],
            "key_levels": [],
        }
    except Exception as e:
        logger.error(f"Screenshot analysis error: {e}")
        result = {
            "signal": "NEUTRAL", "pattern": "", "confidence": 0.0,
            "reason": str(e), "candles_used": [], "key_levels": [],
        }

    # Store session for follow-up chat
    session_id = str(uuid.uuid4())
    _screenshot_sessions[session_id] = {
        "img_b64": img_b64,
        "symbol": symbol,
        "timeframe": timeframe,
        "analysis": result,
        "telegram_id": telegram_id,
        "personal_rules": personal_rules,
        "history": history + [
            {"role": "assistant", "content": json.dumps(result)},
        ],
    }
    # Trim old sessions (keep last 200 in memory)
    if len(_screenshot_sessions) > 200:
        oldest = next(iter(_screenshot_sessions))
        del _screenshot_sessions[oldest]

    logger.info(
        f"Screenshot analysis: {symbol} {timeframe} → {result.get('signal')} "
        f"({result.get('pattern')}) for user {telegram_id}"
    )

    return {
        "ok": True,
        "screenshot_id": session_id,
        "signal": result.get("signal", "NEUTRAL"),
        "pattern": result.get("pattern", ""),
        "confidence": result.get("confidence", 0.0),
        "reason": result.get("reason", ""),
        "candles_used": result.get("candles_used", []),
        "key_levels": result.get("key_levels", []),
    }


