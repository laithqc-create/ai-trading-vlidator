"""
Telegram Bot — Main Interface

Commands:
  /start              — Onboarding + pricing
  /check AAPL BUY 175 — Product 3: Manual validation
  /add_rule <text>    — Add personal trading rule to RAGFlow
  /my_rules           — List active personal rules
  /history            — Last 10 validations
  /connect_indicator  — Get webhook URL for TradingView (Product 1)
  /connect_ea         — Get EA monitoring script (Product 2)
  /subscribe          — Upgrade plan via Stripe
  /status             — Current plan + usage
"""
import re
from datetime import date, datetime
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
from services.subscription import SubscriptionService
from workers.tasks import validate_manual_task


# ─── Bot Application Factory ──────────────────────────────────────────────────

def create_bot_app() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("add_rule", cmd_add_rule))
    app.add_handler(CommandHandler("my_rules", cmd_my_rules))
    app.add_handler(CommandHandler("history", cmd_history))
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
    """Show subscription plans with Stripe payment links."""
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
        f"1️⃣ *Indicator Validator* — $29/mo\n"
        f"   ✓ Unlimited TradingView webhook validations\n"
        f"   ✓ Personal rule storage\n\n"
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
        f"   ✓ Crowd insights (coming soon)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Select a plan below to subscribe via Stripe:"
    )

    sub_svc = SubscriptionService()
    keyboard_rows = []
    plans = [
        ("product1", "1️⃣ Indicator — $29/mo"),
        ("product2", "2️⃣ EA Analyzer — $49/mo"),
        ("product3", "3️⃣ Manual — $19/mo"),
        ("pro", "⭐ Pro All-in — $79/mo"),
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


# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*🤖 AI Trade Validator — Commands*\n\n"
        "*Trading:*\n"
        "`/check TICKER SIGNAL [PRICE]` — Validate a trade\n"
        "  Example: `/check AAPL BUY 175`\n\n"
        "*Personal Rules:*\n"
        "`/add_rule <text>` — Add a trading rule to your KB\n"
        "`/my_rules` — List your rules\n\n"
        "*History & Account:*\n"
        "`/history` — Last 10 validations\n"
        "`/status` — Your plan and usage\n"
        "`/subscribe` — Upgrade your plan\n\n"
        "*Integrations:*\n"
        "`/connect_indicator` — TradingView webhook setup\n"
        "`/connect_ea` — EA monitoring script setup\n\n"
        "*Support:*\n"
        "`/start` — Welcome message\n"
        "`/help` — This help message"
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
        sub_svc = SubscriptionService()

        payment_url = await sub_svc.create_checkout_session(
            telegram_id=user_tg.id,
            plan=plan_id,
        )

        if payment_url:
            await query.message.reply_text(
                f"🔗 *Complete your subscription:*\n\n[Click here to pay via Stripe]({payment_url})\n\n"
                f"_After payment, your plan activates within 30 seconds._",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        else:
            await query.message.reply_text(
                "❌ Could not create payment link. Please try again or contact support.",
            )


# ─── Text Message Handler ─────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages (try to parse as trade check)."""
    text = update.message.text.strip()

    # Pattern: "AAPL BUY" or "AAPL BUY 175" or "buy AAPL"
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
            "💬 I didn't understand that. Try `/check AAPL BUY` or type /help.",
            parse_mode=ParseMode.MARKDOWN,
        )
