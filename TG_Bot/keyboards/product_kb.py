"""
TG_Bot/keyboards/product_kb.py

Inline keyboards for product-specific interactions:
  - Subscription plan selection
  - Validation verdict actions
  - History / outcome reporting
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def subscription_plans_keyboard(current_plan: str = "free") -> InlineKeyboardMarkup:
    """
    Subscription plan selection keyboard.
    Highlights current plan; hides it from clickable options.
    """
    plans = [
        ("product1", "1️⃣ Indicator Validator — $19/mo"),
        ("product2", "2️⃣ EA Analyzer — $49/mo"),
        ("product3", "3️⃣ Manual Validator — $19/mo"),
        ("pro",      "⭐ Pro Bundle — $79/mo"),
    ]

    builder = InlineKeyboardBuilder()
    for plan_id, label in plans:
        if plan_id != current_plan:
            builder.button(
                text=label,
                callback_data=f"subscribe_{plan_id}",
            )
    builder.button(
        text="📊 Compare Plans",
        callback_data="compare_plans",
    )
    builder.adjust(1)
    return builder.as_markup()


def verdict_actions_keyboard(validation_id: int) -> InlineKeyboardMarkup:
    """
    Shown after a validation result so user can quickly report outcome.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ I took it — WON",  callback_data=f"outcome_win_{validation_id}")
    builder.button(text="❌ I took it — LOST", callback_data=f"outcome_loss_{validation_id}")
    builder.button(text="⏭️ Skipped",          callback_data=f"outcome_skip_{validation_id}")
    builder.button(text="📤 Share result",      callback_data=f"share_{validation_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def history_actions_keyboard() -> InlineKeyboardMarkup:
    """Actions below the /history list."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 View Stats",     callback_data="view_stats")
    builder.button(text="🗑️ Clear History",  callback_data="clear_history_confirm")
    builder.adjust(2)
    return builder.as_markup()


def account_keyboard(plan: str) -> InlineKeyboardMarkup:
    """Account overview actions."""
    builder = InlineKeyboardBuilder()
    if plan == "free":
        builder.button(text="⬆️ Upgrade Plan",    callback_data="show_plans")
    else:
        builder.button(text="🔄 Change Plan",      callback_data="show_plans")
        builder.button(text="❌ Cancel Sub",        callback_data="cancel_subscription")
    builder.button(text="📊 Usage Stats",          callback_data="view_usage")
    builder.button(text="📋 My Rules",             callback_data="view_rules")
    builder.adjust(1)
    return builder.as_markup()


def confirm_cancel_keyboard(action: str) -> InlineKeyboardMarkup:
    """Generic confirm/cancel keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data=f"confirm_{action}")
    builder.button(text="❌ Cancel",  callback_data="cancel_action")
    builder.adjust(2)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Single back button."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Back to Menu", callback_data="back_to_menu")
    return builder.as_markup()
