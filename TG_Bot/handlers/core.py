"""
TG_Bot/handlers/core.py
Core bot commands for AI Trade Validator.

Commands:
  /start         — Welcome + auto-offer trial to new users
  /help          — Full command list
  /status        — Account status, plan, trial info
  /subscribe     — Show upgrade options with inline buttons
  /my_rules      — List personal trading rules
  /add_rule      — Add a personal rule (FSM)
  /delete_rule   — Delete a rule by number
  /history       — Recent signal validations
  /connect_indicator — Show indicator webhook URL + token
  /connect_ea        — Show EA webhook token
  /connect_extension — Show screenshot webhook token
"""

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from loguru import logger

from db.database import AsyncSessionLocal
from db.models import PlanTier
from services.user import UserService
from config.settings import settings

router = Router()

# ── Plan display names ─────────────────────────────────────────────────────────
PLAN_NAMES = {
    "free":     "Free",
    "trial":    "Trial (14-day)",
    "product1": "Signal Validator ($29/mo)",
    "product2": "EA Analyzer ($49/mo)",
    "product3": "Manual Validator ($19/mo)",
    "pro":      "Pro Bundle ($79/mo)",
}


def _checkout_url(plan_key: str, telegram_id: int) -> str:
    urls = {
        "product1": getattr(settings, "WHOP_PRODUCT1_URL", ""),
        "product2": getattr(settings, "WHOP_PRODUCT2_URL", ""),
        "product3": getattr(settings, "WHOP_PRODUCT3_URL", ""),
        "pro":      getattr(settings, "WHOP_PRO_URL", ""),
    }
    base = urls.get(plan_key, "")
    if not base or "placeholder" in base:
        return ""
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}metadata[telegram_id]={telegram_id}"


