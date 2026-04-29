"""
TG_Bot/handlers/validate.py

Handles trade validation flows:
  /check [TICKER] [SIGNAL] [PRICE] — Manual validation (Product 3)
  /outcome WIN|LOSS [#id] [pnl]   — Report trade result
  /history                         — Last 10 validations
  /connect_indicator               — Webhook URL for TradingView
  /connect_ea                      — EA monitoring script instructions
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from TG_Bot.states.states import ManualCheckSG, OutcomeSG
from TG_Bot.keyboards.strategy_kb import signal_selector, skip_price_keyboard
from TG_Bot.keyboards.product_kb import (
    verdict_actions_keyboard, history_actions_keyboard,
    subscription_plans_keyboard, back_to_menu_keyboard,
)
from TG_Bot.keyboards.main_menu import main_menu_keyboard, remove_keyboard
from db.models import User, PlanTier, Validation, ValidationStatus, SignalType
from config.settings import settings

router = Router(name="validate")


# ─── /check ───────────────────────────────────────────────────────────────────

@router.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext, user: User):
    """Entry point — parse inline args or start FSM flow."""
    args = message.text.split()[1:]  # skip /check

    # If all three args given: /check AAPL BUY 175
    if len(args) >= 2:
        ticker = args[0].upper()
        signal_raw = args[1].upper()
        price = None
        if len(args) >= 3:
            try:
                price = float(args[2].replace("$", "").replace(",", ""))
            except ValueError:
                pass

        if signal_raw not in ("BUY", "SELL", "HOLD"):
            await message.answer(
                f"❌ Invalid signal `{signal_raw}`. Use BUY, SELL, or HOLD.",
                parse_mode="Markdown",
            )
            return

        await _dispatch_validation(message, state, user, ticker, signal_raw, price)
        return

    # Else start FSM
    await start_manual_check(message, user)


async def start_manual_check(message: Message, user: User):
    """Begin the guided /check FSM flow."""
    if user.plan not in (PlanTier.PRODUCT3, PlanTier.PRO, PlanTier.FREE):
        await message.answer(
            "🔒 *Manual Validator* requires *Product 3* ($19/mo) or *Pro* ($79/mo).\n\n"
            "Use /subscribe to upgrade.",
            parse_mode="Markdown",
            reply_markup=subscription_plans_keyboard(user.plan.value),
        )
        return

    if not user.can_validate(settings.FREE_TIER_DAILY_LIMIT):
        await message.answer(
            f"⏰ *Daily limit reached* ({settings.FREE_TIER_DAILY_LIMIT}/day on free plan).\n\n"
            "Upgrade to *Product 3* ($19/mo) for unlimited checks.",
            parse_mode="Markdown",
            reply_markup=subscription_plans_keyboard(user.plan.value),
        )
        return

    from aiogram.fsm.context import FSMContext
    # Can't set state here without FSMContext, so just prompt inline
    await message.answer(
        "*🔍 Manual Trade Validator*\n\n"
        "Type your trade in this format:\n\n"
        "`/check TICKER SIGNAL [PRICE]`\n\n"
        "*Examples:*\n"
        "• `/check AAPL BUY`\n"
        "• `/check AAPL BUY 175.50`\n"
        "• `/check EURUSD SELL`\n"
        "• `/check BTC-USD BUY 65000`",
        parse_mode="Markdown",
    )


async def send_webhook_setup(message: Message, user: User):
    """Send TradingView webhook setup instructions."""
    if user.plan not in (PlanTier.PRODUCT1, PlanTier.PRO):
        await message.answer(
            "🔒 *Webhook connection* requires *Product 1* ($19/mo) or *Pro* ($79/mo).\n\n"
            "Use /subscribe to upgrade, or try the free options:\n"
            "📄 Share Source Code or 🤖 AI Generate (no subscription needed).",
            parse_mode="Markdown",
            reply_markup=subscription_plans_keyboard(user.plan.value),
        )
        return

    from services.user import UserService
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        token = await user_svc.get_or_create_webhook_token(db_user, "indicator")

    base = settings.TELEGRAM_WEBHOOK_URL.rsplit("/webhook", 1)[0]
    webhook_url = f"{base}/webhook/indicator/{token}"

    await message.answer(
        f"*🔌 TradingView Webhook Setup*\n\n"
        f"Your webhook URL:\n`{webhook_url}`\n\n"
        f"*Steps in TradingView:*\n"
        f"1. Open indicator → Settings → Alerts\n"
        f"2. Set *Webhook URL* to the URL above\n"
        f"3. Set message body to:\n\n"
        f"```json\n"
        f'{{\n  "ticker": "{{{{ticker}}}}",\n'
        f'  "signal": "BUY",\n'
        f'  "price": {{{{close}}}},\n'
        f'  "indicator": "MyIndicator"\n}}\n'
        f"```\n\n"
        f"_Replace `\"BUY\"` with your signal variable._",
        parse_mode="Markdown",
    )


async def _dispatch_validation(
    message: Message,
    state: FSMContext,
    user: User,
    ticker: str,
    signal: str,
    price: float | None,
):
    """Create DB record, send 'working' message, dispatch Celery task."""
    from db.database import AsyncSessionLocal
    from db.models import Validation, ValidationStatus, SignalType

    # Check free tier limit
    if not user.can_validate(settings.FREE_TIER_DAILY_LIMIT):
        await message.answer(
            f"⏰ *Daily limit reached* ({settings.FREE_TIER_DAILY_LIMIT}/day on free plan).\n\n"
            "Upgrade to Product 3 ($19/mo) for unlimited checks.",
            parse_mode="Markdown",
            reply_markup=subscription_plans_keyboard(user.plan.value),
        )
        return

    async with AsyncSessionLocal() as db:
        from services.user import UserService
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        await user_svc.increment_daily_count(db_user)

        validation = Validation(
            user_id=db_user.id,
            product=3,
            ticker=ticker,
            signal=SignalType(signal),
            price=price,
            status=ValidationStatus.PENDING,
            source_payload={"ticker": ticker, "signal": signal, "price": price},
        )
        db.add(validation)
        await db.flush()
        validation_id = validation.id
        ragflow_dataset_id = db_user.ragflow_dataset_id

    price_str = f" @ ${price:.2f}" if price else ""
    await message.answer(
        f"⏳ *Analyzing {ticker} {signal}{price_str}...*\n\n"
        f"_Running OpenTrade.ai + RAGFlow pipeline._\n"
        f"_Result arrives in ~30-60 seconds._",
        parse_mode="Markdown",
    )

    from workers.tasks import validate_manual_task
    validate_manual_task.delay(
        validation_id=validation_id,
        telegram_id=user.telegram_id,
        ticker=ticker,
        signal=signal,
        price=price,
        ragflow_dataset_id=ragflow_dataset_id,
    )

    await state.clear()


# ─── /outcome ─────────────────────────────────────────────────────────────────

@router.message(Command("outcome"))
async def cmd_outcome(message: Message, state: FSMContext, user: User):
    args = message.text.split()[1:]

    if not args:
        await message.answer(
            "*📝 Report Trade Outcome*\n\n"
            "`/outcome WIN` — last trade won\n"
            "`/outcome LOSS` — last trade lost\n"
            "`/outcome WIN 42` — trade #42 won\n"
            "`/outcome LOSS 42 -2.5` — #42 lost, -2.5% PnL",
            parse_mode="Markdown",
        )
        return

    outcome_raw = args[0].upper()
    if outcome_raw not in ("WIN", "LOSS", "SKIP"):
        await message.answer("❌ Use WIN, LOSS, or SKIP.")
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

    await _save_outcome(message, user, outcome_raw, validation_id, pnl)


@router.callback_query(F.data.startswith("outcome_win_"))
async def cb_outcome_win(callback: CallbackQuery, user: User):
    val_id = int(callback.data.split("_")[-1])
    await _save_outcome(callback.message, user, "WIN", val_id, None)
    await callback.answer("✅ Outcome recorded!")


@router.callback_query(F.data.startswith("outcome_loss_"))
async def cb_outcome_loss(callback: CallbackQuery, user: User):
    val_id = int(callback.data.split("_")[-1])
    await _save_outcome(callback.message, user, "LOSS", val_id, None)
    await callback.answer("❌ Outcome recorded!")


@router.callback_query(F.data.startswith("outcome_skip_"))
async def cb_outcome_skip(callback: CallbackQuery, user: User):
    val_id = int(callback.data.split("_")[-1])
    await _save_outcome(callback.message, user, "SKIP", val_id, None)
    await callback.answer("⏭️ Skipped.")


async def _save_outcome(
    message: Message,
    user: User,
    outcome: str,
    validation_id: int | None,
    pnl: float | None,
):
    from db.database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        if validation_id:
            result = await db.execute(
                select(Validation).where(
                    Validation.id == validation_id,
                    Validation.user_id == user.id,
                )
            )
        else:
            result = await db.execute(
                select(Validation)
                .where(
                    Validation.user_id == user.id,
                    Validation.status == ValidationStatus.COMPLETED,
                )
                .order_by(Validation.completed_at.desc())
                .limit(1)
            )

        validation = result.scalar_one_or_none()

        if not validation:
            await message.answer(
                "❌ No validation found. Run `/check TICKER SIGNAL` first.",
                parse_mode="Markdown",
            )
            return

        validation.user_outcome = outcome
        if pnl is not None:
            validation.user_outcome_pnl = pnl

        ticker   = validation.ticker
        signal   = validation.signal.value if validation.signal else "?"
        verdict  = validation.verdict or "?"
        val_id   = validation.id

    emoji = {"WIN": "✅", "LOSS": "❌", "SKIP": "⏭️"}.get(outcome, "📊")
    pnl_str = f" ({'+' if pnl and pnl > 0 else ''}{pnl:.2f}%)" if pnl else ""
    ai_correct = (
        (outcome == "WIN" and verdict == "CONFIRM") or
        (outcome == "LOSS" and verdict in ("REJECT", "CAUTION"))
    )
    accuracy_note = "🎯 AI was correct!" if ai_correct else "📊 Noted for learning."

    await message.answer(
        f"{emoji} *Outcome Recorded*\n\n"
        f"Trade: *{ticker}* {signal} (#{val_id})\n"
        f"Result: *{outcome}*{pnl_str}\n"
        f"AI verdict was: *{verdict}*\n\n"
        f"{accuracy_note}",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )


# ─── /history ─────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message, user: User):
    from db.database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Validation)
            .where(
                Validation.user_id == user.id,
                Validation.status == ValidationStatus.COMPLETED,
            )
            .order_by(Validation.completed_at.desc())
            .limit(10)
        )
        validations = result.scalars().all()

    if not validations:
        await message.answer(
            "📊 *No validations yet.*\n\n"
            "Try `/check AAPL BUY` to run your first analysis.",
            parse_mode="Markdown",
        )
        return

    v_emoji = {"CONFIRM": "✅", "CAUTION": "⚠️", "REJECT": "❌"}
    s_emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸️"}

    lines = ["*📊 Last 10 Validations*\n"]
    for v in validations:
        ve = v_emoji.get(v.verdict or "", "🔄")
        se = s_emoji.get(v.signal.value if v.signal else "", "")
        conf = f"{int((v.confidence_score or 0) * 100)}%"
        ts = v.completed_at.strftime("%m/%d %H:%M") if v.completed_at else "?"
        outcome_tag = f" → {v.user_outcome}" if v.user_outcome else ""
        lines.append(
            f"{ve} `{v.ticker}` {se}{v.signal.value if v.signal else ''} "
            f"— {conf} — {ts}{outcome_tag}"
        )

    # Accuracy summary
    reported = [v for v in validations if v.user_outcome in ("WIN", "LOSS")]
    if reported:
        correct = sum(
            1 for v in reported
            if (v.user_outcome == "WIN" and v.verdict == "CONFIRM")
            or (v.user_outcome == "LOSS" and v.verdict in ("REJECT", "CAUTION"))
        )
        acc = int(correct / len(reported) * 100)
        lines.append(f"\n_AI accuracy (self-reported): {acc}% over {len(reported)} trades_")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=history_actions_keyboard(),
    )


# ─── /connect_indicator ───────────────────────────────────────────────────────

@router.message(Command("connect_indicator"))
async def cmd_connect_indicator(message: Message, user: User):
    await send_webhook_setup(message, user)


# ─── /connect_ea ──────────────────────────────────────────────────────────────

@router.message(Command("connect_ea"))
async def cmd_connect_ea(message: Message, user: User):
    if user.plan not in (PlanTier.PRODUCT2, PlanTier.PRO):
        await message.answer(
            "🔒 *EA Monitor* requires *Product 2* ($49/mo) or *Pro* ($79/mo).\n\n"
            "Or use the free MQL5 generator: `/generate_ea <strategy>`",
            parse_mode="Markdown",
            reply_markup=subscription_plans_keyboard(user.plan.value),
        )
        return

    from services.user import UserService
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        token = await user_svc.get_or_create_webhook_token(db_user, "ea")

    base = settings.TELEGRAM_WEBHOOK_URL.rsplit("/webhook", 1)[0]
    ea_url = f"{base}/webhook/ea/{token}"

    await message.answer(
        f"*⚙️ EA Monitor Setup*\n\n"
        f"Your EA webhook:\n`{ea_url}`\n\n"
        f"*Option 1 — Python monitor script*\n"
        f"Run on your VPS:\n"
        f"`python scripts/ea_monitor.py --webhook-url {ea_url} --logfile /path/to/EA.log`\n\n"
        f"*Option 2 — MQL5 snippet*\n"
        f"See `scripts/ea_snippet.mq5` — paste `OnTradeTransaction()` into your EA.\n\n"
        f"_Your EA runs on your own account. We only receive completed trade logs._",
        parse_mode="Markdown",
    )


# ─── /add_rule ────────────────────────────────────────────────────────────────

@router.message(Command("add_rule"))
async def cmd_add_rule(message: Message, user: User):
    args = message.text.split(maxsplit=1)
    rule_text = args[1].strip() if len(args) > 1 else ""

    if not rule_text:
        await message.answer(
            "*📝 Add Trading Rule*\n\n"
            "`/add_rule <your rule>`\n\n"
            "*Examples:*\n"
            "• `/add_rule No AMD trades before 10am EST`\n"
            "• `/add_rule Avoid TSLA during earnings week`\n"
            "• `/add_rule Only buy when RSI below 35 AND MACD bullish`",
            parse_mode="Markdown",
        )
        return

    from db.database import AsyncSessionLocal
    from db.models import UserRule
    from ragflow.service import RAGFlowService
    from config.settings import settings as app_settings

    async with AsyncSessionLocal() as db:
        from services.user import UserService
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)

        if not db_user.ragflow_dataset_id:
            ragflow = RAGFlowService(app_settings)
            dataset_id = await ragflow.create_user_dataset(user.telegram_id)
            db_user.ragflow_dataset_id = dataset_id

        rule = UserRule(user_id=db_user.id, rule_text=rule_text)
        db.add(rule)
        await db.flush()
        rule_id = rule.id
        dataset_id = db_user.ragflow_dataset_id

    if dataset_id:
        ragflow = RAGFlowService(app_settings)
        doc_id = await ragflow.add_rule_to_dataset(dataset_id, rule_text, rule_id)
        if doc_id:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                r = await db.execute(select(UserRule).where(UserRule.id == rule_id))
                saved = r.scalar_one_or_none()
                if saved:
                    saved.ragflow_doc_id = doc_id

    await message.answer(
        f"*✅ Rule Added*\n\n`{rule_text}`\n\n"
        f"_Applied to every future validation._",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )


# ─── /my_rules ────────────────────────────────────────────────────────────────

@router.message(Command("my_rules"))
async def cmd_my_rules(message: Message, user: User):
    from db.database import AsyncSessionLocal
    from db.models import UserRule
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserRule)
            .where(UserRule.user_id == user.id, UserRule.is_active == True)
            .order_by(UserRule.created_at.desc())
        )
        rules = result.scalars().all()

    if not rules:
        await message.answer(
            "*📋 No personal rules yet.*\n\n"
            "Add rules with `/add_rule <text>`",
            parse_mode="Markdown",
        )
        return

    lines = [f"*📋 Your {len(rules)} Trading Rules*\n"]
    for i, r in enumerate(rules, 1):
        lines.append(f"{i}. `{r.rule_text}`")
    lines.append("\n_Applied to every validation._")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )


# ─── History callbacks ────────────────────────────────────────────────────────

@router.callback_query(F.data == "view_stats")
async def cb_view_stats(callback: CallbackQuery, user: User):
    from db.database import AsyncSessionLocal
    from sqlalchemy import select, func as sqlfunc, case

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                sqlfunc.count(Validation.id).label("total"),
                sqlfunc.sum(
                    case((Validation.user_outcome == "WIN", 1), else_=0)
                ).label("wins"),
                sqlfunc.sum(
                    case((Validation.user_outcome == "LOSS", 1), else_=0)
                ).label("losses"),
            )
            .where(Validation.user_id == user.id)
        )
        row = result.one()

    total = row.total or 0
    wins = row.wins or 0
    losses = row.losses or 0
    reported = wins + losses
    win_rate = int(wins / reported * 100) if reported > 0 else 0

    await callback.message.answer(
        f"*📊 Your Stats*\n\n"
        f"Total validations: *{total}*\n"
        f"Reported outcomes: *{reported}*\n"
        f"Wins: *{wins}* | Losses: *{losses}*\n"
        f"Win rate: *{win_rate}%*\n\n"
        f"_Report outcomes with `/outcome WIN` or `/outcome LOSS`_",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


# ─── Unhandled callback handlers ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("signal_"))
async def cb_signal_select(callback: CallbackQuery, state: FSMContext, user: User):
    """Handle BUY/SELL/HOLD quick-select buttons from signal_selector keyboard."""
    signal = callback.data.replace("signal_", "")
    await state.update_data(selected_signal=signal)
    await callback.answer(f"Signal set to {signal}")
    # Update the message to show selection
    signal_emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸️"}.get(signal, "")
    await callback.message.edit_text(
        f"Signal selected: {signal_emoji} *{signal}*\n\n"
        f"Now enter the ticker symbol:",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "skip_price")
async def cb_skip_price(callback: CallbackQuery, state: FSMContext, user: User):
    """User skipped price entry — dispatch with price=None."""
    await callback.answer("Using current market price")
    data = await state.get_data()
    ticker = data.get("ticker", "")
    signal = data.get("signal", "BUY")
    if ticker:
        await _dispatch_validation(callback.message, state, user, ticker, signal, None)
    else:
        await callback.message.answer("Please start with /check TICKER SIGNAL")


@router.callback_query(F.data.startswith("share_"))
async def cb_share_result(callback: CallbackQuery, user: User):
    """Share result — forward the analysis message."""
    await callback.answer("Long-press the message above to forward it to others!", show_alert=True)


@router.callback_query(F.data == "clear_history_confirm")
async def cb_clear_history_confirm(callback: CallbackQuery, user: User):
    """Ask confirmation before clearing history."""
    from TG_Bot.keyboards.product_kb import confirm_cancel_keyboard
    await callback.message.answer(
        "⚠️ *Clear all validation history?*\n\n"
        "This removes all your recorded validations from the database. "
        "Your rules and account remain unchanged.",
        parse_mode="Markdown",
        reply_markup=confirm_cancel_keyboard("clear_history"),
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_clear_history")
async def cb_confirm_clear_history(callback: CallbackQuery, user: User):
    """Execute history clear after confirmation."""
    from db.database import AsyncSessionLocal
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(Validation).where(Validation.user_id == user.id)
        )
    await callback.message.edit_text(
        "🗑️ *History cleared.*\n\nAll validation records removed.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer("History cleared")


@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(callback: CallbackQuery):
    """Generic cancel — dismiss the confirmation message."""
    await callback.message.edit_text(
        "↩️ Cancelled.",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "view_usage")
async def cb_view_usage(callback: CallbackQuery, user: User):
    """Show DeepSeek generation usage from account keyboard."""
    from TG_Bot.handlers.generate import cmd_my_usage
    await cmd_my_usage(callback.message, user)
    await callback.answer()


@router.callback_query(F.data == "view_rules")
async def cb_view_rules(callback: CallbackQuery, user: User):
    """Show personal rules from account keyboard."""
    await cmd_my_rules(callback.message, user)
    await callback.answer()


@router.callback_query(F.data == "ea_connect_monitor")
async def cb_ea_connect_monitor(callback: CallbackQuery, user: User):
    """Route EA connect monitor button to /connect_ea handler."""
    await cmd_connect_ea(callback.message, user)
    await callback.answer()


# ─── /link — Connect extension to Telegram account ───────────────────────────

@router.message(Command("link"))
async def cmd_link(message: Message, user: User):
    """
    Link a browser extension user ID to this Telegram account.
    Extension users can find their ID in the extension's Settings panel.

    Usage: /link ext_abc123def456
    """
    args = message.text.split()[1:]

    if not args:
        await message.answer(
            "*🔗 Link Browser Extension*\n\n"
            "This connects your browser extension to your Telegram account "
            "so your personal trading rules apply to screenshot analyses.\n\n"
            "*How to find your extension ID:*\n"
            "1. Click the extension icon in Chrome\n"
            "2. Click ⚙️ Settings\n"
            "3. Copy the *Your User ID* value\n\n"
            "*Then run:*\n"
            "`/link YOUR_USER_ID`",
            parse_mode="Markdown",
        )
        return

    ext_id = args[0].strip()
    if len(ext_id) < 8 or len(ext_id) > 64:
        await message.answer("❌ Invalid extension ID format.")
        return

    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        from services.user import UserService
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        db_user.ext_user_id = ext_id

    await message.answer(
        f"*✅ Extension linked!*\n\n"
        f"Extension ID: `{ext_id}`\n\n"
        f"Your personal trading rules will now apply to all screenshot analyses "
        f"from your browser extension.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )
