"""
TG_Bot/states/ — Finite State Machine groups for all multi-step user flows.

Aiogram 3.x FSM lets us track where a user is in a conversation
(e.g. "waiting for Pine Script paste" or "waiting for strategy description").
"""
from aiogram.fsm.state import State, StatesGroup


class GeneratePineScriptSG(StatesGroup):
    """States for /generate flow (English → Pine Script)."""
    waiting_for_strategy = State()    # user needs to type their strategy
    generating           = State()    # DeepSeek API call in progress
    showing_result       = State()    # showing generated code


class GenerateMQL5SG(StatesGroup):
    """States for /generate_ea flow (English → MQL5 EA)."""
    waiting_for_strategy = State()
    generating           = State()
    showing_result       = State()


class ShareCodeSG(StatesGroup):
    """States for /share_code flow (paste Pine Script source)."""
    waiting_for_code = State()        # user needs to paste code
    confirming       = State()        # confirm before storing in RAGFlow


class ManualCheckSG(StatesGroup):
    """States for /check flow (manual trade validation)."""
    waiting_for_ticker  = State()     # prompt: enter ticker
    waiting_for_signal  = State()     # prompt: BUY / SELL / HOLD
    waiting_for_price   = State()     # optional price entry
    processing          = State()     # validation running


class AddRuleSG(StatesGroup):
    """States for /add_rule multi-step flow."""
    waiting_for_rule = State()


class OutcomeSG(StatesGroup):
    """States for /outcome — report trade result."""
    waiting_for_outcome = State()     # WIN / LOSS / SKIP
    waiting_for_pnl     = State()     # optional PnL entry
