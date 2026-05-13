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
    """Ask the user to choose a platform before showing webhook setup."""
    from TG_Bot.keyboards.strategy_kb import webhook_platform_selector

    await message.answer(
        "*🔌 Connect Indicator Webhook*\n\n"
        "Choose your preferred platform first:",
        parse_mode="Markdown",
        reply_markup=webhook_platform_selector(),
    )


async def _get_indicator_webhook_url(user: User) -> str | None:
    if user.plan not in (PlanTier.PRODUCT1, PlanTier.PRO):
        return None

    from services.user import UserService
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        token = await user_svc.get_or_create_webhook_token(db_user, "indicator")

    base = settings.TELEGRAM_WEBHOOK_URL.rsplit("/webhook", 1)[0]
    return f"{base}/webhook/indicator/{token}"


async def _send_webhook_locked_message(message: Message, user: User):
    await message.answer(
        "🔒 *Webhook connection* requires *Product 1* ($19/mo) or *Pro* ($79/mo).\n\n"
        "Use /subscribe to upgrade, or try the free options:\n"
        "📄 Share Source Code or 🤖 AI Generate (no subscription needed).",
        parse_mode="Markdown",
        reply_markup=subscription_plans_keyboard(user.plan.value),
    )


async def _send_platform_webhook_setup(message: Message, user: User, platform: str):
    webhook_url = await _get_indicator_webhook_url(user)
    if not webhook_url:
        await _send_webhook_locked_message(message, user)
        return
    mt4_link = settings.MT4_DOWNLOAD_URL or "#"
    mt5_link = settings.MT5_DOWNLOAD_URL or "#"

    platform_text = {
        "tradingview": (
            "*📊 TradingView Webhook Setup*\n\n"
            f"Your webhook URL:\n`{webhook_url}`\n\n"
            "*Steps:*\n"
            "1. Open your indicator and create an alert.\n"
            "2. Enable *Webhook URL* and paste the link above.\n"
            "3. Set the alert message to:\n\n"
            "```json\n"
            "{\n"
            '  "ticker": "{{ticker}}",\n'
            '  "signal": "BUY",\n'
            '  "price": {{close}},\n'
            '  "indicator": "MyIndicator"\n'
            "}\n"
            "```\n\n"
            "_Replace `BUY` with your signal variable or alert output._"
        ),
        "metatrader": (
            "*🤖 MetaTrader Webhook Setup*\n\n"
            f"Your webhook URL:\n`{webhook_url}`\n\n"
            "*Steps:*\n"
            "1. Copy your special webhook URL.\n"
            "2. Upload screenshots from your indicator.\n"
            "3. Explain your indicator to the system.\n"
            f"4. Download [MT4 (.ex4)]({mt4_link}) or [MT5 (.ex5)]({mt5_link}).\n"
            "5. Attach the Expert Advisor to your chart.\n"
            "6. Go to Tools -> Options -> Expert Advisors and enable Allow automated trading plus Allow WebRequest for listed URLs.\n"
            f"7. Add this URL to the allowed list: `{webhook_url}`\n"
            "8. Right-click chart -> Expert Advisors -> Properties -> Inputs and set WebhookURL plus SignalDescription.\n"
            "9. Set SignalDescription to: Green arrow = BUY, Red arrow = SELL, Blue line = TP, Orange line = SL.\n"
            "10. Choose the desired chart timeframe, then click OK.\n\n"
            "_If the MT4/MT5 links are placeholders, set MT4_DOWNLOAD_URL and MT5_DOWNLOAD_URL in the app environment._"
        ),
        "ctrader": (
            "*📈 cTrader Webhook Setup*\n\n"
            f"Your webhook URL:\n`{webhook_url}`\n\n"
            "*Steps:*\n"
            "1. Open your cBot or indicator logic.\n"
            "2. Add an HTTP POST call that sends alerts to the webhook URL above.\n"
            "3. Include ticker, signal, price, and indicator fields in the JSON body.\n\n"
            "_This works for cTrader setups that support outbound web requests._"
        ),
        "matchtrader": (
            "*⚡ MatchTrader Webhook Setup*\n\n"
            f"Your webhook URL:\n`{webhook_url}`\n\n"
            "*Steps:*\n"
            "1. Open your MatchTrader webhook or automation settings.\n"
            "2. Paste the webhook URL above.\n"
            "3. Map your alert fields to ticker, signal, price, and indicator name.\n\n"
            "_Use your platform’s webhook feature to forward each alert to our system._"
        ),
        "daxtrader": (
            "*💹 DAX Trader Webhook Setup*\n\n"
            f"Your webhook URL:\n`{webhook_url}`\n\n"
            "*Steps:*\n"
            "1. Open DAX Trader alert settings.\n"
            "2. Add the webhook URL above to your outgoing alert action.\n"
            "3. Send your symbol, side, price, and indicator name in the payload.\n\n"
            "_Once connected, our system responds to each alert automatically._"
        ),
        "takeprofit": (
            "*🎯 TakeProfit.com Webhook Setup*\n\n"
            f"Your webhook URL:\n`{webhook_url}`\n\n"
            "*Steps:*\n"
            "1. Copy your webhook URL.\n"
            "2. Attach your indicator.\n"
            "3. Click the bell icon.\n"
            "4. Set the source to your indicator.\n"
            "5. Click Expand.\n"
            "6. Set frequency to Every Trigger.\n"
            "7. Paste your webhook URL into the Webhook field.\n"
            "8. In the Message field, explain your indicator logic using the JSON format shown below.\n\n"
            "```json\n"
            "{\n"
            '  "ticker": "EURUSD",\n'
            '  "signal": "BUY",\n'
            '  "price": 1.0845,\n'
            '  "indicator": "MyIndicator",\n'
            '  "timeframe": "H1",\n'
            '  "logic": "Green arrow = BUY, Red arrow = SELL, Blue line = TP, Orange line = SL"\n'
            "}\n"
            "```\n\n"
            "_Every alert sent there will be analyzed by Indicator Validator._"
        ),
    }

    await message.answer(
        platform_text[platform],
        parse_mode="Markdown",
        reply_markup=_webhook_platform_back_keyboard(),
    )

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


