"""
TG_Bot/handlers/start.py — /start command and main menu routing.

Handles:
  /start            — Welcome message + main menu keyboard
  Menu button taps  — Route to correct product handler
  /help             — Full command reference
  /status           — Account overview
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from TG_Bot.keyboards.main_menu import main_menu_keyboard
from TG_Bot.keyboards.product_kb import account_keyboard, subscription_plans_keyboard, back_to_menu_keyboard
from db.models import User, PlanTier
from config.settings import settings

router = Router(name="start")


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User):
    await state.clear()  # Reset any active FSM state

    name = message.from_user.first_name or "Trader"
    plan_emoji = {"free": "🆓", "product1": "1️⃣", "product2": "2️⃣",
                  "product3": "3️⃣", "pro": "⭐"}.get(user.plan.value, "🆓")

    text = (
        f"👋 *Welcome to AI Trade Validator, {name}!*\n\n"
        f"I use two AI systems to validate your trades:\n"
        f"• 🤖 *OpenTrade.ai* — Technical analysis (RSI, MACD, Bollinger Bands)\n"
        f"• 📚 *RAGFlow* — Rules & historical pattern matching\n\n"
        f"Your plan: {plan_emoji} *{user.plan.value.upper()}*\n\n"
        f"*Choose a product below or use these free tools:*\n"
        f"• 🆓 `/generate` — English → Pine Script\n"
        f"• 🆓 `/generate_ea` — English → MQL5 EA\n\n"
        f"_Use the menu buttons below to get started._"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


# ─── Menu button routing ───────────────────────────────────────────────────────

@router.message(F.text == "📊 Indicator Validator")
async def menu_indicator(message: Message, user: User):
    from TG_Bot.keyboards.strategy_kb import strategy_selector
    text = (
        "*📊 Indicator Validator*\n\n"
        "Choose how you want to connect your TradingView indicator:\n\n"
        "🔌 *Webhook* — Requires paid TradingView ($15-30/mo)\n"
        "📄 *Share Code* — Free! Paste your Pine Script source\n"
        "🤖 *AI Generate* — Free! Describe your strategy in English\n\n"
        "_All three methods feed into the same AI validation pipeline._"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=strategy_selector())


@router.message(F.text == "🤖 EA Analyzer")
async def menu_ea(message: Message, user: User):
    from TG_Bot.keyboards.strategy_kb import ea_entry_selector
    text = (
        "*🤖 EA Analyzer*\n\n"
        "Monitor your Expert Advisor and get AI explanations for every win/loss.\n\n"
        "📡 *Connect Monitor* — Install our script on your VPS (Paid)\n"
        "🤖 *Generate EA* — Free! We'll write the MQL5 code for you\n\n"
        "_Your EA runs on your own account. We only receive trade logs._"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=ea_entry_selector())


@router.message(F.text == "🔍 Manual Check")
async def menu_manual(message: Message, user: User):
    from TG_Bot.handlers.validate import start_manual_check
    await start_manual_check(message, user)


@router.message(F.text == "🆓 Free Generator")
async def menu_generator(message: Message, user: User):
    text = (
        "*🆓 Free AI Code Generator*\n\n"
        "Generate trading code from plain English — completely free:\n\n"
        "📈 `/generate <strategy>` — Pine Script v6 for TradingView\n"
        "⚙️ `/generate_ea <strategy>` — MQL5 EA for MetaTrader 5\n\n"
        "*Examples:*\n"
        "• `/generate Buy when RSI below 30 and volume above average`\n"
        "• `/generate_ea Scalp 5 pip TP, 10 pip SL on EURUSD M1`\n\n"
        f"_Free budget: $5/user (~2,500 generations)_\n"
        f"_Use /my_usage to see how much you\\'ve used._"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(F.text == "⚙️ My Account")
async def menu_account(message: Message, user: User):
    from datetime import date
    plan_emoji = {"free": "🆓", "product1": "1️⃣", "product2": "2️⃣",
                  "product3": "3️⃣", "pro": "⭐"}.get(user.plan.value, "🆓")

    daily_used = user.daily_validation_count if user.daily_validation_date == date.today() else 0
    daily_limit = settings.FREE_TIER_DAILY_LIMIT if user.plan == PlanTier.FREE else "∞"
    spent = user.total_generation_cost or 0.0
    gens = user.total_generations or 0

    expires = ""
    if user.plan_expires_at:
        expires = f"\n📅 Renews: {user.plan_expires_at.strftime('%Y-%m-%d')}"

    text = (
        f"*⚙️ My Account*\n\n"
        f"Plan: {plan_emoji} *{user.plan.value.upper()}*{expires}\n\n"
        f"*Usage today:* {daily_used}/{daily_limit} validations\n"
        f"*Free generations used:* {gens} (${spent:.3f} / $5.00)\n\n"
        f"*Connections:*\n"
        f"• Indicator webhook: {'✅' if user.indicator_webhook_token else '❌ Not set up'}\n"
        f"• EA webhook: {'✅' if user.ea_webhook_token else '❌ Not set up'}\n"
        f"• RAGFlow KB: {'✅' if user.ragflow_dataset_id else '❌ Not set up'}"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=account_keyboard(user.plan.value),
    )


@router.message(F.text == "❓ Help")
async def menu_help(message: Message):
    await cmd_help(message)


# ─── /help ────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "*🤖 AI Trade Validator — All Commands*\n\n"
        "*🆓 Free for everyone:*\n"
        "`/generate <strategy>` — English → Pine Script v6\n"
        "`/generate_ea <strategy>` — English → MQL5 EA\n"
        "`/share_code` — Paste your Pine Script source\n"
        "`/my_usage` — View free generation budget\n\n"
        "*📈 Trading (Paid plans):*\n"
        "`/check TICKER SIGNAL [PRICE]` — Validate a trade\n"
        "`/outcome WIN|LOSS [#id]` — Report trade result\n\n"
        "*📚 Knowledge Base:*\n"
        "`/add_rule <text>` — Add personal trading rule\n"
        "`/my_rules` — List your rules\n\n"
        "*📊 History & Stats:*\n"
        "`/history` — Last 10 validations\n"
        "`/insights` — Crowd win-rate stats ⭐ Pro\n\n"
        "*⚙️ Integrations:*\n"
        "`/connect_indicator` — TradingView webhook URL\n"
        "`/connect_ea` — EA monitoring script\n\n"
        "*💳 Account:*\n"
        "`/status` — Plan & usage\n"
        "`/subscribe` — Upgrade via Whop"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())


# ─── /status ──────────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message, user: User):
    await menu_account(message, user)


# ─── Callback: back to menu ───────────────────────────────────────────────────

@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "🏠 Back to main menu.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "show_plans")
async def cb_show_plans(callback: CallbackQuery, user: User):
    from TG_Bot.handlers.subscription import show_subscription_plans
    await show_subscription_plans(callback.message, user)
    await callback.answer()
