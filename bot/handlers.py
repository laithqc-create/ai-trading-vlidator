"""
bot/handlers.py — DEPRECATED

This module was the original python-telegram-bot implementation.
It has been fully replaced by the aiogram 3.x TG_Bot/ layer.

The aiogram bot is now the only active bot implementation:
  TG_Bot/main.py              — entry point
  TG_Bot/handlers/start.py    — /start, menu routing
  TG_Bot/handlers/generate.py — /generate, /generate_ea, /share_code
  TG_Bot/handlers/validate.py — /check, /outcome, /history
  TG_Bot/handlers/subscription.py — /subscribe, /insights

This file is kept only to avoid breaking any import that might reference it.
Do not add new code here.
"""

# Legacy stub — kept for backwards compatibility only
def create_bot_app():
    raise RuntimeError(
        "bot/handlers.py is deprecated. "
        "Use TG_Bot.main.get_bot() and TG_Bot.main.get_dispatcher() instead."
    )