# ─── Platform selection callbacks ─────────────────────────────────────────────

@router.callback_query(F.data == "back_to_platforms")
async def cb_back_to_platforms(callback: CallbackQuery, user: User):
    from TG_Bot.keyboards.strategy_kb import platform_selector
    await callback.answer()
    await callback.message.edit_text(
        "*📊 Indicator Validator*\n\nSelect your trading platform:",
        parse_mode="Markdown",
        reply_markup=platform_selector(),
    )


@router.callback_query(F.data == "back_to_webhook_platforms")
async def cb_back_to_webhook_platforms(callback: CallbackQuery, user: User):
    from TG_Bot.keyboards.strategy_kb import webhook_platform_selector
    await callback.answer()
    await callback.message.edit_text(
        "*🔌 Connect Indicator Webhook*\n\n"
        "Choose your preferred platform first:",
        parse_mode="Markdown",
        reply_markup=webhook_platform_selector(),
    )


@router.callback_query(F.data.startswith("webhook_platform_"))
async def cb_webhook_platform(callback: CallbackQuery, user: User):
    platform = callback.data.replace("webhook_platform_", "")
    await callback.answer()
    await _send_platform_webhook_setup(callback.message, user, platform)


@router.callback_query(F.data == "platform_tradingview")
async def cb_platform_tradingview(callback: CallbackQuery, user: User):
    from TG_Bot.keyboards.strategy_kb import strategy_selector
    await callback.answer()
    await callback.message.edit_text(
        _indicator_options_text(),
        parse_mode="Markdown",
        reply_markup=strategy_selector(),
    )


