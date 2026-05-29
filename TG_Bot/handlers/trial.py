"""
TG_Bot/handlers/trial.py
New handler file — register in TG_Bot/main.py dispatcher.

Handles:
  /trial        — show trial status or start a trial
  /start        — extended to auto-offer trial to new FREE users
  callback: trial_start  — inline button to confirm trial start
  callback: trial_upgrade — redirect to Whop purchase
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger

from db.database import AsyncSessionLocal
from services.user import UserService
from db.models import PlanTier
from config.settings import settings

router = Router()

TRIAL_DURATION_DAYS = 14

# ── Whop checkout URLs — set these in your .env ────────────────────────────────
# WHOP_PRODUCT1_URL, WHOP_PRODUCT2_URL, WHOP_PRODUCT3_URL, WHOP_PRO_URL
# Each URL should include ?metadata[telegram_id]={telegram_id} appended at runtime


def _checkout_url(plan_key: str, telegram_id: int) -> str:
    urls = {
        "product1": getattr(settings, "WHOP_PRODUCT1_URL", ""),
        "product2": getattr(settings, "WHOP_PRODUCT2_URL", ""),
        "product3": getattr(settings, "WHOP_PRODUCT3_URL", ""),
        "pro":      getattr(settings, "WHOP_PRO_URL", ""),
    }
    base = urls.get(plan_key, "")
    if not base:
        return ""
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}metadata[telegram_id]={telegram_id}"


def _trial_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Start my 14-day free trial", callback_data="trial_start"),
    ]])


def _upgrade_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    rows = []
    plans = [
        ("product1", "Indicator Validator — $29/mo"),
        ("product2", "EA Analyzer — $49/mo"),
        ("product3", "Manual Validator — $19/mo"),
        ("pro",      "Pro Bundle — $79/mo"),
    ]
    for key, label in plans:
        url = _checkout_url(key, telegram_id)
        if url:
            rows.append([InlineKeyboardButton(text=label, url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── /trial command ─────────────────────────────────────────────────────────────

@router.message(Command("trial"))
async def cmd_trial(message: Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        status = await user_svc.get_trial_status(telegram_id)

    if status["active"]:
        days = status["days_remaining"]
        await message.answer(
            f"⏳ *Your free trial is active*\n\n"
            f"You have *{days} day{'s' if days != 1 else ''}* remaining.\n\n"
            f"When your trial ends you'll need a paid plan to keep access.\n"
            f"Use /subscribe to see plans.",
            parse_mode="Markdown",
            reply_markup=_upgrade_keyboard(telegram_id),
        )
        return

    if status["used"]:
        await message.answer(
            "ℹ️ *Trial already used*\n\n"
            "Your 14-day trial has ended. Subscribe to keep access:",
            parse_mode="Markdown",
            reply_markup=_upgrade_keyboard(telegram_id),
        )
        return

    # Eligible for trial
    await message.answer(
        "🎁 *Start your free 14-day trial*\n\n"
        "Get full access to all 3 products for 14 days — no card needed.\n\n"
        "• Indicator Validator\n"
        "• EA Analyzer\n"
        "• Manual Validator\n\n"
        "After 14 days, subscribe to keep access.",
        parse_mode="Markdown",
        reply_markup=_trial_keyboard(telegram_id),
    )


# ── Callback: confirm trial start ─────────────────────────────────────────────

@router.callback_query(F.data == "trial_start")
async def cb_trial_start(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        status = await user_svc.get_trial_status(telegram_id)

        if status["used"]:
            await callback.answer("Trial already used.", show_alert=True)
            return

        user = await user_svc.start_trial(telegram_id)
        await db.commit()
        expires = user.trial_expires_at.strftime("%b %d, %Y")

    await callback.message.edit_text(
        f"🎉 *Trial started!*\n\n"
        f"You have full access to all products until *{expires}*.\n\n"
        f"Use /help to see all available commands.",
        parse_mode="Markdown",
    )
    await callback.answer()


# ── Helper: offer trial to brand-new users (call from /start handler) ─────────

async def offer_trial_if_eligible(message: Message):
    """
    Call this from your existing /start handler after creating the user.
    If the user is on FREE and has never trialled, show the trial offer.
    """
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        status = await user_svc.get_trial_status(telegram_id)

    if not status["used"]:
        await message.answer(
            "👋 *Welcome to AI Trade Validator!*\n\n"
            "You're eligible for a *14-day free trial* — full access to all products, no credit card needed.\n\n"
            "Tap below to activate it:",
            parse_mode="Markdown",
            reply_markup=_trial_keyboard(telegram_id),
        )


# ── Registration helper ────────────────────────────────────────────────────────
# In TG_Bot/main.py, import and register this router:
#
#   from TG_Bot.handlers.trial import router as trial_router
#   dp.include_router(trial_router)
