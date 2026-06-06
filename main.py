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
# ── Load .env / local_dev.env before anything else ───────────────────────────
import os as _os
from pathlib import Path as _Path
_root = _Path(__file__).parent
for _env_file in (_root / ".env", _root / "local_dev.env"):
    if _env_file.exists():
        try:
            from dotenv import load_dotenv as _load_dotenv
            _load_dotenv(_env_file, override=False)  # don't override already-set vars
        except ImportError:
            pass
        break
# ─────────────────────────────────────────────────────────────────────────────

import json
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from config.settings import settings
from db.database import init_db, AsyncSessionLocal
from db.models import (
    User, Validation, EALog, ValidationStatus, SignalType, PlanTier, AnalysisReport
)
from services.user import UserService
from services.subscription import WhopService, PLAN_TIER_MAP
from workers.tasks import validate_indicator_task, analyze_ea_task
from TG_Bot.main import get_bot, get_dispatcher, on_startup
from webhooks.screenshot import router as screenshot_router
from miniapp.serve import router as miniapp_router
from appbuilder.endpoints import router as appbuilder_router
from marketplace.endpoints import router as marketplace_router
from pattern_editor.endpoints import router as pattern_router
from webhooks.ohlc import router as ohlc_router
from sqlalchemy import select


# ─── Webhook rate limiter (per token, in-memory) ──────────────────────────────
_webhook_buckets: dict = defaultdict(list)
WEBHOOK_RATE_LIMIT = 60      # max requests
WEBHOOK_RATE_WINDOW = 60     # per 60 seconds