@router.callback_query(F.data == "platform_metatrader")
async def cb_platform_metatrader(callback: CallbackQuery, user: User):
    from TG_Bot.keyboards.strategy_kb import platform_coming_soon
    await callback.answer()
    await callback.message.edit_text(
        "*🤖 MetaTrader (MT4/MT5) Indicator*\n\n"
        "Connect your MetaTrader indicator via our EA monitor:\n\n"
        "1️⃣ Download our MT4/MT5 indicator file\n"
        "2️⃣ Install it in MetaEditor\n"
        "3️⃣ It sends signals here automatically\n\n"
        "Use /connect_indicator to get your personal webhook URL.\n\n"
        "_Works with any MT4/MT5 broker._",
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "platform_ctrader")
async def cb_platform_ctrader(callback: CallbackQuery, user: User):
    await callback.answer()
    await callback.message.edit_text(
        "*📈 cTrader Indicator*\n\n"
        "Connect your cTrader cBot or indicator:\n\n"
        "1️⃣ Get your webhook URL via /connect_indicator\n"
        "2️⃣ Add our HTTP request call to your cAlgo indicator\n"
        "3️⃣ Signals are validated automatically\n\n"
        "_Compatible with all cTrader brokers._",
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "platform_takeprofit")
async def cb_platform_takeprofit(callback: CallbackQuery, user: User):
    await callback.answer()
    await callback.message.edit_text(
        "*🎯 TakeProfit.com Indicator*\n\n"
        "Connect your TakeProfit.com strategy:\n\n"
        "1️⃣ Get your webhook URL via /connect_indicator\n"
        "2️⃣ Add it as a notification webhook in TakeProfit.com\n"
        "3️⃣ Every signal gets AI-validated instantly\n\n"
        "_Works with TakeProfit.com alert webhooks._",
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "platform_matchtrader")
async def cb_platform_matchtrader(callback: CallbackQuery, user: User):
    await callback.answer()
    await callback.message.edit_text(
        "*⚡ MatchTrader Indicator*\n\n"
        "Connect your MatchTrader strategy:\n\n"
        "1️⃣ Get your webhook URL via /connect_indicator\n"
        "2️⃣ Configure it in your MatchTrader webhook settings\n"
        "3️⃣ Signals validated in real-time\n\n"
        "_Compatible with all MatchTrader prop firms._",
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "platform_daxtrader")
async def cb_platform_daxtrader(callback: CallbackQuery, user: User):
    await callback.answer()
    await callback.message.edit_text(
        "*💹 DAX Trader Indicator*\n\n"
        "Connect your DAX Trader indicator:\n\n"
        "1️⃣ Get your webhook URL via /connect_indicator\n"
        "2️⃣ Add webhook in DAX Trader alert settings\n"
        "3️⃣ AI validates every signal automatically\n\n"
        "_Works with DAX Trader alert system._",
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


def _back_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Back to Platforms", callback_data="back_to_platforms")
    ]])


def _webhook_platform_back_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Back to Platform Choice", callback_data="back_to_webhook_platforms")
    ]])


def _indicator_options_text() -> str:
    return (
        "*📊 Indicator Validator*\n\n"
        "Choose how you want to use Indicator Validator:\n\n"
        "*1. Connect Indicator Webhook*\n"
        "_System responds based on your favorite indicator alerts._\n\n"
        "*2. Share Source Code*\n"
        "_You will get a JSON file that you paste to our bridge indicator so it can rebuild your indicator and connect without needing a paid TradingView plan._\n\n"
        "*3. Get Bridge Indicator*\n"
        "_Turn any strategy into an indicator or visualize your Pine Script after you get the JSON version of it._\n\n"
        "*4. Get Our Indicator*\n"
        "_Let our AI monitor and analyze chart patterns for you, including SMC and ICT patterns, market structure, time and session analysis, classical patterns, strategy models, and key levels according to your strategy._\n\n"
        "*5. Get Browser Extension*\n"
        "_Do exactly what our indicator does, but based on screenshots you provide instead of monitoring the market live._"
    )
