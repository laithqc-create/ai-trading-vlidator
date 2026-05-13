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
from miniapp.serve import router as miniapp_router
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

    # Set Telegram webhook only in production (APP_ENV=production)
    # In development, the polling bot handles updates instead
    # Only set webhook in production — dev uses polling bot instead
    if settings.APP_ENV == "production" and settings.TELEGRAM_WEBHOOK_URL:
        bot = get_bot()
        dp = get_dispatcher()
        await on_startup(bot, allow_network_failures=False)
        await bot.set_webhook(
            url=settings.TELEGRAM_WEBHOOK_URL,
            drop_pending_updates=True,
        )
        app.state.bot = bot
        app.state.dp = dp
        logger.info(f"Telegram webhook set: {settings.TELEGRAM_WEBHOOK_URL}")
    else:
        # Dev mode should keep the web app available even if Telegram is unreachable.
        logger.info("Development mode: skipping Telegram startup handshake for FastAPI.")

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

# Telegram Mini App
app.include_router(miniapp_router)


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-trade-validator"}


# ─── Mini App API ─────────────────────────────────────────────────────────────

@app.get("/api/user/stats")
async def api_user_stats(request: Request):
    """
    Return live stats for the Mini App hero section.
    Identifies user via X-Telegram-User-Id header (set by Mini App JS).
    Falls back to zeros if user not found.
    """
    telegram_id_str = request.headers.get("X-Telegram-User-Id", "")
    if not telegram_id_str or not telegram_id_str.isdigit():
        return {"validations": 0, "generations": 0, "accuracy": 0}

    telegram_id = int(telegram_id_str)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_telegram_id(telegram_id=telegram_id)
        if user is None:
            return {"validations": 0, "generations": 0, "accuracy": 0}

        # Count total validations from DB
        from sqlalchemy import func
        from db.models import Validation
        total_q = await db.execute(
            select(func.count()).where(Validation.user_id == user.id)
        )
        total_validations = total_q.scalar() or 0

        # Count wins for accuracy using user_outcome field
        wins_q = await db.execute(
            select(func.count()).where(
                Validation.user_id == user.id,
                Validation.user_outcome == "WIN",
            )
        )
        wins = wins_q.scalar() or 0
        accuracy = round((wins / total_validations * 100) if total_validations > 0 else 0)

        generations = user.total_generations or 0

    return {
        "validations": total_validations,
        "generations": generations,
        "accuracy": accuracy,
    }


@app.get("/api/user/plan")
async def api_user_plan(request: Request):
    """
    Return the user's current plan for the Mini App profile tab.
    Identifies user via X-Telegram-User-Id header.
    """
    telegram_id_str = request.headers.get("X-Telegram-User-Id", "")
    if not telegram_id_str or not telegram_id_str.isdigit():
        return {"plan": "free", "plan_label": "Free", "expires_at": None}

    telegram_id = int(telegram_id_str)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_telegram_id(telegram_id=telegram_id)
        if user is None:
            return {"plan": "free", "plan_label": "Free", "expires_at": None}

        plan_labels = {
            "free":     "Free",
            "product1": "Indicator Validator",
            "product2": "EA Analyzer",
            "product3": "Manual Validator",
            "pro":      "Pro Bundle",
        }
        expires = user.plan_expires_at.isoformat() if user.plan_expires_at else None
        plan_val   = user.plan.value
        plan_label = plan_labels.get(plan_val, "Free")

    return {
        "plan":       plan_val,
        "plan_label": plan_label,
        "expires_at": expires,
    }


