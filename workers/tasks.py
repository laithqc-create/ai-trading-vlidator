"""
workers/tasks.py
Real Celery tasks for all async processing.

Tasks:
  validate_indicator_task  — Product 1: analyse indicator signal, notify user via Telegram
  analyze_ea_task          — Product 2: analyse EA trade (why entry/exit), notify user
  _send_telegram_message   — helper for bot notifications
"""
from workers.celery_app import celery_app, run_async
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# ── Telegram helper ───────────────────────────────────────────────────────────

async def _send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a Telegram message using the configured bot token."""
    try:
        import httpx
        from config.settings import settings
        token = settings.TELEGRAM_BOT_TOKEN
        if not token or token == "placeholder":
            logger.debug(f"[TG] Would send to {chat_id}: {text[:80]}")
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            })
    except Exception as e:
        logger.warning(f"Telegram notify failed for {chat_id}: {e}")


# ── Product 1: Indicator Validator ────────────────────────────────────────────

@celery_app.task(name="tasks.validate_indicator_task", bind=True, max_retries=2)
def validate_indicator_task(
    self,
    validation_id: int,
    telegram_id: int,
    ticker: str,
    signal: str,
    price: float,
    indicator_name: str = "TradingView",
    ragflow_dataset_id: str = None,
    extra_payload: dict = None,
    **kwargs,
):
    """
    Product 1 — Validate an indicator signal.

    Flow:
      1. Load user's personal pattern rules from DB
      2. Fetch market data via Polygon (optional — fallback to DB candles)
      3. Run pattern engine on recent candles
      4. Send everything to DeepSeek for a final verdict
      5. Update Validation row in DB
      6. Notify user via Telegram
    """
    run_async(_validate_indicator_async(
        validation_id=validation_id,
        telegram_id=telegram_id,
        ticker=ticker,
        signal=signal,
        price=price,
        indicator_name=indicator_name,
        ragflow_dataset_id=ragflow_dataset_id,
    ))


async def _validate_indicator_async(
    validation_id: int,
    telegram_id: int,
    ticker: str,
    signal: str,
    price: float,
    indicator_name: str,
    ragflow_dataset_id: str,
):
    from db.database import AsyncSessionLocal
    from db.models import Validation, ValidationStatus, SignalType
    from services.user import UserService
    from services.validation_service import ValidationService
    from services.market_data import PolygonService
    from sqlalchemy import select

    logger.info(f"[P1] Validating {ticker} {signal} for user {telegram_id}")

    async with AsyncSessionLocal() as db:
        # Load validation record
        result = await db.execute(select(Validation).where(Validation.id == validation_id))
        validation = result.scalar_one_or_none()
        if not validation:
            logger.warning(f"[P1] Validation {validation_id} not found")
            return

        # Update to PROCESSING
        validation.status = ValidationStatus.PROCESSING
        await db.commit()

        # Load user's personal rules
        user_svc = UserService(db)
        personal_rules = await user_svc.get_personal_rules(validation.user_id)

    # Run validation (market data → pattern engine → DeepSeek)
    try:
        polygon = PolygonService()
        svc = ValidationService(polygon=polygon)
        verdict = await svc.validate_signal(
            ticker=ticker,
            signal=signal,
            price=price or 0.0,
            personal_rules=personal_rules,
        )
    except Exception as e:
        logger.error(f"[P1] Validation error for {ticker}: {e}")
        verdict = {
            "verdict": "NEUTRAL",
            "confidence": 0.0,
            "patterns": [],
            "reason": f"Analysis error: {e}",
        }

    # Build Telegram notification
    emoji = {"CONFIRMED": "✅", "REJECTED": "❌", "NEUTRAL": "⚠️"}.get(verdict["verdict"], "⚠️")
    patterns_str = ", ".join(verdict["patterns"]) if verdict["patterns"] else "none detected"
    price_str = f" @ ${price:.4f}" if price else ""

    msg = (
        f"{emoji} *{verdict['verdict']}* — {indicator_name} signal\n\n"
        f"*{ticker}* {signal}{price_str}\n"
        f"Confidence: {verdict['confidence']:.0%}\n"
        f"Patterns: {patterns_str}\n\n"
        f"_{verdict['reason']}_\n\n"
        f"_This is an analytical tool only. Not financial advice._"
    )

    # Update DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Validation).where(Validation.id == validation_id))
        validation = result.scalar_one_or_none()
        if validation:
            validation.status = ValidationStatus.COMPLETED
            validation.verdict = verdict["verdict"]
            validation.confidence_score = verdict["confidence"]
            validation.final_message = verdict["reason"]
            validation.trader_analysis = {"patterns": verdict["patterns"]}
            await db.commit()

    await _send_telegram_message(telegram_id, msg)
    logger.info(f"[P1] Done: {ticker} {signal} → {verdict['verdict']} ({verdict['confidence']:.0%})")


# ── Product 2: EA Trade Analyser ──────────────────────────────────────────────

@celery_app.task(name="tasks.analyze_ea_task", bind=True, max_retries=2)
def analyze_ea_task(
    self,
    validation_id: int,
    telegram_id: int,
    ticker: str,
    action: str,
    result_outcome: str = None,
    pnl: float = None,
    ea_name: str = "EA",
    trade_time: str = None,
    ragflow_dataset_id: str = None,
    **kwargs,
):
    """
    Product 2 — Analyse an EA trade.

    Tells user: why the EA entered, what the market conditions were,
    why it won or lost, and suggestions for improvement.
    """
    run_async(_analyze_ea_async(
        validation_id=validation_id,
        telegram_id=telegram_id,
        ticker=ticker,
        action=action,
        result_outcome=result_outcome,
        pnl=pnl,
        ea_name=ea_name,
        trade_time=trade_time,
    ))


async def _analyze_ea_async(
    validation_id: int,
    telegram_id: int,
    ticker: str,
    action: str,
    result_outcome: str,
    pnl: float,
    ea_name: str,
    trade_time: str,
):
    from db.database import AsyncSessionLocal
    from db.models import Validation, ValidationStatus
    from services.user import UserService
    from services.deepseek import DeepSeekService
    from services.market_data import PolygonService
    from services.pattern_engine import PatternEngine
    from sqlalchemy import select

    logger.info(f"[P2] Analysing EA trade: {ea_name} {ticker} {action} → {result_outcome}")

    # Fetch recent candles for context
    bars = []
    try:
        polygon = PolygonService()
        bars = await polygon.get_bars(ticker, timespan="day", limit=20)
    except Exception as e:
        logger.warning(f"[P2] Could not fetch market data for {ticker}: {e}")

    # Detect patterns at trade time
    patterns = []
    if bars:
        engine = PatternEngine()
        candles = [{"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in bars]
        patterns = engine.detect(candles)

    # Build DeepSeek prompt
    pattern_str = ", ".join(p["name"] for p in patterns) if patterns else "none detected"
    result_str = result_outcome or "OPEN"
    pnl_str = f"PnL: {pnl:+.2f}" if pnl is not None else "PnL: unknown"
    time_str = f" at {trade_time}" if trade_time else ""

    prompt = (
        f"An Expert Advisor ({ea_name}) placed a {action} trade on {ticker}{time_str}.\n"
        f"Result: {result_str}. {pnl_str}\n"
        f"Candle patterns at trade time: {pattern_str}\n\n"
        f"Analyse in 3 short sections:\n"
        f"1. WHY ENTERED: What market conditions likely triggered this {action} trade.\n"
        f"2. WHY {result_str}: What caused this outcome based on the patterns and conditions.\n"
        f"3. SUGGESTION: One specific parameter or condition to improve this EA.\n\n"
        f"Keep each section to 2-3 sentences. Be technical and specific."
    )

    analysis = ""
    try:
        ds = DeepSeekService()
        analysis = await ds.chat([
            {"role": "system", "content": "You are an expert algorithmic trading analyst. Be concise and technical."},
            {"role": "user", "content": prompt},
        ], max_tokens=500)
    except Exception as e:
        logger.error(f"[P2] DeepSeek error: {e}")
        analysis = f"Analysis unavailable: {e}"

    # Telegram message
    outcome_emoji = {"WIN": "🟢", "LOSS": "🔴", "OPEN": "🔵"}.get(result_str, "⚪")
    pnl_display = f" ({pnl:+.2f})" if pnl is not None else ""

    msg = (
        f"{outcome_emoji} *EA Trade Analysis* — {ea_name}\n\n"
        f"*{ticker}* {action} → *{result_str}*{pnl_display}\n"
        f"Patterns: {pattern_str}\n\n"
        f"{analysis}\n\n"
        f"_Analytical tool only. Not financial advice._"
    )

    # Update DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Validation).where(Validation.id == validation_id))
        validation = result.scalar_one_or_none()
        if validation:
            validation.status = ValidationStatus.COMPLETED
            validation.final_message = analysis
            validation.trader_analysis = {"patterns": [p["name"] for p in patterns]}
            await db.commit()

    await _send_telegram_message(telegram_id, msg)
    logger.info(f"[P2] Done: {ea_name} {ticker} {action} {result_str}")
