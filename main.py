"""
FastAPI Main Application

Webhook endpoints:
  POST /webhook/telegram         — Telegram bot updates
  POST /webhook/indicator/{token} — TradingView indicator signals (Product 1)
  POST /webhook/ea/{token}       — EA trade logs (Product 2)
  POST /webhook/stripe           — Stripe payment events

Health:
  GET  /health                   — Health check
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from config.settings import settings
from db.database import init_db, AsyncSessionLocal
from db.models import (
    User, Validation, EALog, ValidationStatus, SignalType, PlanTier
)
from services.user import UserService
from services.subscription import SubscriptionService, PLAN_TIER_MAP
from workers.tasks import validate_indicator_task, analyze_ea_task
from bot.handlers import create_bot_app
from sqlalchemy import select


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting AI Trade Validator...")
    await init_db()

    # Set Telegram webhook if URL is configured
    if settings.TELEGRAM_WEBHOOK_URL:
        bot_app = create_bot_app()
        await bot_app.bot.set_webhook(
            url=settings.TELEGRAM_WEBHOOK_URL,
            drop_pending_updates=True,
        )
        app.state.bot_app = bot_app
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


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-trade-validator"}


# ─── Telegram Webhook ─────────────────────────────────────────────────────────

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates and dispatch to python-telegram-bot."""
    try:
        body = await request.json()
        bot_app = getattr(request.app.state, "bot_app", None)
        if not bot_app:
            logger.warning("Bot app not initialized, creating inline")
            bot_app = create_bot_app()
            request.app.state.bot_app = bot_app

        from telegram import Update
        update = Update.de_json(body, bot_app.bot)
        await bot_app.process_update(update)
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

    EA sends JSON like:
    {"ea_name":"SuperScalper","ticker":"EURUSD","action":"BUY","result":"LOSS","pnl":-2.3}

    Only analyzes completed trades (WIN or LOSS), not open positions.
    """
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


# ─── Stripe Webhook ───────────────────────────────────────────────────────────

@app.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """Handle Stripe subscription events to update user plans."""
    body = await request.body()

    sub_svc = SubscriptionService()
    event = sub_svc.handle_webhook_event(body, stripe_signature or "")

    if not event:
        raise HTTPException(400, "Invalid Stripe webhook signature")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    logger.info(f"Stripe event: {event_type}")

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        await _handle_subscription_updated(data)

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_cancelled(data)

    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data)

    return {"received": True}


async def _handle_checkout_completed(session: dict):
    metadata = session.get("metadata", {})
    telegram_id = int(metadata.get("telegram_id", 0))
    plan = metadata.get("plan", "")

    if not telegram_id or not plan:
        return

    plan_tier = PLAN_TIER_MAP.get(plan)
    if not plan_tier:
        return

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        await user_svc.update_plan(
            telegram_id=telegram_id,
            plan=plan_tier,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
        )

    logger.info(f"User {telegram_id} upgraded to {plan}")

    # Notify user in Telegram
    from workers.celery_app import run_async
    from workers.tasks import _send_telegram_message
    plan_names = {
        "product1": "Indicator Validator ($29/mo)",
        "product2": "EA Analyzer ($49/mo)",
        "product3": "Manual Validator ($19/mo)",
        "pro": "Pro — All Products ($79/mo)",
    }
    await _send_telegram_message(
        telegram_id,
        f"🎉 *Subscription activated!*\n\n"
        f"Plan: *{plan_names.get(plan, plan)}*\n\n"
        f"You now have full access. Use /help to see all commands.",
    )


async def _handle_subscription_updated(subscription: dict):
    metadata = subscription.get("metadata", {})
    telegram_id = int(metadata.get("telegram_id", 0))
    plan = metadata.get("plan", "")
    if not telegram_id or not plan:
        return

    plan_tier = PLAN_TIER_MAP.get(plan, PlanTier.FREE)
    period_end = subscription.get("current_period_end")
    expires_at = datetime.fromtimestamp(period_end) if period_end else None

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        await user_svc.update_plan(
            telegram_id=telegram_id,
            plan=plan_tier,
            expires_at=expires_at,
        )


async def _handle_subscription_cancelled(subscription: dict):
    metadata = subscription.get("metadata", {})
    telegram_id = int(metadata.get("telegram_id", 0))
    if not telegram_id:
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        await user_svc.update_plan(telegram_id=telegram_id, plan=PlanTier.FREE)

    logger.info(f"User {telegram_id} downgraded to FREE (subscription cancelled)")

    from workers.tasks import _send_telegram_message
    await _send_telegram_message(
        telegram_id,
        "ℹ️ Your subscription has been cancelled. You've been moved to the free plan.\n\n"
        "Use /subscribe to re-subscribe anytime.",
    )


async def _handle_payment_failed(invoice: dict):
    customer_id = invoice.get("customer")
    if not customer_id:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user:
            from workers.tasks import _send_telegram_message
            await _send_telegram_message(
                user.telegram_id,
                "⚠️ *Payment failed* for your AI Trade Validator subscription.\n\n"
                "Please update your payment method to continue using premium features.\n"
                "Use /subscribe to manage your plan.",
            )
