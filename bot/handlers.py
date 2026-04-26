"""
Telegram Bot — Main Interface

Commands:
  /start                — Onboarding + pricing
  /check TICKER SIGNAL  — Product 3: Manual validation
  /outcome WIN|LOSS     — Report trade result
  /generate <strategy>  — Product 1: English → Pine Script (free)
  /generate_ea <strat>  — Product 2: English → MQL5 EA (free)
  /share_code           — Product 1: Paste Pine Script source code
  /my_usage             — Show DeepSeek generation usage & budget
  /add_rule <text>      — Add personal trading rule to RAGFlow
  /my_rules             — List active personal rules
  /history              — Last 10 validations
  /insights             — Crowd win-rate stats (Pro)
  /connect_indicator    — Get webhook URL for TradingView (Product 1)
  /connect_ea           — Get EA monitoring script (Product 2)
  /subscribe            — Upgrade plan via Whop
  /status               — Current plan + usage
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from loguru import logger

from config.settings import settings
from db.database import AsyncSessionLocal
from db.models import User, Validation, UserRule, PlanTier, ValidationStatus, SignalType
from services.user import UserService
from services.subscription import WhopService, PLAN_TIER_MAP
from workers.tasks import validate_manual_task


# ─── Simple in-memory rate limiter (webhook abuse protection) ────────────────
# Limits each telegram_id to 20 /check commands per minute
_rate_buckets: dict = defaultdict(list)
RATE_LIMIT = 20
RATE_WINDOW = 60  # seconds


def _is_rate_limited(telegram_id: int) -> bool:
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=RATE_WINDOW)
    _rate_buckets[telegram_id] = [
        t for t in _rate_buckets[telegram_id] if t > cutoff
    ]
    if len(_rate_buckets[telegram_id]) >= RATE_LIMIT:
        return True
    _rate_buckets[telegram_id].append(now)
    return False


# ─── Bot Application Factory ──────────────────────────────────────────────────

def create_bot_app() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("outcome", cmd_outcome))
    app.add_handler(CommandHandler("generate", cmd_generate))
    app.add_handler(CommandHandler("generate_ea", cmd_generate_ea))
    app.add_handler(CommandHandler("share_code", cmd_share_code))
    app.add_handler(CommandHandler("my_usage", cmd_my_usage))
    app.add_handler(CommandHandler("add_rule", cmd_add_rule))
    app.add_handler(CommandHandler("my_rules", cmd_my_rules))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("insights", cmd_insights))
    app.add_handler(CommandHandler("connect_indicator", cmd_connect_indicator))
    app.add_handler(CommandHandler("connect_ea", cmd_connect_ea))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
            last_name=user_tg.last_name,
        )

    name = user_tg.first_name or "Trader"
    text = (
        f"👋 *Welcome to AI Trade Validator, {name}!*\n\n"
        f"I use two AI systems to validate your trades:\n"
        f"• 🤖 *OpenTrade.ai* — Technical analysis (RSI, MACD, Bollinger Bands)\n"
        f"• 📚 *RAGFlow* — Rules & historical pattern matching\n\n"
        f"*Three products available:*\n\n"
        f"1️⃣ *Indicator Validator* — $29/mo\n"
        f"   Connect your TradingView indicator for live validation\n\n"
        f"2️⃣ *EA Analyzer* — $49/mo\n"
        f"   Get AI explanations for your EA's wins and losses\n\n"
        f"3️⃣ *Manual Validator* — $19/mo\n"
        f"   Type any trade idea and get an instant second opinion\n\n"
        f"🆓 *Free tier:* 5 validations/day\n\n"
        f"*Quick start:* Try `/check AAPL BUY` to validate a trade now!\n\n"
        f"Type /help to see all commands."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 View Plans", callback_data="show_plans")],
        [InlineKeyboardButton("🔍 Try Free Check", callback_data="try_check")],
    ])

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


# ─── /check TICKER SIGNAL [PRICE] ─────────────────────────────────────────────

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Product 3: Manual trade validation.
    Usage: /check AAPL BUY [175.50]
    """
    user_tg = update.effective_user
    args = context.args

    # Rate limit check
    if _is_rate_limited(user_tg.id):
        await update.message.reply_text(
            "⏱ Slow down! You're sending too many requests. Please wait a minute.",
        )
        return

    # Parse arguments
    if not args or len(args) < 2:
        await update.message.reply_text(
            "📝 *Usage:* `/check TICKER SIGNAL [PRICE]`\n\n"
            "*Examples:*\n"
            "• `/check AAPL BUY`\n"
            "• `/check AAPL BUY 175.50`\n"
            "• `/check EURUSD SELL`\n"
            "• `/check BTC-USD BUY 65000`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = args[0].upper()
    signal_raw = args[1].upper()
    price = None

    if signal_raw not in ("BUY", "SELL", "HOLD"):
        await update.message.reply_text(
            f"❌ Invalid signal `{signal_raw}`. Use BUY, SELL, or HOLD.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if len(args) >= 3:
        try:
            price = float(args[2].replace("$", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text(
                f"❌ Invalid price `{args[2]}`. Use a number like `175.50`.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

        # Check plan access for Product 3
        if user.plan not in (PlanTier.PRODUCT3, PlanTier.PRO) and user.plan != PlanTier.FREE:
            await update.message.reply_text(
                "🔒 Manual Validator requires *Product 3* ($19/mo) or *Pro* ($79/mo).\n\n"
                "Use /subscribe to upgrade.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Check free tier limit
        if not user.can_validate(settings.FREE_TIER_DAILY_LIMIT):
            await update.message.reply_text(
                f"⏰ *Daily limit reached* ({settings.FREE_TIER_DAILY_LIMIT}/day on free plan).\n\n"
                f"Upgrade to *Product 3* ($19/mo) for unlimited checks.\n"
                f"Use /subscribe to upgrade.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Create validation record
        validation = Validation(
            user_id=user.id,
            product=3,
            ticker=ticker,
            signal=SignalType(signal_raw),
            price=price,
            status=ValidationStatus.PENDING,
            source_payload={"ticker": ticker, "signal": signal_raw, "price": price},
        )
        db.add(validation)
        await db.flush()
        validation_id = validation.id

        # Increment daily counter
        await user_svc.increment_daily_count(user)

    ragflow_dataset_id = user.ragflow_dataset_id

    # Acknowledge immediately (Telegram 30s timeout)
    price_str = f" @ ${price:.2f}" if price else ""
    await update.message.reply_text(
        f"⏳ Analyzing *{ticker}* {signal_raw}{price_str}...\n\n"
        f"_Running OpenTrade.ai + RAGFlow pipeline. "
        f"Result arrives in ~30-60 seconds._",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Dispatch to Celery worker
    validate_manual_task.delay(
        validation_id=validation_id,
        telegram_id=user_tg.id,
        ticker=ticker,
        signal=signal_raw,
        price=price,
        ragflow_dataset_id=ragflow_dataset_id,
    )


# ─── /outcome WIN|LOSS [#id] ──────────────────────────────────────────────────

async def cmd_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Report the actual outcome of your last (or specific) validation.
    Usage:
      /outcome WIN         — marks your last validation as a WIN
      /outcome LOSS        — marks your last validation as a LOSS
      /outcome WIN 42      — marks validation #42 as a WIN
      /outcome LOSS 42 -2.5 — marks #42 as LOSS with -2.5% PnL
    """
    user_tg = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text(
            "📝 *Usage:* `/outcome WIN|LOSS [#id] [pnl%]`\n\n"
            "*Examples:*\n"
            "• `/outcome WIN` — last trade won\n"
            "• `/outcome LOSS` — last trade lost\n"
            "• `/outcome WIN 42` — trade #42 won\n"
            "• `/outcome LOSS 42 -2.5` — trade #42 lost, -2.5%",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    outcome_raw = args[0].upper()
    if outcome_raw not in ("WIN", "LOSS", "SKIP"):
        await update.message.reply_text(
            "❌ Outcome must be WIN, LOSS, or SKIP.",
        )
        return

    validation_id = None
    pnl = None

    if len(args) >= 2:
        try:
            validation_id = int(args[1].lstrip("#"))
        except ValueError:
            pass

    if len(args) >= 3:
        try:
            pnl = float(args[2])
        except ValueError:
            pass

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, desc
        # Get user
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_tg.id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            await update.message.reply_text("Use /start to get started.")
            return

        if validation_id:
            # Look up specific validation
            val_result = await db.execute(
                select(Validation).where(
                    Validation.id == validation_id,
                    Validation.user_id == user.id,
                )
            )
        else:
            # Get the most recent completed validation
            val_result = await db.execute(
                select(Validation)
                .where(
                    Validation.user_id == user.id,
                    Validation.status == ValidationStatus.COMPLETED,
                )
                .order_by(Validation.completed_at.desc())
                .limit(1)
            )

        validation = val_result.scalar_one_or_none()

        if not validation:
            await update.message.reply_text(
                "❌ No validation found. Run `/check TICKER SIGNAL` first.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Update outcome
        validation.user_outcome = outcome_raw
        if pnl is not None:
            validation.user_outcome_pnl = pnl

        ticker   = validation.ticker
        signal   = validation.signal.value if validation.signal else "?"
        verdict  = validation.verdict or "?"
        val_id   = validation.id

    outcome_emoji = "✅" if outcome_raw == "WIN" else ("❌" if outcome_raw == "LOSS" else "⏭️")
    pnl_str = f" ({'+' if pnl and pnl > 0 else ''}{pnl:.2f}%)" if pnl is not None else ""

    # Was the AI correct?
    ai_correct = (
        (outcome_raw == "WIN" and verdict == "CONFIRM") or
        (outcome_raw == "LOSS" and verdict in ("REJECT", "CAUTION"))
    )
    accuracy_note = "🎯 AI was correct!" if ai_correct else "📊 Outcome logged for learning."

    await update.message.reply_text(
        f"{outcome_emoji} *Outcome recorded*\n\n"
        f"Trade: *{ticker}* {signal} (#{val_id})\n"
        f"Result: *{outcome_raw}*{pnl_str}\n"
        f"AI verdict was: *{verdict}*\n\n"
        f"{accuracy_note}\n\n"
        f"_This helps improve future validations. Use /history to see your record._",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /add_rule ────────────────────────────────────────────────────────────────

async def cmd_add_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a personal trading rule to the user's RAGFlow knowledge base."""
    user_tg = update.effective_user
    rule_text = " ".join(context.args).strip() if context.args else ""

    if not rule_text:
        await update.message.reply_text(
            "📝 *Usage:* `/add_rule <your rule>`\n\n"
            "*Examples:*\n"
            "• `/add_rule No AMD trades before 10am EST`\n"
            "• `/add_rule Avoid TSLA during earnings week`\n"
            "• `/add_rule Only buy when RSI below 35 AND MACD bullish`\n"
            "• `/add_rule Never trade crypto on weekends`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

        # Create RAGFlow dataset for user if they don't have one
        if not user.ragflow_dataset_id:
            from ragflow.service import RAGFlowService
            ragflow = RAGFlowService(settings)
            dataset_id = await ragflow.create_user_dataset(user_tg.id)
            user.ragflow_dataset_id = dataset_id

        # Save rule to DB
        rule = UserRule(user_id=user.id, rule_text=rule_text)
        db.add(rule)
        await db.flush()
        rule_id = rule.id
        dataset_id = user.ragflow_dataset_id

    # Add to RAGFlow in background
    if dataset_id:
        from ragflow.service import RAGFlowService
        import asyncio
        ragflow = RAGFlowService(settings)
        doc_id = await ragflow.add_rule_to_dataset(dataset_id, rule_text, rule_id)
        if doc_id:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                result = await db.execute(select(UserRule).where(UserRule.id == rule_id))
                saved_rule = result.scalar_one_or_none()
                if saved_rule:
                    saved_rule.ragflow_doc_id = doc_id

    await update.message.reply_text(
        f"✅ *Rule added to your knowledge base!*\n\n"
        f"📋 `{rule_text}`\n\n"
        f"_This rule will now be checked every time you validate a trade._",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /my_rules ────────────────────────────────────────────────────────────────

async def cmd_my_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List the user's personal trading rules."""
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_tg.id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await update.message.reply_text("Use /start to get started.")
            return

        rules_result = await db.execute(
            select(UserRule)
            .where(UserRule.user_id == user.id, UserRule.is_active == True)
            .order_by(UserRule.created_at.desc())
        )
        rules = rules_result.scalars().all()

    if not rules:
        await update.message.reply_text(
            "📋 *You have no personal rules yet.*\n\n"
            "Add rules with `/add_rule <your rule>`\n\n"
            "_Example:_ `/add_rule No AMD before 10am EST`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = ["📋 *Your Personal Trading Rules*\n"]
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. `{rule.rule_text}`")

    lines.append(f"\n_Total: {len(rules)} rules — applied to every validation._")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /history ─────────────────────────────────────────────────────────────────

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the last 10 validations."""
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_tg.id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            await update.message.reply_text("Use /start to get started.")
            return

        val_result = await db.execute(
            select(Validation)
            .where(
                Validation.user_id == user.id,
                Validation.status == ValidationStatus.COMPLETED,
            )
            .order_by(Validation.completed_at.desc())
            .limit(10)
        )
        validations = val_result.scalars().all()

    if not validations:
        await update.message.reply_text(
            "📊 *No validations yet.*\n\nTry `/check AAPL BUY` to run your first analysis.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = ["📊 *Your Last 10 Validations*\n"]
    for v in validations:
        verdict_emoji = {"CONFIRM": "✅", "CAUTION": "⚠️", "REJECT": "❌"}.get(v.verdict, "🔄")
        conf = f"{int((v.confidence_score or 0) * 100)}%"
        ts = v.completed_at.strftime("%m/%d %H:%M") if v.completed_at else "?"
        signal_emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸️"}.get(
            v.signal.value if v.signal else "", "")
        lines.append(
            f"{verdict_emoji} `{v.ticker}` {signal_emoji}{v.signal.value if v.signal else ''} "
            f"— {conf} — {ts}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /connect_indicator ───────────────────────────────────────────────────────

async def cmd_connect_indicator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and display the TradingView webhook URL for Product 1."""
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

        if user.plan not in (PlanTier.PRODUCT1, PlanTier.PRO):
            await update.message.reply_text(
                "🔒 *Indicator Validator requires Product 1* ($29/mo) or *Pro* ($79/mo).\n\n"
                "Use /subscribe to upgrade.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        token = await user_svc.get_or_create_webhook_token(user, "indicator")

    webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL.rsplit('/webhook', 1)[0]}/webhook/indicator/{token}"

    text = (
        f"*📡 TradingView Webhook Setup*\n\n"
        f"Your webhook URL:\n`{webhook_url}`\n\n"
        f"*Setup steps in TradingView:*\n"
        f"1. Open your indicator → Settings → Alerts\n"
        f"2. Set *Webhook URL* to the URL above\n"
        f"3. Set the message body to:\n\n"
        f"```\n"
        f"{{\n"
        f'  "ticker": "{{{{ticker}}}}",\n'
        f'  "signal": "BUY",\n'
        f'  "price": {{{{close}}}},\n'
        f'  "indicator": "YourIndicatorName"\n'
        f"}}\n"
        f"```\n\n"
        f"_Replace `\"BUY\"` with your signal variable._"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /connect_ea ──────────────────────────────────────────────────────────────

async def cmd_connect_ea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provide EA monitoring script instructions for Product 2."""
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

        if user.plan not in (PlanTier.PRODUCT2, PlanTier.PRO):
            await update.message.reply_text(
                "🔒 *EA Analyzer requires Product 2* ($49/mo) or *Pro* ($79/mo).\n\n"
                "Use /subscribe to upgrade.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        token = await user_svc.get_or_create_webhook_token(user, "ea")

    ea_webhook = f"{settings.TELEGRAM_WEBHOOK_URL.rsplit('/webhook', 1)[0]}/webhook/ea/{token}"

    text = (
        f"*⚙️ EA Monitoring Setup*\n\n"
        f"Your EA webhook:\n`{ea_webhook}`\n\n"
        f"*Option 1 — Python monitoring script*\n"
        f"Download: `/scripts/ea_monitor.py`\n"
        f"Run on your VPS: `python ea_monitor.py --logfile path/to/ea.log`\n\n"
        f"*Option 2 — MQL5 direct webhook*\n"
        f"Add to your EA's `OnTrade()` function:\n\n"
        f"```mql5\n"
        f'string url = "{ea_webhook}";\n'
        f'string json = StringFormat(\n'
        f'  "{{\\\"ea_name\\\":\\\"MyEA\\\",\\\"ticker\\\":\\\"{{%s}}\\\","'
        f'  "\\\"action\\\":\\\"{{%s}}\\\",\\\"result\\\":\\\"{{%s}}\\\","'
        f'  "\\\"pnl\\\":{{%.2f}}}}",\n'
        f"  Symbol(), action, result, pnl\n"
        f");\n"
        f"WebRequest(\"POST\", url, headers, 5000, json, response, res_headers);\n"
        f"```\n\n"
        f"_Your EA runs on your own account. We only receive trade logs, never credentials._"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /subscribe ───────────────────────────────────────────────────────────────

async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show subscription plans with Whop payment links."""
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)
        current_plan = user.plan

    plan_emoji = {"free": "🆓", "product1": "1️⃣", "product2": "2️⃣", "product3": "3️⃣", "pro": "⭐"}
    current = plan_emoji.get(current_plan.value, "🆓")

    text = (
        f"*💳 Subscription Plans*\n\n"
        f"Current plan: {current} *{current_plan.value.upper()}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ *Indicator Validator* — $19/mo\n"
        f"   ✓ TradingView webhook validation\n"
        f"   ✓ Share source code storage\n"
        f"   ✓ Personal rule KB\n\n"
        f"2️⃣ *EA Analyzer* — $49/mo\n"
        f"   ✓ EA trade log analysis\n"
        f"   ✓ Win/loss explanations\n"
        f"   ✓ Improvement suggestions\n\n"
        f"3️⃣ *Manual Validator* — $19/mo\n"
        f"   ✓ Unlimited `/check` commands\n"
        f"   ✓ Full technical + mentor analysis\n\n"
        f"⭐ *Pro (All 3)* — $79/mo\n"
        f"   ✓ Everything above\n"
        f"   ✓ Priority processing\n"
        f"   ✓ Crowd insights\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆓 *Free for everyone:* /generate (Pine Script) + /generate_ea (MQL5)\n\n"
        f"Select a plan to pay via *Whop* (241 territories, instant activation):"
    )

    keyboard_rows = []
    plans = [
        ("product1", "1️⃣ Indicator Validator — $19/mo"),
        ("product2", "2️⃣ EA Analyzer — $49/mo"),
        ("product3", "3️⃣ Manual Validator — $19/mo"),
        ("pro", "⭐ Pro Bundle — $79/mo"),
    ]

    for plan_id, label in plans:
        if plan_id != current_plan.value:
            keyboard_rows.append([
                InlineKeyboardButton(label, callback_data=f"subscribe_{plan_id}")
            ])

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


# ─── /status ──────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, func as sqlfunc
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_tg.id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            await update.message.reply_text("Use /start to get started.")
            return

        count_result = await db.execute(
            select(sqlfunc.count(Validation.id))
            .where(Validation.user_id == user.id, Validation.status == ValidationStatus.COMPLETED)
        )
        total_validations = count_result.scalar() or 0

    plan_emoji = {"free": "🆓", "product1": "1️⃣", "product2": "2️⃣", "product3": "3️⃣", "pro": "⭐"}
    emoji = plan_emoji.get(user.plan.value, "🆓")

    daily_used = user.daily_validation_count if user.daily_validation_date == date.today() else 0
    daily_limit = settings.FREE_TIER_DAILY_LIMIT if user.plan == PlanTier.FREE else "∞"

    expires = ""
    if user.plan_expires_at:
        expires = f"\n📅 Renews: {user.plan_expires_at.strftime('%Y-%m-%d')}"

    text = (
        f"*📊 Your Account Status*\n\n"
        f"Plan: {emoji} *{user.plan.value.upper()}*{expires}\n"
        f"Daily usage: {daily_used}/{daily_limit}\n"
        f"Total validations: {total_validations}\n\n"
        f"RAGFlow KB: {'✅ Active' if user.ragflow_dataset_id else '❌ Not set up'}\n"
        f"Indicator webhook: {'✅ Connected' if user.indicator_webhook_token else '❌ Not connected'}\n"
        f"EA webhook: {'✅ Connected' if user.ea_webhook_token else '❌ Not connected'}"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── /insights ────────────────────────────────────────────────────────────────

async def cmd_insights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Pro feature: Show crowd-sourced win rate insights from all users.
    """
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, case
        from sqlalchemy import func as sqlfunc

        user_result = await db.execute(
            select(User).where(User.telegram_id == user_tg.id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            await update.message.reply_text("Use /start to get started.")
            return

        if user.plan != PlanTier.PRO:
            await update.message.reply_text(
                "🔒 *Crowd Insights* is a *Pro* feature ($79/mo).\n\n"
                "It shows anonymized win-rate data from all users:\n"
                "_\"When AI says CONFIRM on a BUY, users win 71% of the time\"_\n\n"
                "Use /subscribe to upgrade to Pro.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Fetch real stats from DB — count wins per verdict+signal combination
        result = await db.execute(
            select(
                Validation.verdict,
                Validation.signal,
                sqlfunc.count(Validation.id).label("total"),
                sqlfunc.sum(
                    case((Validation.user_outcome == "WIN", 1), else_=0)
                ).label("wins"),
            )
            .where(Validation.user_outcome.isnot(None))
            .group_by(Validation.verdict, Validation.signal)
            .order_by(sqlfunc.count(Validation.id).desc())
        )
        rows = result.fetchall()

    if not rows:
        await update.message.reply_text(
            "📊 *Crowd Insights*\n\n"
            "_Not enough data yet. Insights are generated weekly once enough users report outcomes._\n\n"
            "Help build the dataset by reporting your trade outcomes with `/outcome WIN` or `/outcome LOSS`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = ["📊 *Crowd Insights — Community Win Rates*\n"]
    has_data = False
    for row in rows:
        if (row.total or 0) < 5:
            continue
        has_data = True
        win_rate = (row.wins or 0) / row.total * 100
        emoji = "✅" if win_rate >= 60 else ("⚠️" if win_rate >= 45 else "❌")
        signal_val = row.signal.value if hasattr(row.signal, "value") else str(row.signal)
        lines.append(
            f"{emoji} AI *{row.verdict}* on *{signal_val}*: "
            f"{win_rate:.0f}% win rate ({row.total} trades)"
        )

    if not has_data:
        lines.append("_Not enough trades per category yet (need 5+). Keep reporting outcomes!_")

    lines.append("\n_Data is anonymized. Updated weekly._")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)



# ─── /generate "strategy" ─────────────────────────────────────────────────────

async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Product 1 (Free): Natural language → Pine Script v6.
    Usage: /generate Buy when RSI below 30 and volume above average
    Cost: ~$0.002/call absorbed up to $5/user.
    """
    user_tg = update.effective_user
    strategy = " ".join(context.args).strip() if context.args else ""

    if not strategy:
        await update.message.reply_text(
            "*📈 Pine Script Generator — Free*\n\n"
            "Describe your trading strategy in plain English:\n\n"
            "`/generate Buy when RSI is below 30 and volume is above 20-day average`\n"
            "`/generate Sell when price crosses below the 50 EMA`\n"
            "`/generate Alert when MACD histogram turns positive after being negative`\n\n"
            "_Generates ready-to-paste Pine Script v6 code for TradingView._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

        if user_svc.is_over_generation_cap(user):
            await update.message.reply_text(
                "⚠️ *Free generation limit reached*\n\n"
                f"You\'ve used your $5.00 free credit (~{user.total_generations} generations).\n\n"
                "Upgrade to *Pro* ($79/mo) for unlimited generations.\n"
                "Use /subscribe to upgrade.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        budget_left = user_svc.generation_budget_remaining(user)
        spent = user.total_generation_cost or 0.0

    # Show "working" message
    thinking_msg = await update.message.reply_text(
        "⏳ *Generating Pine Script v6...*\n_DeepSeek AI is writing your indicator._",
        parse_mode=ParseMode.MARKDOWN,
    )

    from services.deepseek import DeepSeekService, CODE_DISCLAIMER
    ds = DeepSeekService()
    result = await ds.generate_pine_script(strategy)

    if not result["success"]:
        await thinking_msg.edit_text(
            f"❌ Generation failed: {result['error']}\n\nPlease try again.",
        )
        return

    # Track cost
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)
        await user_svc.increment_generation_cost(user, result["cost"])
        new_spent = user.total_generation_cost or 0.0

    # Delete the "working" message
    await thinking_msg.delete()

    code = result["code"]
    # Telegram has 4096 char limit — truncate if massive
    code_preview = code[:3000] + "\n... (truncated)" if len(code) > 3000 else code

    response = (
        f"*✅ Pine Script v6 Generated*\n\n"
        f"*Strategy:* _{strategy[:80]}_\n\n"
        f"```pine\n{code_preview}\n```"
        f"{CODE_DISCLAIMER}\n\n"
        f"_Budget used: ${new_spent:.3f} / $5.00_\n"
        f"_💡 Want this validated? /subscribe for $19/mo_"
    )

    # Warn if approaching cap
    if new_spent >= 4.50:
        response += f"\n\n⚠️ _Approaching $5 free limit ({new_spent:.2f} spent). Upgrade for unlimited._"

    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


# ─── /generate_ea "strategy" ──────────────────────────────────────────────────

async def cmd_generate_ea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Product 2 (Free): Natural language → MQL5 Expert Advisor.
    Usage: /generate_ea Place buy stop 10 pips above high when RSI > 50
    """
    user_tg = update.effective_user
    strategy = " ".join(context.args).strip() if context.args else ""

    if not strategy:
        await update.message.reply_text(
            "*⚙️ MQL5 EA Generator — Free*\n\n"
            "Describe your EA strategy in plain English:\n\n"
            "`/generate_ea Buy when RSI crosses above 50, sell when it crosses below`\n"
            "`/generate_ea Place buy stop 10 pips above the high of every new candle`\n"
            "`/generate_ea Scalp with 5 pip TP and 10 pip SL on EURUSD M1`\n\n"
            "_Generates ready-to-compile MQL5 EA code for MetaTrader 5._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

        if user_svc.is_over_generation_cap(user):
            await update.message.reply_text(
                "⚠️ *Free generation limit reached*\n\n"
                "You\'ve used your $5.00 free credit.\n\n"
                "Upgrade to *Pro* ($79/mo) for unlimited generations.\n"
                "Use /subscribe to upgrade.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    thinking_msg = await update.message.reply_text(
        "⏳ *Generating MQL5 EA...*\n_DeepSeek AI is writing your Expert Advisor._",
        parse_mode=ParseMode.MARKDOWN,
    )

    from services.deepseek import DeepSeekService, CODE_DISCLAIMER
    ds = DeepSeekService()
    result = await ds.generate_mql5(strategy)

    if not result["success"]:
        await thinking_msg.edit_text(
            f"❌ Generation failed: {result['error']}\n\nPlease try again.",
        )
        return

    # Track cost
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)
        await user_svc.increment_generation_cost(user, result["cost"])
        new_spent = user.total_generation_cost or 0.0

    await thinking_msg.delete()

    code = result["code"]
    code_preview = code[:3000] + "\n... (truncated)" if len(code) > 3000 else code

    response = (
        f"*✅ MQL5 EA Generated*\n\n"
        f"*Strategy:* _{strategy[:80]}_\n\n"
        f"```mql5\n{code_preview}\n```"
        f"{CODE_DISCLAIMER}\n\n"
        f"_Budget used: ${new_spent:.3f} / $5.00_\n"
        f"_💡 Want this EA monitored & analyzed? /subscribe for $49/mo_"
    )

    if new_spent >= 4.50:
        response += f"\n\n⚠️ _Approaching $5 free limit ({new_spent:.2f} spent). Upgrade for unlimited._"

    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


# ─── /share_code ──────────────────────────────────────────────────────────────

async def cmd_share_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Product 1: Share Pine Script source code so the system can use it
    as validation context (bypasses TradingView 3-indicator limit).
    The code is stored in the user's RAGFlow dataset.
    """
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)

    # Check if code was passed inline or if we need to prompt
    inline_code = " ".join(context.args).strip() if context.args else ""

    if not inline_code:
        # Set a flag so next text message is treated as Pine Script
        context.user_data["awaiting_pine_code"] = True
        await update.message.reply_text(
            "*📋 Share Pine Script Source Code*\n\n"
            "Paste your indicator\'s Pine Script code in the next message.\n\n"
            "_Your code will be stored in your personal knowledge base and used "
            "to validate future signals from this indicator._\n\n"
            "Supports: `.pine` file upload or plain text paste.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await _store_pine_code(update, user, inline_code)


async def _store_pine_code(update: Update, user, code: str):
    """Store Pine Script code in the user's RAGFlow dataset."""
    from ragflow.service import RAGFlowService
    ragflow = RAGFlowService(settings)

    # Create dataset if needed
    if not user.ragflow_dataset_id:
        dataset_id = await ragflow.create_user_dataset(user.telegram_id)
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(User.telegram_id == user.telegram_id)
            )
            db_user = result.scalar_one_or_none()
            if db_user:
                db_user.ragflow_dataset_id = dataset_id
    else:
        dataset_id = user.ragflow_dataset_id

    # Build rule text wrapping the code
    rule_text = (
        f"PINE SCRIPT INDICATOR (user-shared):\n"
        f"The user trades with this indicator. Use this code to understand "
        f"their entry/exit logic when validating signals.\n\n"
        f"```pine\n{code[:2000]}\n```"
    )

    doc_id = await ragflow.add_rule_to_dataset(
        dataset_id=dataset_id,
        rule_text=rule_text,
        rule_id=99000 + (user.id or 0),
    )

    if doc_id:
        # Count lines for confirmation
        lines = len(code.strip().split("\n"))
        await update.message.reply_text(
            f"*✅ Pine Script Saved*\n\n"
            f"_{lines} lines stored in your knowledge base._\n\n"
            f"Your indicator logic will now be used to validate future signals.\n"
            f"Use /connect_indicator to link your TradingView webhook.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "❌ Failed to save code. RAGFlow may be unavailable. Please try again.",
        )


# ─── /my_usage ────────────────────────────────────────────────────────────────

async def cmd_my_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user's DeepSeek generation usage and remaining free budget."""
    user_tg = update.effective_user

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=user_tg.id)
        spent = user.total_generation_cost or 0.0
        generations = user.total_generations or 0
        remaining = user_svc.generation_budget_remaining(user)
        capped = user_svc.is_over_generation_cap(user)

    # Build usage bar
    pct = min(spent / settings.DEEPSEEK_FREE_CAP, 1.0)
    filled = int(pct * 10)
    bar = "█" * filled + "░" * (10 - filled)

    status = "🔴 Limit reached" if capped else ("🟡 Approaching limit" if pct >= 0.8 else "🟢 Good")

    await update.message.reply_text(
        f"*📊 Your Free Generation Usage*\n\n"
        f"Budget: `[{bar}]` ${spent:.3f} / ${settings.DEEPSEEK_FREE_CAP:.2f}\n"
        f"Generations used: *{generations}*\n"
        f"Budget remaining: *${remaining:.3f}*\n"
        f"Status: {status}\n\n"
        f"*Commands that use budget:*\n"
        f"• `/generate` — Pine Script (~$0.002 each)\n"
        f"• `/generate_ea` — MQL5 EA (~$0.002 each)\n\n"
        f"_At $0.002/generation you can generate ~{int(remaining/0.002):,} more scripts._\n\n"
        + ("⚠️ Upgrade to *Pro* ($79/mo) for unlimited. Use /subscribe." if capped else
           "💡 Validations (/check) do NOT consume this budget."),
        parse_mode=ParseMode.MARKDOWN,
    )



# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*🤖 AI Trade Validator — Commands*\n\n"
        "*🆓 Free for everyone:*\n"
        "`/generate <strategy>` — English → Pine Script v6\n"
        "  Example: `/generate Buy when RSI below 30`\n\n"
        "`/generate_ea <strategy>` — English → MQL5 EA\n"
        "  Example: `/generate_ea Scalp 5 pip TP on EURUSD M1`\n\n"
        "`/share_code` — Paste Pine Script source (stores in your KB)\n"
        "`/my_usage` — View free generation budget ($5 cap)\n\n"
        "*📈 Trading (Paid):*\n"
        "`/check TICKER SIGNAL [PRICE]` — Validate a trade\n"
        "  Example: `/check AAPL BUY 175`\n\n"
        "`/outcome WIN|LOSS [#id] [pnl%]` — Report trade result\n"
        "  Example: `/outcome WIN` or `/outcome LOSS 42 -2.5`\n\n"
        "*📚 Personal Rules:*\n"
        "`/add_rule <text>` — Add a trading rule to your KB\n"
        "`/my_rules` — List your rules\n\n"
        "*📊 History & Stats:*\n"
        "`/history` — Last 10 validations\n"
        "`/insights` — Crowd win-rate data ⭐ Pro\n\n"
        "*⚙️ Integrations:*\n"
        "`/connect_indicator` — TradingView webhook setup\n"
        "`/connect_ea` — EA monitoring script setup\n\n"
        "*💳 Account:*\n"
        "`/status` — Your plan and usage\n"
        "`/subscribe` — Upgrade via Whop (241 territories)\n\n"
        "`/start` — Welcome · `/help` — This message"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── Callback Query Handler ───────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "show_plans":
        await cmd_subscribe(update, context)

    elif data == "try_check":
        await query.message.reply_text(
            "Try it now! Type:\n`/check AAPL BUY`\nor\n`/check TSLA SELL 250`",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("subscribe_"):
        plan_id = data.replace("subscribe_", "")
        user_tg = update.effective_user
        from services.subscription import WhopService
        whop = WhopService()
        checkout_url = whop.get_checkout_url(plan=plan_id, telegram_id=user_tg.id)

        if checkout_url:
            plan_labels = {
                "product1": "Indicator Validator ($19/mo)",
                "product2": "EA Analyzer ($49/mo)",
                "product3": "Manual Validator ($19/mo)",
                "pro": "Pro Bundle ($79/mo)",
            }
            await query.message.reply_text(
                f"🔗 *Complete your subscription on Whop:*\n\n"
                f"Plan: *{plan_labels.get(plan_id, plan_id)}*\n\n"
                f"[👉 Click here to subscribe]({checkout_url})\n\n"
                f"_Whop supports 241 territories. Your plan activates instantly after payment._",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        else:
            await query.message.reply_text(
                "❌ Could not create payment link. "
                "Whop product IDs may not be configured yet. Please contact support.",
            )


# ─── Text Message Handler ─────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages.
    1. If awaiting Pine Script after /share_code, capture and store it.
    2. If looks like a trade (AAPL BUY), route to /check.
    3. Otherwise show help hint.
    """
    text = update.message.text.strip()

    # ── Check if we are awaiting Pine Script paste ────────────────
    if context.user_data.get("awaiting_pine_code"):
        context.user_data.pop("awaiting_pine_code", None)
        # Looks like code if it has //@version or common Pine keywords
        pine_keywords = ["//@version", "indicator(", "strategy(", "plot(", "ta.rsi"]
        if any(kw in text for kw in pine_keywords) or len(text) > 100:
            async with AsyncSessionLocal() as db:
                user_svc = UserService(db)
                user = await user_svc.get_or_create_user(telegram_id=update.effective_user.id)
            await _store_pine_code(update, user, text)
            return
        else:
            await update.message.reply_text(
                "❓ That doesn't look like Pine Script. "
                "Use /share_code again and paste your indicator code.",
            )
            return

    # ── Try to parse as quick trade check ─────────────────────────
    pattern = r"^([A-Z]{1,6}(?:-USD)?)\s+(BUY|SELL|HOLD)(?:\s+(\d+(?:\.\d+)?))?$"
    match = re.match(pattern, text.upper())
    if match:
        ticker, signal, price_str = match.groups()
        context.args = [ticker, signal]
        if price_str:
            context.args.append(price_str)
        await cmd_check(update, context)
    else:
        await update.message.reply_text(
            "💬 I didn't understand that.\n\n"
            "Try `/check AAPL BUY` or `/generate Buy when RSI below 30`\n"
            "Type /help to see all commands.",
            parse_mode=ParseMode.MARKDOWN,
        )
