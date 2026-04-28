"""
FastAPI Main Application

Webhook endpoints:
  POST /webhook/telegram         — Telegram bot updates
  POST /webhook/indicator/{token} — TradingView indicator signals (Product 1)
  POST /webhook/ea/{token}       — EA trade logs (Product 2)
  POST /webhook/whop             — Whop payment events

Health:
  GET  /health                   — Health check
"""
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from config.settings import settings
from db.database import init_db, AsyncSessionLocal
from db.models import (
    User, Validation, EALog, ValidationStatus, SignalType, PlanTier
)
from services.user import UserService
from services.subscription import WhopService, PLAN_TIER_MAP
from workers.tasks import validate_indicator_task, analyze_ea_task
from TG_Bot.main import get_bot, get_dispatcher, on_startup
from webhooks.screenshot import router as screenshot_router
from sqlalchemy import select


# ─── Webhook rate limiter (per token, in-memory) ──────────────────────────────
_webhook_buckets: dict = defaultdict(list)
WEBHOOK_RATE_LIMIT = 60      # max requests
WEBHOOK_RATE_WINDOW = 60     # per 60 seconds


def _check_webhook_rate(token: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=WEBHOOK_RATE_WINDOW)
    _webhook_buckets[token] = [t for t in _webhook_buckets[token] if t > cutoff]
    if len(_webhook_buckets[token]) >= WEBHOOK_RATE_LIMIT:
        return False
    _webhook_buckets[token].append(now)
    return True


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting AI Trade Validator...")
    await init_db()

    # Set Telegram webhook if URL is configured
    if settings.TELEGRAM_WEBHOOK_URL:
        bot = get_bot()
        dp  = get_dispatcher()
        await on_startup(bot)
        await bot.set_webhook(
            url=settings.TELEGRAM_WEBHOOK_URL,
            drop_pending_updates=True,
        )
        app.state.bot = bot
        app.state.dp  = dp
        logger.info(f"Telegram webhook set: {settings.TELEGRAM_WEBHOOK_URL}")

    logger.info("AI Trade Validator ready.")
    yield
    logger.info("Shutting down...")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Trade Validator",
    description="Telegram-based AI trading advisor",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Screenshot endpoint (browser extension)
app.include_router(screenshot_router)


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-trade-validator"}