def _subscribe_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    rows = []
    plans = [
        ("product1", "📊 Signal Validator — $29/mo"),
        ("product2", "🤖 EA Analyzer — $49/mo"),
        ("product3", "📋 Manual Validator — $19/mo"),
        ("pro",      "⭐ Pro Bundle — $79/mo"),
    ]
    for key, label in plans:
        url = _checkout_url(key, telegram_id)
        if url:
            rows.append([InlineKeyboardButton(text=label, url=url)])
    if not rows:
        rows = [[InlineKeyboardButton(text="Visit Whop", url="https://whop.com")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    name = message.from_user.first_name or "Trader"

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        await user_svc.ensure_all_webhook_tokens(user.id)
        await db.refresh(user)
        trial_status = await user_svc.get_trial_status(telegram_id)

    plan_key = user.plan.value if user.plan else "free"
    is_free  = plan_key == "free"

    welcome = (
        f"👋 Welcome to *AI Trade Validator*, {name}!\n\n"
        "I validate your trade signals using AI + 30+ technical indicators "
        "and 55 chart patterns — before you enter.\n\n"
    )

    if trial_status["active"]:
        days = trial_status["days_remaining"]
        welcome += f"⏳ Trial active — *{days} days* remaining.\n\n"
    elif plan_key != "free":
        welcome += f"✅ Plan: *{PLAN_NAMES.get(plan_key, plan_key)}*\n\n"

    welcome += (
        "📌 *Quick start:*\n"
        "• /connect\\_indicator — get your webhook token\n"
        "• /connect\\_ea — get your EA token\n"
        "• /help — all commands\n"
    )

    if is_free and not trial_status["used"]:
        from TG_Bot.handlers.trial import _trial_keyboard
        await message.answer(welcome, parse_mode="Markdown")
        await message.answer(
            "🎁 *Start your free 14-day trial*\n\n"
            "Full access to all products — no credit card needed.",
            parse_mode="Markdown",
            reply_markup=_trial_keyboard(telegram_id),
        )
    else:
        await message.answer(welcome, parse_mode="Markdown")


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 *AI Trade Validator — Commands*\n\n"
        "📊 *Validation*\n"
        "/status — Account & plan info\n"
        "/history — Recent signal history\n\n"
        "⚙️ *Setup*\n"
        "/connect\\_indicator — Indicator webhook token\n"
        "/connect\\_ea — EA analyzer webhook token\n"
        "/connect\\_extension — Screenshot webhook token\n"
        "/tokens — View all webhook tokens at once\n\n"
        "📋 *Personal Rules*\n"
        "/my\\_rules — View your trading rules\n"
        "/add\\_rule — Add a new rule\n"
        "/delete\\_rule — Remove a rule\n\n"
        "💳 *Subscription*\n"
        "/trial — Start or check your 14-day free trial\n"
        "/subscribe — View plans and upgrade\n\n"
        "🏗️ *App Builder*\n"
        "/build — Build your trading app with AI\n\n"
        "/help — Show this message",
        parse_mode="Markdown",
    )


# ── /status ───────────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        trial_status = await user_svc.get_trial_status(telegram_id)

        from sqlalchemy import select, func
        from db.models import Validation
        val_count = await db.scalar(
            select(func.count(Validation.id)).where(Validation.user_id == user.id)
        )

    plan_key  = user.plan.value if user.plan else "free"
    plan_name = PLAN_NAMES.get(plan_key, plan_key)

    lines = [f"📊 *Your Account*\n"]

    # Plan / trial
    if trial_status["active"]:
        days = trial_status["days_remaining"]
        exp  = user.trial_expires_at.strftime("%b %d, %Y") if user.trial_expires_at else "—"
        lines.append(f"⏳ *Plan:* Trial — {days} day{'s' if days != 1 else ''} left (expires {exp})")
    else:
        lines.append(f"💳 *Plan:* {plan_name}")
        if user.plan_expires_at:
            lines.append(f"   Renews: {user.plan_expires_at.strftime('%b %d, %Y')}")

    lines.append(f"\n📈 *Validations run:* {val_count or 0}")
    lines.append(f"🆔 *Telegram ID:* `{telegram_id}`")

    # Access summary
    products = []
    for i in range(1, 4):
        if user.has_product_access(i):
            names = {1: "Signal Validator", 2: "EA Analyzer", 3: "Manual Validator"}
            products.append(names[i])
    if products:
        lines.append(f"\n✅ *Access:* {', '.join(products)}")
    else:
        lines.append("\n🔒 No active product access")

    text = "\n".join(lines)

    if plan_key == "free" and not trial_status["active"]:
        await message.answer(
            text, parse_mode="Markdown",
            reply_markup=_subscribe_keyboard(telegram_id),
        )
    else:
        await message.answer(text, parse_mode="Markdown")


# ── /subscribe ────────────────────────────────────────────────────────────────

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    telegram_id = message.from_user.id
    await message.answer(
        "💳 *Upgrade your plan*\n\n"
        "Choose the plan that fits your trading style:\n\n"
        "📊 *Signal Validator* — $29/mo\n"
        "Validate signals from TradingView, indicators, webhooks\n\n"
        "🤖 *EA Analyzer* — $49/mo\n"
        "AI analysis on every MT4/MT5/cTrader trade\n\n"
        "📋 *Manual Validator* — $19/mo\n"
        "Screenshot + AI analysis via browser extension\n\n"
        "⭐ *Pro Bundle* — $79/mo\n"
        "All three products + App Builder",
        parse_mode="Markdown",
        reply_markup=_subscribe_keyboard(telegram_id),
    )


# ── /history ──────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        from sqlalchemy import select, desc
        from db.models import Validation
        res = await db.execute(
            select(Validation)
            .where(Validation.user_id == user.id)
            .order_by(desc(Validation.created_at))
            .limit(10)
        )
        validations = res.scalars().all()

    if not validations:
        await message.answer(
            "📭 No validations yet.\n\n"
            "Connect your platform via /connect\\_indicator or /connect\\_ea to get started.",
            parse_mode="Markdown",
        )
        return

    lines = ["📊 *Recent Validations* (last 10)\n"]
    verdict_emoji = {"CONFIRM": "✅", "REJECT": "❌", "CAUTION": "⚠️"}

    for v in validations:
        emoji  = verdict_emoji.get(v.verdict or "", "•")
        signal = v.signal.value if v.signal else "—"
        conf   = f"{v.confidence_score*100:.0f}%" if v.confidence_score else "—"
        dt     = v.created_at.strftime("%b %d %H:%M") if v.created_at else "—"
        lines.append(f"{emoji} *{v.ticker}* {signal} — {v.verdict or 'pending'} ({conf}) · _{dt}_")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── /connect_indicator ────────────────────────────────────────────────────────

@router.message(Command("connect_indicator"))
async def cmd_connect_indicator(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        await user_svc.ensure_all_webhook_tokens(user.id)
        await db.refresh(user)

    token   = user.indicator_webhook_token or "—"
    api_base = getattr(settings, "API_BASE_URL", "https://your-domain.com").rstrip("/")
    url      = f"{api_base}/webhook/indicator/{token}"

    await message.answer(
        "📊 *Indicator / TradingView Webhook*\n\n"
        "Paste this URL into your TradingView alert or indicator webhook:\n\n"
        f"`{url}`\n\n"
        "Or use just the token if your platform asks for it separately:\n\n"
        f"Token: `{token}`\n\n"
        "📖 *Payload format:*\n"
        "```json\n"
        '{\n'
        '  "token": "YOUR_TOKEN",\n'
        '  "ticker": "EURUSD",\n'
        '  "signal": "BUY",\n'
        '  "price": 1.0850\n'
        '}\n'
        "```",
        parse_mode="Markdown",
    )


# ── /connect_ea ───────────────────────────────────────────────────────────────

@router.message(Command("connect_ea"))
async def cmd_connect_ea(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        await user_svc.ensure_all_webhook_tokens(user.id)
        await db.refresh(user)

    token    = user.ea_webhook_token or "—"
    api_base = getattr(settings, "API_BASE_URL", "https://your-domain.com").rstrip("/")
    url      = f"{api_base}/api/ohlc/analyze"

    await message.answer(
        "🤖 *EA Analyzer Token*\n\n"
        "Paste this token into your MT4/MT5/cTrader EA:\n\n"
        f"`{token}`\n\n"
        f"The EA will POST candle data to:\n`{url}`\n\n"
        "📥 Download your EA from the Signal Validator → Setup tab in the Mini App.\n\n"
        "Use /tokens to see all your tokens at once.",
        parse_mode="Markdown",
    )


# ── /connect_extension ────────────────────────────────────────────────────────

@router.message(Command("connect_extension"))
async def cmd_connect_extension(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        await user_svc.ensure_all_webhook_tokens(user.id)
        await db.refresh(user)

    token = user.screenshot_webhook_token or "—"
    await message.answer(
        "🖥️ *Chrome Extension Token*\n\n"
        "Install the ATV Chrome extension, then paste this token in the Settings tab:\n\n"
        f"`{token}`\n\n"
        "The extension will capture candle-close screenshots and send them for AI analysis.\n\n"
        "Use /tokens to see all your tokens at once.",
        parse_mode="Markdown",
    )


# ── /my_rules ─────────────────────────────────────────────────────────────────

@router.message(Command("my_rules"))
async def cmd_my_rules(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        from db.models import UserRule
        from sqlalchemy import select
        res = await db.execute(
            select(UserRule)
            .where(UserRule.user_id == user.id, UserRule.is_active == True)
            .order_by(UserRule.created_at)
        )
        rules = res.scalars().all()

    if not rules:
        await message.answer(
            "📭 You have no personal rules yet.\n\n"
            "Use /add\\_rule to add your first rule.\n\n"
            "Example: `/add\\_rule Never trade EURUSD before 8am London open`",
            parse_mode="Markdown",
        )
        return

    lines = [f"📋 *Your Personal Trading Rules* ({len(rules)})\n"]
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {rule.rule_text}")
    lines.append("\nUse /delete\\_rule \\<number\\> to remove a rule.")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── /add_rule FSM ─────────────────────────────────────────────────────────────

class AddRuleFSM(StatesGroup):
    waiting_rule_text = State()


@router.message(Command("add_rule"))
async def cmd_add_rule_start(message: Message, state: FSMContext):
    # Check if rule was passed inline: /add_rule text here
    args = message.text.split(None, 1)
    if len(args) > 1 and len(args[1].strip()) >= 5:
        await _save_rule(message, args[1].strip())
        return

    await message.answer(
        "📝 *Add a personal trading rule*\n\n"
        "Type your rule in plain English. Examples:\n"
        "• _Never trade during news events_\n"
        "• _Only take BUY signals when price is above the 200 EMA_\n"
        "• _Max 2 trades per day on EURUSD_\n\n"
        "Type your rule now, or /cancel to abort:",
        parse_mode="Markdown",
    )
    await state.set_state(AddRuleFSM.waiting_rule_text)


@router.message(AddRuleFSM.waiting_rule_text)
async def fsm_rule_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == "/cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=ReplyKeyboardRemove())
        return
    if len(text) < 5:
        await message.answer("Rule is too short. Be more specific:")
        return
    await state.clear()
    await _save_rule(message, text)


async def _save_rule(message: Message, rule_text: str):
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user     = await user_svc.get_or_create_user(telegram_id=telegram_id)
        await user_svc.add_personal_rule(user.id, rule_text)
        await db.commit()

    await message.answer(
        f"✅ *Rule saved!*\n\n_{rule_text}_\n\nUse /my\\_rules to see all your rules.",
        parse_mode="Markdown",
    )


# ── /delete_rule ──────────────────────────────────────────────────────────────

@router.message(Command("delete_rule"))
async def cmd_delete_rule(message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Usage: /delete\\_rule \\<number\\>\n\nUse /my\\_rules to see the numbered list.",
            parse_mode="Markdown",
        )
        return

    rule_number = int(args[1].strip())
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user     = await user_svc.get_or_create_user(telegram_id=telegram_id)

        from db.models import UserRule
        from sqlalchemy import select
        res = await db.execute(
            select(UserRule)
            .where(UserRule.user_id == user.id, UserRule.is_active == True)
            .order_by(UserRule.created_at)
        )
        rules = res.scalars().all()

        if rule_number < 1 or rule_number > len(rules):
            await message.answer(
                f"❌ Rule #{rule_number} not found. You have {len(rules)} rule(s).\n"
                "Use /my\\_rules to see the list.",
                parse_mode="Markdown",
            )
            return

        target = rules[rule_number - 1]
        rule_text = target.rule_text
        target.is_active = False
        await db.commit()

    await message.answer(
        f"🗑️ Rule #{rule_number} deleted.\n\n"
        f"_\"{rule_text}\"_",
        parse_mode="Markdown",
    )
