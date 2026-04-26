"""
TG_Bot/keyboards/strategy_kb.py

Three-button strategy keyboard for Product 1 (Indicator Validator).
Each button is a different entry method for different user types.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def strategy_selector() -> InlineKeyboardMarkup:
    """
    Product 1 — Three entry methods:
      Button 1: Webhook (paid TradingView users)
      Button 2: Share Source Code (free TradingView users, bypass 3-indicator limit)
      Button 3: AI Generate Pine Script (everyone, free loss leader)
    """
    buttons = [
        [InlineKeyboardButton(
            text="🔌 Connect via Webhook",
            callback_data="strategy_webhook",
        )],
        [InlineKeyboardButton(
            text="📄 Share Source Code",
            callback_data="strategy_source",
        )],
        [InlineKeyboardButton(
            text="🤖 AI Generate Pine Script (Free)",
            callback_data="strategy_generate",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def ea_entry_selector() -> InlineKeyboardMarkup:
    """
    Product 2 — Two entry methods for EA users:
      Button 1: Connect EA monitor (paid)
      Button 2: AI Generate MQL5 EA (free)
    """
    buttons = [
        [InlineKeyboardButton(
            text="📡 Connect EA Monitor",
            callback_data="ea_connect_monitor",
        )],
        [InlineKeyboardButton(
            text="🤖 AI Generate MQL5 EA (Free)",
            callback_data="ea_generate",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def signal_selector() -> InlineKeyboardMarkup:
    """BUY / SELL / HOLD quick-select for /check flow."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 BUY",  callback_data="signal_BUY")
    builder.button(text="📉 SELL", callback_data="signal_SELL")
    builder.button(text="⏸️ HOLD", callback_data="signal_HOLD")
    builder.adjust(3)
    return builder.as_markup()


def generation_result_keyboard(code_type: str) -> InlineKeyboardMarkup:
    """
    Actions after code is generated (Pine Script or MQL5).
    code_type: 'pine' or 'mql5'
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📋 Copy Code",
        callback_data=f"copy_code_{code_type}",
    )
    builder.button(
        text="💾 Save to My KB",
        callback_data=f"save_code_{code_type}",
    )
    builder.button(
        text="🔄 Regenerate",
        callback_data=f"regen_{code_type}",
    )
    builder.button(
        text="💳 Validate Signals ($19/mo)",
        callback_data="subscribe_product1",
    )
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def skip_price_keyboard() -> InlineKeyboardMarkup:
    """Used in /check flow — allow user to skip price entry."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Skip (use current price)", callback_data="skip_price")
    return builder.as_markup()
