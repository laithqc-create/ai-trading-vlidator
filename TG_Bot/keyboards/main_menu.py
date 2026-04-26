"""
TG_Bot/keyboards/main_menu.py

Main navigation Reply Keyboard — replaces the user's input field with buttons.
Shown after /start and after completing any action.
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Main persistent menu keyboard.
    Shown at the bottom of the screen after /start.
    """
    kb = [
        [
            KeyboardButton(text="📊 Indicator Validator"),
            KeyboardButton(text="🤖 EA Analyzer"),
        ],
        [
            KeyboardButton(text="🔍 Manual Check"),
            KeyboardButton(text="🆓 Free Generator"),
        ],
        [
            KeyboardButton(text="⚙️ My Account"),
            KeyboardButton(text="❓ Help"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Choose a product or type a command...",
    )


def remove_keyboard():
    """Remove the reply keyboard (used when expecting free-form input)."""
    from aiogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()