@app.get("/api/integrations/indicator-webhook")
async def api_indicator_webhook_setup(request: Request, platform: str):
    """
    Return indicator webhook setup details for the Mini App.
    Identifies user via X-Telegram-User-Id header.
    """
    telegram_id_str = request.headers.get("X-Telegram-User-Id", "")
    if not telegram_id_str or not telegram_id_str.isdigit():
        raise HTTPException(401, "Missing Telegram user context")

    platform_key = platform.strip().lower()
    platform_labels = {
        "tradingview": "TradingView",
        "metatrader": "MetaTrader",
        "ctrader": "cTrader",
        "matchtrader": "MatchTrader",
        "daxtrader": "DAX Trader",
        "takeprofit": "TakeProfit.com",
    }
    if platform_key not in platform_labels:
        raise HTTPException(400, "Unsupported platform")

    telegram_id = int(telegram_id_str)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_user_by_telegram_id(telegram_id=telegram_id)
        if user is None:
            user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        has_access = user.plan in (PlanTier.PRODUCT1, PlanTier.PRO)
        if not has_access and not settings.is_production:
            has_access = True

        if not has_access:
            return {
                "ok": False,
                "requires_upgrade": True,
                "platform": platform_labels[platform_key],
                "message": "Webhook connection requires Indicator Validator or Pro.",
            }

        token = await user_svc.get_or_create_webhook_token(user, "indicator")
        base = settings.TELEGRAM_WEBHOOK_URL.rsplit("/webhook", 1)[0]
        webhook_url = f"{base}/webhook/indicator/{token}"

    example_payloads = {
        "tradingview": {
            "ticker": "{{ticker}}",
            "signal": "BUY",
            "price": "{{close}}",
            "indicator": "MyIndicator",
        },
        "metatrader": {
            "ticker": "EURUSD",
            "signal": "BUY",
            "price": 1.0845,
            "indicator": "MyIndicator",
            "timeframe": "H1",
            "logic": "Green arrow = BUY, Red arrow = SELL, Blue line = TP, Orange line = SL",
        },
        "ctrader": {
            "ticker": "EURUSD",
            "signal": "BUY",
            "price": 1.0845,
            "indicator": "MyIndicator",
        },
        "matchtrader": {
            "ticker": "EURUSD",
            "signal": "BUY",
            "price": 1.0845,
            "indicator": "MyIndicator",
        },
        "daxtrader": {
            "ticker": "EURUSD",
            "signal": "BUY",
            "price": 1.0845,
            "indicator": "MyIndicator",
        },
        "takeprofit": {
            "ticker": "EURUSD",
            "signal": "BUY",
            "price": 1.0845,
            "indicator": "MyIndicator",
            "timeframe": "H1",
            "logic": "Green arrow = BUY, Red arrow = SELL, Blue line = TP, Orange line = SL",
        },
    }

    mt4_link = (
        f'<a href="{settings.MT4_DOWNLOAD_URL}" target="_blank" rel="noopener noreferrer">MT4 (.ex4)</a>'
        if settings.MT4_DOWNLOAD_URL else
        "MT4 (.ex4)"
    )
    mt5_link = (
        f'<a href="{settings.MT5_DOWNLOAD_URL}" target="_blank" rel="noopener noreferrer">MT5 (.ex5)</a>'
        if settings.MT5_DOWNLOAD_URL else
        "MT5 (.ex5)"
    )

    platform_details = {
        "tradingview": {
            "asks": [
                "Generate webhook URL",
                "Alert message format with copyable JSON template",
            ],
            "actions": [
                "Copy your webhook URL.",
                "Go to TradingView, create an alert, and scroll to Webhook URL.",
                "Paste your webhook URL.",
                "Format the alert message as JSON using the template below.",
                "Save the alert.",
            ],
            "notes": [
                "TradingView will send POST requests to your endpoint whenever the alert fires.",
            ],
        },
        "metatrader": {
            "asks": [
                "Webhook URL",
                "Indicator screenshots",
                "Indicator logic description",
            ],
            "actions": [
                "Copy your special webhook URL.",
                "Upload screenshots from your indicator.",
                "Explain your indicator to the system.",
                f"Install the MetaTrader Expert Advisor: {mt4_link} or {mt5_link}.",
                "Attach the Expert Advisor to your chart.",
                "Go to Tools -> Options -> Expert Advisors, enable Allow automated trading, and enable Allow WebRequest for listed URLs.",
                f"Add this URL to the allowed list: {webhook_url}",
                "Right-click the chart -> Expert Advisors -> Properties -> Inputs, then set WebhookURL to your webhook URL and SignalDescription to: Green arrow = BUY, Red arrow = SELL, Blue line = TP, Orange line = SL.",
                "Choose the desired chart timeframe.",
                "Click OK.",
            ],
            "notes": [
                "MetaTrader uses WebRequest, so the webhook domain must be whitelisted before the EA can send alerts.",
                "If the MT4/MT5 labels are not clickable yet, add MT4_DOWNLOAD_URL and MT5_DOWNLOAD_URL to the environment.",
            ],
        },
        "ctrader": {
            "asks": [
                "Webhook URL",
                "cBot name to identify which bot is sending signals",
            ],
            "actions": [
                "Download our custom cBot (.cs file).",
                "Import it into cTrader.",
                "Enter your webhook URL in the cBot parameters.",
                "Attach the cBot to your chart.",
            ],
            "notes": [
                "For this use case, the cBot should send data to your webhook.",
                "The cBot still needs to be built and provided inside the product flow.",
                "On our end, the endpoint receives POST requests from the cBot.",
            ],
        },
        "matchtrader": {
            "asks": [
                "Webhook URL",
            ],
            "actions": [
                "Log into the MatchTrader dashboard.",
                "Go to Webhook settings.",
                "Enter your URL.",
                "Configure which events trigger the webhook.",
            ],
            "notes": [
                "MatchTrader sends POST requests to your endpoint whenever the selected events occur.",
            ],
        },
        "daxtrader": {
            "asks": [
                "Webhook URL",
            ],
            "actions": [
                "Log into the DAX Trader web platform.",
                "Go to Alert settings.",
                "Paste your webhook URL.",
            ],
            "notes": [
                "DAX Trader sends POST requests when alert conditions are met.",
            ],
        },
        "takeprofit": {
            "asks": [
                "Webhook URL",
                "Indicator logic description",
            ],
            "actions": [
                "Copy your webhook URL.",
                "Attach your indicator.",
                "Click the bell icon.",
                "Set the source to your indicator.",
                "Click Expand.",
                "Set frequency to Every Trigger.",
                "Paste your webhook URL into the Webhook field.",
                "Explain your indicator logic in the Message field using the recommended JSON format below.",
            ],
            "notes": [
                "TakeProfit.com sends a POST request to your webhook each time the alert is triggered.",
            ],
        },
    }

    return {
        "ok": True,
        "platform": platform_labels[platform_key],
        "webhook_url": webhook_url,
        "asks": platform_details[platform_key]["asks"],
        "actions": platform_details[platform_key]["actions"],
        "notes": platform_details[platform_key]["notes"],
        "example_payload": example_payloads[platform_key],
    }




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