def _check_webhook_rate(token: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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

    # Register Telegram webhook whenever a webhook URL is configured.
    # If api.telegram.org is blocked regionally, skip gracefully.
    if settings.TELEGRAM_WEBHOOK_URL and settings.TELEGRAM_BOT_TOKEN:
        try:
            import httpx
            url = (
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
                f"/setWebhook?url={settings.TELEGRAM_WEBHOOK_URL}"
                f"&drop_pending_updates=true"
            )
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(url)
                data = r.json()
            if data.get("ok"):
                logger.info(f"✓ Telegram webhook set: {settings.TELEGRAM_WEBHOOK_URL}")
            else:
                logger.warning(f"Webhook set failed: {data}")
        except Exception as e:
            logger.info(
                f"Telegram webhook auto-registration skipped "
                f"({type(e).__name__} — likely regional restriction). "
                f"Webhook set via BotFather — bot will work normally."
            )
    else:
        logger.info("No webhook URL configured — skipping Telegram webhook registration.")

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

# Product 4 — App Builder
app.include_router(appbuilder_router)

# Marketplace
app.include_router(marketplace_router)

# Pattern rule editor
app.include_router(pattern_router)

# OHLC from MT4/MT5/cTrader bots
app.include_router(ohlc_router)




# ─── Bot / Extension Downloads ────────────────────────────────────────────────

@app.get("/api/download/{filename}")
async def download_bot_file(filename: str):
    """Serve bot files for download from the bots/ directory."""
    from fastapi.responses import FileResponse
    from pathlib import Path
    allowed = {
        "ATV_Analyzer.mq5": "bots/mt5/ATV_Analyzer.mq5",
        "ATV_Analyzer.mq4": "bots/mt4/ATV_Analyzer.mq4",
        "ATV_Analyzer.cs":  "bots/ctrader/ATV_Analyzer.cs",
        "extension.zip":    "miniapp/static/extension.zip",
    }
    if filename not in allowed:
        raise HTTPException(404, "File not found")
    path = Path(__file__).parent / allowed[filename]
    if not path.exists():
        raise HTTPException(404, "File not built yet")
    media = "application/zip" if filename.endswith(".zip") else "application/octet-stream"
    return FileResponse(path=str(path), filename=filename, media_type=media)

# ─── Root redirect → Mini App ─────────────────────────────────────────────────

@app.get("/")
async def root_redirect():
    """Redirect root to the Mini App."""
    return RedirectResponse(url="/app", status_code=302)


@app.get("/setup-webhook")
async def setup_webhook():
    """
    Manually register the Telegram webhook.
    Visit this URL in your browser after starting the server:
    http://localhost:8000/setup-webhook
    """
    if not settings.TELEGRAM_WEBHOOK_URL or not settings.TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_URL not set in .env"}
    try:
        import httpx
        url = (
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
            f"/setWebhook?url={settings.TELEGRAM_WEBHOOK_URL}"
            f"&drop_pending_updates=true"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            data = r.json()
        return {
            "ok": data.get("ok"),
            "webhook_url": settings.TELEGRAM_WEBHOOK_URL,
            "telegram_response": data,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


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

        has_access = user.has_product_access(1)
        if not has_access and not settings.is_production:
            has_access = True

        if not has_access:
            trial_used = user.trial_started_at is not None
            return {
                "ok": False,
                "requires_upgrade": True,
                "trial_available": not trial_used,
                "platform": platform_labels[platform_key],
                "message": "Webhook connection requires Indicator Validator, Pro, or active trial.",
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






# ─── Trial endpoints ──────────────────────────────────────────────────────────

@app.post("/api/trial/start")
async def api_trial_start(request: Request):
    """Start a 14-day free trial. Idempotent — safe to call multiple times."""
    tid = request.headers.get("X-Telegram-User-Id", "")
    if not tid.isdigit():
        raise HTTPException(401, "Missing Telegram user context")
    telegram_id = int(tid)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        status = await user_svc.get_trial_status(telegram_id)
        if status["used"]:
            return {
                "ok": False,
                "already_used": True,
                "message": "Trial already used. Subscribe to continue.",
                "active": status["active"],
                "days_remaining": status.get("days_remaining", 0),
            }
        user = await user_svc.start_trial(telegram_id)
        await db.commit()
        return {
            "ok": True,
            "message": f"14-day trial started! Full access until {user.trial_expires_at.strftime('%b %d, %Y')}.",
            "expires_at": user.trial_expires_at.isoformat(),
            "days_remaining": user.trial_days_remaining(),
        }


@app.get("/api/trial/status")
async def api_trial_status(request: Request):
    """Return trial status for the Mini App and extension trial banner."""
    tid = request.headers.get("X-Telegram-User-Id", "")
    if not tid.isdigit():
        return {"has_trial": False, "active": False, "days_remaining": 0, "used": False}
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        return await user_svc.get_trial_status(int(tid))


# ─── Checkout / purchase ──────────────────────────────────────────────────────

@app.get("/api/checkout/{plan}")
async def api_checkout_url(plan: str, request: Request):
    """
    Return the Whop checkout URL for a given plan with telegram_id injected.
    Called by Mini App and extension Upgrade buttons.
    plan: product1 | product2 | product3 | pro
    """
    tid = request.headers.get("X-Telegram-User-Id", "0")
    telegram_id = int(tid) if tid.isdigit() else 0

    plan_urls = {
        "product1": getattr(settings, "WHOP_PRODUCT1_URL", ""),
        "product2": getattr(settings, "WHOP_PRODUCT2_URL", ""),
        "product3": getattr(settings, "WHOP_PRODUCT3_URL", ""),
        "pro":      getattr(settings, "WHOP_PRO_URL", ""),
    }
    base = plan_urls.get(plan, "")
    if not base:
        raise HTTPException(400, f"Unknown plan or checkout URL not configured: {plan}")

    sep = "&" if "?" in base else "?"
    checkout_url = f"{base}{sep}metadata[telegram_id]={telegram_id}"
    affiliate_url = getattr(settings, "WHOP_AFFILIATE_URL", "") or None

    return {"ok": True, "plan": plan, "checkout_url": checkout_url, "affiliate_url": affiliate_url}


# ─── User tokens ──────────────────────────────────────────────────────────────

@app.get("/api/user/tokens")
async def api_user_tokens(request: Request):
    """Return all three webhook tokens for the Mini App profile tab."""
    tid = request.headers.get("X-Telegram-User-Id", "")
    if not tid.isdigit():
        raise HTTPException(401, "Missing Telegram user context")
    telegram_id = int(tid)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        tokens = await user_svc.ensure_all_webhook_tokens(user.id)
        await db.commit()
    return {
        "ok": True,
        "indicator":  tokens["indicator"],
        "ea":         tokens["ea"],
        "screenshot": tokens["screenshot"],
    }


# ─── Chart chat ───────────────────────────────────────────────────────────────

class ChartChatRequest(BaseModel):
    message: str
    screenshot_id: Optional[str] = None
    history: Optional[list] = []
    token: Optional[str] = None


@app.post("/api/chart/chat")
async def api_chart_chat(req: ChartChatRequest, request: Request):
    """
    Follow-up chat on a previously analysed screenshot.
    Detects rule-override phrases and saves them as personal rules.
    """
    tid = request.headers.get("X-Telegram-User-Id", "")
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = None
        if req.token:
            user = await user_svc.get_user_by_webhook_token(req.token, "screenshot")
        if user is None and tid.isdigit():
            user = await user_svc.get_user_by_telegram_id(int(tid))
        if user is None:
            raise HTTPException(401, "Unrecognized user")
        if not user.has_product_access(2):
            raise HTTPException(403, "Live chart analysis requires Product 2, Pro, or active trial")

        # Detect rule-override intent
        triggers = ["use this rule", "follow this rule", "only buy when", "only sell when",
                    "from now on", "use rule:", "new rule:"]
        msg_lower = req.message.lower()
        rule_saved = False
        for t in triggers:
            if t in msg_lower:
                await user_svc.add_personal_rule(user.id, req.message.strip())
                await db.commit()
                rule_saved = True
                break

        user_id = user.id

    from services.deepseek import DeepSeekService
    ds = DeepSeekService()
    system_msg = (
        "You are an expert technical analyst helping a trader understand a chart analysis. "
        "Answer clearly and concisely. If the user asks to use a specific rule, acknowledge it."
    )
    if rule_saved:
        system_msg += f" Note: user added a new rule: '{req.message[:100]}'"

    messages = [{"role": "system", "content": system_msg}]
    for h in (req.history or []):
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    reply = await ds.chat(messages)
    return {"ok": True, "reply": reply, "rule_saved": rule_saved}


# ─── News impact analysis ─────────────────────────────────────────────────────

class NewsAnalysisRequest(BaseModel):
    text: str
    symbol: str
    token: Optional[str] = None


@app.post("/api/news/analyze")
async def api_news_analyze(req: NewsAnalysisRequest, request: Request):
    """
    Analyse historical price impact of a news event on a symbol.
    Called from browser extension news highlighter.
    """
    tid = request.headers.get("X-Telegram-User-Id", "")
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = None
        if req.token:
            user = await user_svc.get_user_by_webhook_token(req.token, "screenshot")
        if user is None and tid.isdigit():
            user = await user_svc.get_user_by_telegram_id(int(tid))
        if user is None:
            raise HTTPException(401, "Unrecognized user")
        if not user.has_product_access(2):
            raise HTTPException(403, "News analysis requires Product 2, Pro, or active trial")

    if len(req.text.strip()) < 10:
        raise HTTPException(400, "News text too short")

    symbol = req.symbol.upper()

    # Try to fetch recent price data for context
    price_context = ""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y", interval="1d")
        if not hist.empty:
            recent = hist.tail(5)
            price_context = f"Recent closes for {symbol}: " + ", ".join(
                f"{row.name.strftime('%Y-%m-%d')}={row['Close']:.4f}"
                for _, row in recent.iterrows()
            )
    except Exception:
        price_context = f"No price data available for {symbol}."

    from services.deepseek import DeepSeekService
    ds = DeepSeekService()

    prompt = (
        "You are a professional market analyst. A trader highlighted this news:\n"
        + f'"\"{req.text[:500]}\"\n\n"'
        + f"Symbol: {symbol}\n{price_context}\n\n"
        + "1. Identify the news theme (rate decision, employment data, geopolitical, etc.)\n"
        + f"2. Explain how similar past news typically affected {symbol}\n"
        + "3. State the typical directional bias and timeframe\n"
        + "4. Note important caveats\n\n"
        + "Be specific and professional. Reference real historical patterns."
    )

    analysis = await ds.chat([
        {"role": "system", "content": "You are an expert market analyst. Give precise evidence-based analysis."},
        {"role": "user",   "content": prompt},
    ])

    return {"ok": True, "symbol": symbol, "analysis": analysis, "news_excerpt": req.text[:200]}


# ─── Plan access gating helper used by route handlers ────────────────────────

def _require_plan_access(user: User, product_num: int, trial_ok: bool = True):
    """Raise 403 if user does not have access to the product."""
    if trial_ok and user.has_product_access(product_num):
        return
    plan_names = {1: "Indicator Validator", 2: "EA Analyzer / Live Analysis", 3: "Live Analysis"}
    raise HTTPException(
        403,
        f"{plan_names.get(product_num, 'this product')} requires a paid plan or active trial."
    )


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

        if not user.has_product_access(1):
            logger.warning(f"User {user.telegram_id} sent indicator webhook but has plan={user.plan}")
            raise HTTPException(403, "Indicator Validator requires Product 1, Pro, or active trial")

        # Create validation record
        validation = Validation(
            user_id=user.id,
            product=1,
            ticker=ticker,
            signal=SignalType(signal_upper),
            price=payload.price,
            status=ValidationStatus.PENDING,
            source_payload=payload.model_dump(),
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

        if not user.has_product_access(2):
            raise HTTPException(403, "EA Analyzer requires Product 2, Pro, or active trial")

        # Log the EA trade
        ea_log = EALog(
            user_id=user.id,
            ea_name=payload.ea_name,
            ticker=ticker,
            action=action_upper,
            result=result_upper if result_upper in ("WIN", "LOSS") else "OPEN",
            pnl=payload.pnl,
            trade_time=datetime.fromisoformat(payload.trade_time) if payload.trade_time else datetime.now(timezone.utc).replace(tzinfo=None),
            raw_payload=payload.model_dump(),
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
            source_payload=payload.model_dump(),
        )
        db.add(validation)
        await db.flush()
        validation_id = validation.id
        ea_log.analysis_id = validation_id

        telegram_id = user.telegram_id
        ragflow_dataset_id = user.ragflow_dataset_id

    logger.info(f"EA webhook: {payload.ea_name} {action_upper} {ticker} → {result_upper}")

    # If candles provided, run full OHLC analysis immediately
    candles = payload.model_dump().get("candles") or []
    if candles:
        from services.indicator_engine import IndicatorEngine
        from services.pattern_engine import PatternEngine
        from services.report_formatter import format_ea_trade_report, format_telegram_report

        async with AsyncSessionLocal() as db2:
            user_svc2 = UserService(db2)
            user2 = await user_svc2.get_user_by_webhook_token(token, "ea")
            personal_rules = await user_svc2.get_personal_rules(user2.id)
            enabled_inds   = await user_svc2.get_enabled_indicators(user2.id)
            ind_settings   = await user_svc2.get_indicator_settings(user2.id)

        patterns   = PatternEngine().detect(candles, personal_rules)
        ind_report = IndicatorEngine().calculate_for_report(candles, enabled=enabled_inds, user_settings=ind_settings)

        from services.deepseek import DeepSeekService
        ds = DeepSeekService()
        flat_ind = {n: d["value"] for g in ind_report.get("groups",{}).values() for n,d in g.items() if d.get("value")}
        ai = await ds.analyze_ohlc(
            symbol=ticker, timeframe=payload.model_dump().get("timeframe","1h"),
            candles=candles[-20:], indicators=flat_ind,
            detected_patterns=patterns, personal_rules=personal_rules,
            trade_context={"direction": action_upper.lower(),
                           "price": payload.pnl,
                           "event": "sl" if result_upper=="LOSS" else "tp" if result_upper=="WIN" else "open"},
        )
        raw_report = {
            "symbol": ticker, "timeframe": payload.model_dump().get("timeframe","1h"),
            "source": "ea", "signal": ai.get("signal","NEUTRAL"),
            "pattern": ai.get("pattern",""), "reason": ai.get("reason",""),
            "confidence": round(ai.get("confidence",0)*100),
            "patterns": patterns, "indicators": ind_report,
            "levels": ai.get("levels",[]),
            "trade": {
                "direction": action_upper.lower(),
                "price": payload.pnl, "event": result_upper.lower(),
                "verdict": ai.get("trade_verdict",""),
                "why_entry": ai.get("why_entry",""),
                "why_result": ai.get("why_result",""),
            }
        }
        ea_report   = format_ea_trade_report(raw_report)
        tg_message  = format_telegram_report(raw_report, raw_report.get("trade"))

        # Send Telegram message
        try:
            await bot.send_message(chat_id=telegram_id, text=tg_message, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"EA Telegram send failed: {e}")

        return {
            "ok": True,
            "message": "EA trade analysed.",
            "validation_id": validation_id,
            "report": ea_report,
        }

    # No candles — queue background analysis
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

    # subscription.created / membership.went_valid → activate plan
    if event in ("subscription.created", "membership.went_valid"):
        await _whop_handle_created(data)
        await _whop_handle_marketplace_activated(data)

    # subscription.cancelled / membership.was_cancelled → deactivate
    elif event in ("subscription.cancelled", "membership.was_cancelled"):
        await _whop_handle_cancelled(data)
        await _whop_handle_marketplace_deactivated(data)

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


# ─── Marketplace purchase handlers (Whop membership events) ──────────────────

async def _whop_handle_marketplace_activated(data: dict):
    """
    membership.went_valid — a user's marketplace purchase/rental became active.
    Creates a MarketplacePurchase row if one doesn't exist yet, or sets active=True.
    metadata must contain: listing_id, telegram_id, listing_type (sell|rent|free)
    """
    whop_membership_id = data.get("id", "")
    metadata           = data.get("metadata", {})
    listing_id         = metadata.get("listing_id", "")
    telegram_id_str    = metadata.get("telegram_id", "0")
    listing_type_str   = metadata.get("listing_type", "sell")
    amount             = float(data.get("checkout_total_amount", 0) or 0) / 100  # cents → dollars

    if not whop_membership_id:
        return

    from db.models_marketplace import MarketplacePurchase, ListingType, MarketplaceListing
    from sqlalchemy import update as sa_update, select as sa_select
    from datetime import datetime, timedelta
    import uuid

    async with AsyncSessionLocal() as db:
        # Check if purchase row already exists
        res = await db.execute(
            sa_select(MarketplacePurchase)
            .where(MarketplacePurchase.whop_membership_id == whop_membership_id)
        )
        existing = res.scalar_one_or_none()

        if existing:
            existing.active = True
            await db.commit()
        elif listing_id and telegram_id_str.isdigit():
            telegram_id = int(telegram_id_str)
            # Resolve buyer user_id
            user_svc = UserService(db)
            buyer = await user_svc.get_or_create_user(telegram_id=telegram_id)

            try:
                listing_uuid = uuid.UUID(listing_id)
            except ValueError:
                logger.warning(f"Invalid listing_id in Whop metadata: {listing_id}")
                return

            try:
                lt = ListingType(listing_type_str)
            except ValueError:
                lt = ListingType.SELL

            # Set expiry for rentals (30 days default)
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30) if lt == ListingType.RENT else None

            purchase = MarketplacePurchase(
                listing_id=listing_uuid,
                buyer_user_id=buyer.id,
                listing_type=lt,
                amount_paid_usd=amount,
                whop_membership_id=whop_membership_id,
                active=True,
                expires_at=expires_at,
            )
            db.add(purchase)

            # Increment listing purchase count
            listing_res = await db.execute(
                sa_select(MarketplaceListing).where(MarketplaceListing.id == listing_uuid)
            )
            listing = listing_res.scalar_one_or_none()
            if listing:
                listing.purchases = (listing.purchases or 0) + 1

            await db.commit()
            logger.info(f"Marketplace purchase created: listing={listing_id} buyer={telegram_id}")

            # Notify buyer via Telegram
            try:
                from workers.tasks import _send_telegram_message
                await _send_telegram_message(
                    telegram_id,
                    f"🎉 *Purchase confirmed!*\n\n"
                    f"You now have access to your purchased app.\n"
                    f"Find it in the Marketplace → My Purchases tab.",
                )
            except Exception as e:
                logger.warning(f"Purchase Telegram notify failed: {e}")
            return

    logger.info(f"Marketplace activated: whop_membership_id={whop_membership_id}")


async def _whop_handle_marketplace_deactivated(data: dict):
    """
    membership.was_cancelled — a user's marketplace purchase/rental was cancelled.
    Updates the corresponding MarketplacePurchase row to active=False.
    """
    whop_membership_id = data.get("id", "")
    if not whop_membership_id:
        return

    from db.models_marketplace import MarketplacePurchase
    from sqlalchemy import update as sa_update

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(MarketplacePurchase)
            .where(MarketplacePurchase.whop_membership_id == whop_membership_id)
            .values(active=False)
        )
        await db.commit()

    logger.info(f"Marketplace purchase deactivated: whop_membership_id={whop_membership_id}")


# ─── EA + Validation history endpoints (Product 2 + 3 result screens) ─────────

@app.get("/api/ea/history")
async def ea_history(request: Request, limit: int = 20):
    """
    Returns the user's recent EA trade analyses.
    Called by the mini app Product 2 (EA Analyser) results screen.
    """
    tid_str = request.headers.get("X-Telegram-User-Id", "")
    if not tid_str:
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    tid = int(tid_str)

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(tid)

        from sqlalchemy import desc
        result = await db.execute(
            select(EALog)
            .where(EALog.user_id == user.id)
            .order_by(desc(EALog.created_at))
            .limit(min(limit, 50))
        )
        logs = result.scalars().all()

        # For each EALog, fetch the linked Validation analysis if available
        rows = []
        for log in logs:
            analysis_text = None
            patterns = []
            if log.analysis_id:
                v_result = await db.execute(
                    select(Validation).where(Validation.id == log.analysis_id)
                )
                v = v_result.scalar_one_or_none()
                if v:
                    analysis_text = v.final_message
                    patterns = (v.trader_analysis or {}).get("patterns", [])

            rows.append({
                "id": log.id,
                "ea_name": log.ea_name or "EA",
                "ticker": log.ticker,
                "action": log.action,
                "result": log.result or "OPEN",
                "pnl": log.pnl,
                "trade_time": log.trade_time.isoformat() if log.trade_time else None,
                "analysis": analysis_text,
                "patterns": patterns,
                "created_at": log.created_at.isoformat(),
            })

    return {"ok": True, "trades": rows, "total": len(rows)}


@app.get("/api/validations/history")
async def validation_history(request: Request, limit: int = 20):
    """
    Returns the user's recent indicator validations.
    Called by the mini app Product 1 history screen.
    """
    tid_str = request.headers.get("X-Telegram-User-Id", "")
    if not tid_str:
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    tid = int(tid_str)

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(tid)

        from sqlalchemy import desc
        result = await db.execute(
            select(Validation)
            .where(Validation.user_id == user.id, Validation.product == 1)
            .order_by(desc(Validation.created_at))
            .limit(min(limit, 50))
        )
        validations = result.scalars().all()

    rows = []
    for v in validations:
        rows.append({
            "id": v.id,
            "ticker": v.ticker,
            "signal": v.signal.value if v.signal else None,
            "price": v.price,
            "status": v.status.value,
            "verdict": v.verdict,
            "confidence": v.confidence_score,
            "reason": v.final_message,
            "patterns": (v.trader_analysis or {}).get("patterns", []),
            "created_at": v.created_at.isoformat(),
        })

    return {"ok": True, "validations": rows, "total": len(rows)}


# ─── Analysis report endpoints ───────────────────────────────────────────────

@app.get("/api/user/last-report")
async def last_report(request: Request, source: str = "indicator"):
    """
    Returns the most recent analysis report for the user by source.
    source: indicator | ea | extension
    Called by Mini App report tabs (loadSVReport, loadEAReport).
    """
    tid_str = request.headers.get("X-Telegram-User-Id", "")
    if not tid_str:
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    tid = int(tid_str)

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(tid)

        from sqlalchemy import desc
        result = await db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user.id, AnalysisReport.source == source)
            .order_by(desc(AnalysisReport.created_at))
            .limit(1)
        )
        row = result.scalars().first()

    if not row:
        return {"ok": True, "report": None}

    return {
        "ok": True,
        "report": row.report,
        "symbol": row.symbol,
        "timeframe": row.timeframe,
        "created_at": row.created_at.isoformat(),
    }


@app.get("/api/user/reports")
async def user_reports(request: Request, source: str = "ea", limit: int = 10):
    """
    Returns paginated analysis reports for the user by source.
    Called by Mini App EA history tab (loadEAHistory).
    """
    tid_str = request.headers.get("X-Telegram-User-Id", "")
    if not tid_str:
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    tid = int(tid_str)

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(tid)

        from sqlalchemy import desc
        result = await db.execute(
            select(AnalysisReport)
            .where(AnalysisReport.user_id == user.id, AnalysisReport.source == source)
            .order_by(desc(AnalysisReport.created_at))
            .limit(min(limit, 50))
        )
        rows = result.scalars().all()

    reports = [
        {
            "id": r.id,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "source": r.source,
            "report": r.report,
            "created_at": r.created_at.isoformat(),
            # Convenience fields surfaced from the report dict
            "signal": (r.report or {}).get("signal"),
            "trade": (r.report or {}).get("trade"),
        }
        for r in rows
    ]

    return {"ok": True, "reports": reports, "total": len(reports)}


# ─── Affiliate link ───────────────────────────────────────────────────────────

@app.get("/api/affiliate/link")
async def affiliate_link(request: Request):
    """Returns the Whop affiliate URL with telegram_id metadata."""
    tid = request.headers.get("X-Telegram-User-Id", "")
    from config.settings import settings
    base = settings.WHOP_AFFILIATE_URL or "https://whop.com/affiliate"
    url = f"{base}?ref={tid}" if tid else base
    return {"url": url}
