"""
TG_Bot/handlers/subscription.py

Handles:
  /subscribe   — Show Whop plan selection
  /insights    — Crowd win-rate stats (Pro only)
  Callbacks    — subscribe_*, compare_plans, cancel_subscription
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from TG_Bot.keyboards.product_kb import (
    subscription_plans_keyboard, back_to_menu_keyboard, confirm_cancel_keyboard,
)
from TG_Bot.keyboards.main_menu import main_menu_keyboard
from db.models import User, PlanTier

router = Router(name="subscription")

PLAN_NAMES = {
    "product1": "Indicator Validator ($19/mo)",
    "product2": "EA Analyzer ($49/mo)",
    "product3": "Manual Validator ($19/mo)",
    "pro":      "Pro Bundle ($79/mo)",
}

PLAN_FEATURES = {
    "product1": (
        "✓ Unlimited TradingView webhook validations\n"
        "✓ Share Pine Script source code storage\n"
        "✓ Personal trading rules in RAGFlow\n"
        "✓ AI signal confidence scores"
    ),
    "product2": (
        "✓ EA trade log monitoring\n"
        "✓ Win/loss AI explanations\n"
        "✓ Improvement suggestions\n"
        "✓ MQL5 code generator (already free)"
    ),
    "product3": (
        "✓ Unlimited /check commands\n"
        "✓ Full OpenTrade.ai technical analysis\n"
        "✓ RAGFlow mentor validation\n"
        "✓ Live Polygon.io market data"
    ),
    "pro": (
        "✓ Everything in all 3 products\n"
        "✓ Priority processing queue\n"
        "✓ Crowd insights (win-rate analytics)\n"
        "✓ Unlimited AI code generation"
    ),
}


# ─── /subscribe ───────────────────────────────────────────────────────────────

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, user: User):
    await show_subscription_plans(message, user)


async def show_subscription_plans(message: Message, user: User):
    plan_emoji = {
        "free": "🆓", "product1": "1️⃣",
        "product2": "2️⃣", "product3": "3️⃣", "pro": "⭐",
    }
    current = plan_emoji.get(user.plan.value, "🆓")

    text = (
        f"*💳 Subscription Plans*\n\n"
        f"Current plan: {current} *{user.plan.value.upper()}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ *Indicator Validator* — $19/mo\n"
        f"{PLAN_FEATURES['product1']}\n\n"
        f"2️⃣ *EA Analyzer* — $49/mo\n"
        f"{PLAN_FEATURES['product2']}\n\n"
        f"3️⃣ *Manual Validator* — $19/mo\n"
        f"{PLAN_FEATURES['product3']}\n\n"
        f"⭐ *Pro Bundle* — $79/mo\n"
        f"{PLAN_FEATURES['pro']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆓 `/generate` and `/generate_ea` are *always free*\n\n"
        f"Payment via *Whop* — 241 territories, instant activation:"
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=subscription_plans_keyboard(user.plan.value),
    )


# ─── Subscribe callbacks ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("subscribe_"))
async def cb_subscribe(callback: CallbackQuery, user: User):
    plan_id = callback.data.replace("subscribe_", "")

    from services.subscription import WhopService
    whop = WhopService()
    checkout_url = whop.get_checkout_url(plan=plan_id, telegram_id=user.telegram_id)

    if checkout_url:
        await callback.message.answer(
            f"*💳 Complete Your Subscription*\n\n"
            f"Plan: *{PLAN_NAMES.get(plan_id, plan_id)}*\n\n"
            f"[👉 Subscribe via Whop]({checkout_url})\n\n"
            f"_Whop supports credit cards, crypto & bank transfers in 241 territories. "
            f"Your plan activates instantly after payment._",
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=back_to_menu_keyboard(),
        )
    else:
        await callback.message.answer(
            "❌ Could not generate checkout link.\n"
            "Whop product IDs may not be configured yet. Please contact support.",
            reply_markup=back_to_menu_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "compare_plans")
async def cb_compare_plans(callback: CallbackQuery, user: User):
    text = (
        "*📊 Plan Comparison*\n\n"
        "| Feature | Free | P1 | P2 | P3 | Pro |\n"
        "|---|---|---|---|---|---|\n"
        "| Pine Script generator | ✅ | ✅ | ✅ | ✅ | ✅ |\n"
        "| MQL5 generator | ✅ | ✅ | ✅ | ✅ | ✅ |\n"
        "| Webhook validation | ❌ | ✅ | ❌ | ❌ | ✅ |\n"
        "| EA log analysis | ❌ | ❌ | ✅ | ❌ | ✅ |\n"
        "| Manual /check | 5/day | ❌ | ❌ | ✅ | ✅ |\n"
        "| Crowd insights | ❌ | ❌ | ❌ | ❌ | ✅ |\n\n"
        "_All paid plans include personal RAGFlow KB_"
    )
    await callback.message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=subscription_plans_keyboard(user.plan.value),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_subscription")
async def cb_cancel_subscription_prompt(callback: CallbackQuery):
    await callback.message.answer(
        "⚠️ *Cancel Subscription*\n\n"
        "Are you sure? You'll lose access at the end of your billing period.\n\n"
        "_To cancel, visit your Whop dashboard: https://whop.com/dashboard_\n\n"
        "Your data and rules are always preserved.",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ─── /insights ────────────────────────────────────────────────────────────────

@router.message(Command("insights"))
async def cmd_insights(message: Message, user: User):
    if user.plan != PlanTier.PRO:
        await message.answer(
            "*🔒 Crowd Insights — Pro Feature*\n\n"
            "Crowd Insights shows anonymized win-rate data from all users:\n\n"
            "_\"When AI verdict is CONFIRM on a BUY, users win 71% of the time\"_\n\n"
            "Available on *Pro Bundle* ($79/mo).\n"
            "Use /subscribe to upgrade.",
            parse_mode="Markdown",
            reply_markup=subscription_plans_keyboard(user.plan.value),
        )
        return

    from db.database import AsyncSessionLocal
    from db.models import Validation, ValidationStatus
    from sqlalchemy import select, func as sqlfunc, case

    async with AsyncSessionLocal() as db:
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
        await message.answer(
            "*📊 Crowd Insights*\n\n"
            "_Not enough data yet. Insights update weekly._\n\n"
            "Help build the dataset:\n"
            "`/outcome WIN` or `/outcome LOSS` after each trade.",
            parse_mode="Markdown",
        )
        return

    lines = ["*📊 Crowd Insights — Community Win Rates*\n"]
    has_data = False
    for row in rows:
        if (row.total or 0) < 5:
            continue
        has_data = True
        win_rate = (row.wins or 0) / row.total * 100
        emoji = "✅" if win_rate >= 60 else ("⚠️" if win_rate >= 45 else "❌")
        sig = row.signal.value if hasattr(row.signal, "value") else str(row.signal)
        lines.append(
            f"{emoji} AI *{row.verdict}* + *{sig}*: "
            f"{win_rate:.0f}% win rate ({row.total} trades)"
        )

    if not has_data:
        lines.append("_Need 5+ trades per category. Keep reporting outcomes!_")

    lines.append("\n_Anonymized data. Updated every Sunday at 2am UTC._")
    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data == "confirm_cancel_subscription")
async def cb_confirm_cancel_subscription(callback: CallbackQuery, user: User):
    """User confirmed cancellation — direct them to Whop dashboard."""
    await callback.message.edit_text(
        "*ℹ️ How to cancel your subscription:*\n\n"
        "1. Go to [whop.com/dashboard](https://whop.com/dashboard)\n"
        "2. Find *AI Trade Validator* under your memberships\n"
        "3. Click *Cancel membership*\n\n"
        "_Your access continues until the end of the current billing period. "
        "Your rules and history are always preserved._",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()