# ─── Telegram Webhook ─────────────────────────────────────────────────────────

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates and dispatch to aiogram."""
    try:
        body = await request.json()
        bot = getattr(request.app.state, "bot", None)
        dp  = getattr(request.app.state, "dp", None)

        if not bot or not dp:
            bot = get_bot()
            dp  = get_dispatcher()
            request.app.state.bot = bot
            request.app.state.dp  = dp

        from aiogram.types import Update as AiogramUpdate
        update = AiogramUpdate.model_validate(body)
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"ok": False, "error": str(e)}


# ─── Product 1: Indicator Webhook ─────────────────────────────────────────────

class IndicatorPayload(BaseModel):
    ticker: str
    signal: str                      # BUY | SELL | HOLD
    price: Optional[float] = None
    indicator: Optional[str] = None  # indicator name/id
    extra: Optional[dict] = None     # any extra fields from TradingView


@app.post("/webhook/indicator/{token}")
async def indicator_webhook(
    token: str,
    payload: IndicatorPayload,
    background_tasks: BackgroundTasks,
):
    """
    Product 1: Receive TradingView indicator signal.

    TradingView sends JSON like:
    {"ticker": "AAPL", "signal": "BUY", "price": 175, "indicator": "RSI_oversold"}

    Returns 200 immediately; processing happens async in Celery.
    """
    # Rate limit: max 60 signals/min per token
    if not _check_webhook_rate(token):
        raise HTTPException(429, "Rate limit exceeded. Max 60 signals per minute.")

    signal_upper = payload.signal.upper()
    if signal_upper not in ("BUY", "SELL", "HOLD"):
        raise HTTPException(400, f"Invalid signal: {payload.signal}")

    ticker = payload.ticker.upper()

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_webhook_token(token, "indicator")

        if not user:
            raise HTTPException(401, "Invalid webhook token")

        if user.plan not in (PlanTier.PRODUCT1, PlanTier.PRO):
            logger.warning(f"User {user.telegram_id} sent indicator webhook but has plan={user.plan}")
            raise HTTPException(403, "Indicator Validator requires Product 1 or Pro plan")

        # Create validation record
        validation = Validation(
            user_id=user.id,
            product=1,
            ticker=ticker,
            signal=SignalType(signal_upper),
            price=payload.price,
            status=ValidationStatus.PENDING,
            source_payload=payload.dict(),
        )
        db.add(validation)
        await db.flush()
        validation_id = validation.id
        telegram_id = user.telegram_id
        ragflow_dataset_id = user.ragflow_dataset_id

    logger.info(f"Indicator webhook: {ticker} {signal_upper} for user {telegram_id}")

    # Queue async processing
    validate_indicator_task.delay(
        validation_id=validation_id,
        telegram_id=telegram_id,
        ticker=ticker,
        signal=signal_upper,
        price=payload.price,
        indicator_name=payload.indicator or "TradingView",
        ragflow_dataset_id=ragflow_dataset_id,
        extra_payload=payload.extra,
    )

    return {
        "ok": True,
        "message": f"Signal received for {ticker}. Analysis in progress.",
        "validation_id": validation_id,
    }


# ─── Product 2: EA Webhook ────────────────────────────────────────────────────

class EAPayload(BaseModel):
    ea_name: Optional[str] = "Unknown EA"
    ticker: str
    action: str                       # BUY | SELL
    result: Optional[str] = None      # WIN | LOSS | OPEN
    pnl: Optional[float] = None       # profit/loss percentage or points
    trade_time: Optional[str] = None  # ISO timestamp of trade
    extra: Optional[dict] = None


@app.post("/webhook/ea/{token}")
async def ea_webhook(
    token: str,
    payload: EAPayload,
):
    """
    Product 2: Receive EA trade log.
    Only analyzes completed trades (WIN or LOSS), not open positions.
    """
    if not _check_webhook_rate(token):
        raise HTTPException(429, "Rate limit exceeded. Max 60 requests per minute.")

    action_upper = payload.action.upper()
    if action_upper not in ("BUY", "SELL"):
        raise HTTPException(400, f"Invalid action: {payload.action}")

    # We only analyze completed trades
    result_upper = (payload.result or "").upper()

    ticker = payload.ticker.upper()

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_webhook_token(token, "ea")

        if not user:
            raise HTTPException(401, "Invalid webhook token")

        if user.plan not in (PlanTier.PRODUCT2, PlanTier.PRO):
            raise HTTPException(403, "EA Analyzer requires Product 2 or Pro plan")

        # Log the EA trade
        ea_log = EALog(
            user_id=user.id,
            ea_name=payload.ea_name,
            ticker=ticker,
            action=action_upper,
            result=result_upper if result_upper in ("WIN", "LOSS") else "OPEN",
            pnl=payload.pnl,
            trade_time=datetime.fromisoformat(payload.trade_time) if payload.trade_time else datetime.utcnow(),
            raw_payload=payload.dict(),
        )
        db.add(ea_log)

        # Only create full analysis for completed trades
        if result_upper not in ("WIN", "LOSS"):
            await db.flush()
            return {"ok": True, "message": "Open trade logged. Analysis triggered on close."}

        # Create validation record for completed trade
        validation = Validation(
            user_id=user.id,
            product=2,
            ticker=ticker,
            signal=SignalType(action_upper),
            status=ValidationStatus.PENDING,
            source_payload=payload.dict(),
        )
        db.add(validation)
        await db.flush()
        validation_id = validation.id
        ea_log.analysis_id = validation_id

        telegram_id = user.telegram_id
        ragflow_dataset_id = user.ragflow_dataset_id

    logger.info(f"EA webhook: {payload.ea_name} {action_upper} {ticker} → {result_upper}")

    # Queue EA analysis
    analyze_ea_task.delay(
        validation_id=validation_id,
        telegram_id=telegram_id,
        ticker=ticker,
        action=action_upper,
        result_outcome=result_upper,
        pnl=payload.pnl,
        ea_name=payload.ea_name or "Unknown EA",
        trade_time=payload.trade_time,
        ragflow_dataset_id=ragflow_dataset_id,
    )

    return {
        "ok": True,
        "message": f"EA trade logged. Analysis for {result_upper} trade in progress.",
        "validation_id": validation_id,
    }


# ─── Whop Webhook ────────────────────────────────────────────────────────────

@app.post("/webhook/whop")
async def whop_webhook(
    request: Request,
    whop_signature: Optional[str] = Header(None, alias="x-whop-signature"),
):
    """
    Handle Whop subscription events to update user plans.

    Whop events:
      subscription.created   — new subscriber
      subscription.cancelled — cancellation
      payment.succeeded      — renewal confirmed
      payment.failed         — payment issue
    """
    body = await request.body()

    # Verify HMAC signature
    whop = WhopService()
    if whop_signature and not whop.verify_webhook_signature(body, whop_signature):
        raise HTTPException(400, "Invalid Whop webhook signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    event = payload.get("event", "")
    data  = payload.get("data", {})

    logger.info(f"Whop event: {event}")

    if event == "subscription.created":
        await _whop_handle_created(data)

    elif event == "subscription.cancelled":
        await _whop_handle_cancelled(data)

    elif event == "payment.failed":
        await _whop_handle_payment_failed(data)

    return {"received": True}


async def _whop_handle_created(data: dict):
    """User subscribed — activate their plan."""
    metadata    = data.get("metadata", {})
    telegram_id = int(metadata.get("telegram_id", 0))
    plan_key    = metadata.get("plan", "")
    whop_uid    = data.get("user_id", "")
    member_id   = data.get("id", "")

    if not telegram_id or not plan_key:
        logger.warning(f"Whop subscription.created missing metadata: {data}")
        return

    plan_tier = PLAN_TIER_MAP.get(plan_key)
    if not plan_tier:
        logger.warning(f"Unknown Whop plan key: {plan_key}")
        return

    # Calculate expiry from renewal_period_end
    expires_ts  = data.get("renewal_period_end")
    expires_at  = datetime.fromtimestamp(expires_ts) if expires_ts else None

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        await user_svc.update_plan(
            telegram_id=telegram_id,
            plan=plan_tier,
            whop_user_id=whop_uid,
            whop_membership_id=member_id,
            expires_at=expires_at,
        )

    logger.info(f"User {telegram_id} activated plan={plan_key} via Whop")

    plan_names = {
        "product1": "Indicator Validator ($19/mo)",
        "product2": "EA Analyzer ($49/mo)",
        "product3": "Manual Validator ($19/mo)",
        "pro":      "Pro Bundle ($79/mo)",
    }
    from workers.tasks import _send_telegram_message
    await _send_telegram_message(
        telegram_id,
        f"🎉 *Subscription activated!*\n\n"
        f"Plan: *{plan_names.get(plan_key, plan_key)}*\n\n"
        f"You now have full access. Use /help to see all commands.",
    )


async def _whop_handle_cancelled(data: dict):
    """User cancelled — downgrade to FREE."""
    metadata    = data.get("metadata", {})
    telegram_id = int(metadata.get("telegram_id", 0))
    if not telegram_id:
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        await user_svc.update_plan(telegram_id=telegram_id, plan=PlanTier.FREE)

    logger.info(f"User {telegram_id} downgraded to FREE (Whop cancellation)")

    from workers.tasks import _send_telegram_message
    await _send_telegram_message(
        telegram_id,
        "ℹ️ Your subscription has been cancelled. Moved to free plan.\n\n"
        "Use /subscribe to re-subscribe anytime.",
    )


async def _whop_handle_payment_failed(data: dict):
    """Payment failed — warn user."""
    metadata    = data.get("metadata", {})
    telegram_id = int(metadata.get("telegram_id", 0))
    if not telegram_id:
        return

    from workers.tasks import _send_telegram_message
    await _send_telegram_message(
        telegram_id,
        "⚠️ *Payment failed* on your AI Trade Validator subscription.\n\n"
        "Please update your payment method on Whop to keep access.\n"
        "Use /subscribe to manage your plan.",
    )
