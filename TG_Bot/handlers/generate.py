"""
TG_Bot/handlers/generate.py

Handles all code generation flows:
  /generate  — English → Pine Script v6  (free, loss leader)
  /generate_ea — English → MQL5 EA      (free, loss leader)
  /share_code  — Paste Pine Script source (store in RAGFlow)
  /my_usage    — Show generation budget

Uses aiogram FSM for multi-step flows (prompt → input → generate → result).
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from TG_Bot.states.states import GeneratePineScriptSG, GenerateMQL5SG, ShareCodeSG
from TG_Bot.keyboards.strategy_kb import generation_result_keyboard, strategy_selector
from TG_Bot.keyboards.main_menu import main_menu_keyboard, remove_keyboard
from TG_Bot.keyboards.product_kb import back_to_menu_keyboard
from db.models import User
from config.settings import settings

router = Router(name="generate")

CODE_DISCLAIMER = (
    "\n\n---\n"
    "_We use DeepSeek as AI brain. API costs absorbed up to $5/user. "
    "Code quality not our responsibility — we only route. "
    "Use HorizonAI (free) for visual confirmation before live trading._"
)


# ─── /generate ────────────────────────────────────────────────────────────────

@router.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext, user: User):
    args = message.text.split(maxsplit=1)
    strategy = args[1].strip() if len(args) > 1 else ""

    if strategy:
        # Strategy provided inline — run directly
        await _run_pine_generation(message, state, user, strategy)
    else:
        # Prompt user to enter strategy
        await state.set_state(GeneratePineScriptSG.waiting_for_strategy)
        await message.answer(
            "*📈 Pine Script Generator*\n\n"
            "Describe your trading strategy in plain English:\n\n"
            "_Examples:_\n"
            "• `Buy when RSI is below 30 and volume is above average`\n"
            "• `Sell when price crosses below the 50 EMA`\n"
            "• `Alert when MACD histogram turns positive after negative`\n\n"
            "Type your strategy now 👇",
            parse_mode="Markdown",
            reply_markup=remove_keyboard(),
        )


@router.message(GeneratePineScriptSG.waiting_for_strategy)
async def handle_pine_strategy_input(message: Message, state: FSMContext, user: User):
    strategy = message.text.strip()
    if len(strategy) < 10:
        await message.answer(
            "❓ Strategy too short. Please describe in more detail.\n\n"
            "_Example: `Buy when RSI falls below 30 and volume is 1.5x average`_",
            parse_mode="Markdown",
        )
        return
    await _run_pine_generation(message, state, user, strategy)


async def _run_pine_generation(
    message: Message,
    state: FSMContext,
    user: User,
    strategy: str,
):
    from services.user import UserService
    from db.database import AsyncSessionLocal

    # Check budget
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        if user_svc.is_over_generation_cap(db_user):
            await state.clear()
            await message.answer(
                f"⚠️ *Free limit reached* (${settings.DEEPSEEK_FREE_CAP:.0f} cap)\n\n"
                f"You've used {db_user.total_generations} generations.\n"
                f"Upgrade to *Pro* for unlimited. Use /subscribe.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

    await state.set_state(GeneratePineScriptSG.generating)
    thinking = await message.answer(
        "⏳ *Generating Pine Script v6...*\n"
        "_DeepSeek AI is writing your indicator. Usually 10-20 seconds._",
        parse_mode="Markdown",
    )

    from services.deepseek import DeepSeekService
    ds = DeepSeekService()
    result = await ds.generate_pine_script(strategy)

    await thinking.delete()

    if not result["success"]:
        await state.clear()
        await message.answer(
            f"❌ Generation failed: `{result['error']}`\n\nPlease try again.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Track cost
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        await user_svc.increment_generation_cost(db_user, result["cost"])
        spent = db_user.total_generation_cost or 0.0
        remaining = user_svc.generation_budget_remaining(db_user)

    code = result["code"]
    code_preview = code[:3500] + "\n... (truncated)" if len(code) > 3500 else code

    # Store code in FSM for save/regen actions
    await state.update_data(last_code=code, last_strategy=strategy, code_type="pine")
    await state.set_state(GeneratePineScriptSG.showing_result)

    warn = f"\n\n⚠️ _Approaching $5 limit (${spent:.2f} spent)_" if spent >= 4.50 else ""

    await message.answer(
        f"*✅ Pine Script v6 Generated*\n\n"
        f"*Strategy:* _{strategy[:80]}_\n\n"
        f"```pine\n{code_preview}\n```"
        f"{CODE_DISCLAIMER}\n\n"
        f"_Budget: ${spent:.3f} used · ${remaining:.3f} remaining_{warn}",
        parse_mode="Markdown",
        reply_markup=generation_result_keyboard("pine"),
    )


# ─── /generate_ea ─────────────────────────────────────────────────────────────

@router.message(Command("generate_ea"))
async def cmd_generate_ea(message: Message, state: FSMContext, user: User):
    args = message.text.split(maxsplit=1)
    strategy = args[1].strip() if len(args) > 1 else ""

    if strategy:
        await _run_mql5_generation(message, state, user, strategy)
    else:
        await state.set_state(GenerateMQL5SG.waiting_for_strategy)
        await message.answer(
            "*⚙️ MQL5 EA Generator*\n\n"
            "Describe your EA strategy in plain English:\n\n"
            "_Examples:_\n"
            "• `Buy when RSI crosses above 50, sell when it drops below`\n"
            "• `Place buy stop 10 pips above the high of every new candle`\n"
            "• `Scalp with 5 pip TP and 10 pip SL on EURUSD M1`\n\n"
            "Type your strategy now 👇",
            parse_mode="Markdown",
            reply_markup=remove_keyboard(),
        )


@router.message(GenerateMQL5SG.waiting_for_strategy)
async def handle_mql5_strategy_input(message: Message, state: FSMContext, user: User):
    strategy = message.text.strip()
    if len(strategy) < 10:
        await message.answer(
            "❓ Too short. Please describe the EA logic in more detail.",
        )
        return
    await _run_mql5_generation(message, state, user, strategy)


async def _run_mql5_generation(
    message: Message,
    state: FSMContext,
    user: User,
    strategy: str,
):
    from services.user import UserService
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        if user_svc.is_over_generation_cap(db_user):
            await state.clear()
            await message.answer(
                f"⚠️ *Free limit reached* (${settings.DEEPSEEK_FREE_CAP:.0f} cap)\n\n"
                f"Upgrade to *Pro* for unlimited. Use /subscribe.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

    await state.set_state(GenerateMQL5SG.generating)
    thinking = await message.answer(
        "⏳ *Generating MQL5 EA...*\n"
        "_DeepSeek AI is writing your Expert Advisor. Usually 15-25 seconds._",
        parse_mode="Markdown",
    )

    from services.deepseek import DeepSeekService
    ds = DeepSeekService()
    result = await ds.generate_mql5(strategy)

    await thinking.delete()

    if not result["success"]:
        await state.clear()
        await message.answer(
            f"❌ Generation failed: `{result['error']}`\n\nPlease try again.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        await user_svc.increment_generation_cost(db_user, result["cost"])
        spent = db_user.total_generation_cost or 0.0
        remaining = user_svc.generation_budget_remaining(db_user)

    code = result["code"]
    code_preview = code[:3500] + "\n... (truncated)" if len(code) > 3500 else code

    await state.update_data(last_code=code, last_strategy=strategy, code_type="mql5")
    await state.set_state(GenerateMQL5SG.showing_result)

    warn = f"\n\n⚠️ _Approaching $5 limit (${spent:.2f} spent)_" if spent >= 4.50 else ""

    await message.answer(
        f"*✅ MQL5 EA Generated*\n\n"
        f"*Strategy:* _{strategy[:80]}_\n\n"
        f"```mql5\n{code_preview}\n```"
        f"{CODE_DISCLAIMER}\n\n"
        f"_Budget: ${spent:.3f} used · ${remaining:.3f} remaining_{warn}",
        parse_mode="Markdown",
        reply_markup=generation_result_keyboard("mql5"),
    )


# ─── Generation result callbacks ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("regen_"))
async def cb_regenerate(callback: CallbackQuery, state: FSMContext, user: User):
    """Regenerate the last code with the same strategy."""
    code_type = callback.data.split("_", 1)[1]
    data = await state.get_data()
    strategy = data.get("last_strategy", "")

    if not strategy:
        await callback.answer("No previous strategy found. Use /generate again.", show_alert=True)
        return

    await callback.answer("Regenerating...")
    if code_type == "pine":
        await _run_pine_generation(callback.message, state, user, strategy)
    else:
        await _run_mql5_generation(callback.message, state, user, strategy)


@router.callback_query(F.data.startswith("save_code_"))
async def cb_save_code(callback: CallbackQuery, state: FSMContext, user: User):
    """Save generated code to user's RAGFlow knowledge base."""
    code_type = callback.data.split("_", 2)[2]
    data = await state.get_data()
    code = data.get("last_code", "")

    if not code:
        await callback.answer("No code to save.", show_alert=True)
        return

    from ragflow.service import RAGFlowService
    from db.database import AsyncSessionLocal
    from config.settings import settings as app_settings

    ragflow = RAGFlowService(app_settings)
    dataset_id = user.ragflow_dataset_id

    if not dataset_id:
        async with AsyncSessionLocal() as db:
            from services.user import UserService
            user_svc = UserService(db)
            db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
            dataset_id = await ragflow.create_user_dataset(user.telegram_id)
            if dataset_id:
                db_user.ragflow_dataset_id = dataset_id

    if dataset_id:
        lang = "Pine Script" if code_type == "pine" else "MQL5"
        rule_text = f"{lang} GENERATED CODE:\n{code[:2000]}"
        await ragflow.add_rule_to_dataset(dataset_id, rule_text, rule_id=88000 + user.id)
        await callback.answer("✅ Saved to your knowledge base!", show_alert=True)
    else:
        await callback.answer("❌ Could not connect to RAGFlow. Try again.", show_alert=True)


@router.callback_query(F.data.startswith("copy_code_"))
async def cb_copy_hint(callback: CallbackQuery):
    """Telegram doesn't support server-side copy, but we can hint."""
    await callback.answer(
        "Long-press the code block above to copy it!",
        show_alert=True,
    )


# ─── /share_code ──────────────────────────────────────────────────────────────

@router.message(Command("share_code"))
@router.callback_query(F.data == "strategy_source")
async def cmd_share_code(event, state: FSMContext, user: User):
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()

    await state.set_state(ShareCodeSG.waiting_for_code)
    await msg.answer(
        "*📄 Share Pine Script Source Code*\n\n"
        "Paste your indicator code in the next message.\n\n"
        "_Your code will be stored in your personal AI knowledge base "
        "and used to understand your trading logic when validating signals._\n\n"
        "✅ Supports: plain text paste or `.pine` / `.txt` file upload\n"
        "✅ Works on TradingView free plan (bypasses 3-indicator limit)\n\n"
        "Paste your code now 👇",
        parse_mode="Markdown",
        reply_markup=remove_keyboard(),
    )


@router.message(ShareCodeSG.waiting_for_code, F.text)
async def handle_pine_code_paste(message: Message, state: FSMContext, user: User):
    code = message.text.strip()

    pine_keywords = ["//@version", "indicator(", "strategy(", "plot(", "ta.", "input."]
    is_likely_pine = any(kw in code for kw in pine_keywords) or len(code) > 150

    if not is_likely_pine:
        await message.answer(
            "❓ That doesn't look like Pine Script.\n\n"
            "Make sure to paste the full code starting with `//@version=6`\n"
            "or use /share_code and try again.",
        )
        await state.clear()
        return

    # Store in RAGFlow
    await state.set_state(ShareCodeSG.confirming)
    status_msg = await message.answer("⏳ Saving to your knowledge base...")

    from ragflow.service import RAGFlowService
    from db.database import AsyncSessionLocal
    from config.settings import settings as app_settings

    ragflow = RAGFlowService(app_settings)

    async with AsyncSessionLocal() as db:
        from services.user import UserService
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        dataset_id = db_user.ragflow_dataset_id

        if not dataset_id:
            dataset_id = await ragflow.create_user_dataset(user.telegram_id)
            if dataset_id:
                db_user.ragflow_dataset_id = dataset_id

    if dataset_id:
        rule_text = (
            "PINE SCRIPT INDICATOR (user-shared):\n"
            "The user trades with this indicator. Use this code to understand "
            "their entry/exit logic when validating signals.\n\n"
            f"{code[:2000]}"
        )
        doc_id = await ragflow.add_rule_to_dataset(
            dataset_id=dataset_id,
            rule_text=rule_text,
            rule_id=99000 + (user.id or 0),
        )

        if doc_id:
            lines = len(code.strip().split("\n"))
            await status_msg.edit_text(
                f"*✅ Pine Script Saved*\n\n"
                f"_{lines} lines stored in your AI knowledge base._\n\n"
                f"Your indicator logic will now be considered when validating signals.\n\n"
                f"💡 Use /connect_indicator to set up your TradingView webhook.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await status_msg.edit_text(
                "❌ Failed to save. RAGFlow may be offline. Please try again.",
            )
    else:
        await status_msg.edit_text(
            "❌ Could not create your knowledge base. Please try again.",
        )

    await state.clear()


@router.message(ShareCodeSG.waiting_for_code, F.document)
async def handle_pine_file_upload(message: Message, state: FSMContext, user: User):
    """Handle .pine or .txt file upload."""
    doc = message.document
    if not (doc.file_name.endswith(".pine") or doc.file_name.endswith(".txt")):
        await message.answer("❌ Only .pine or .txt files supported.")
        return

    # Download file content
    from aiogram import Bot
    bot: Bot = message.bot
    file = await bot.get_file(doc.file_id)
    file_bytes = await bot.download_file(file.file_path)
    code = file_bytes.read().decode("utf-8", errors="replace")

    # Reuse paste handler
    message.text = code
    await handle_pine_code_paste(message, state, user)


# ─── /my_usage ────────────────────────────────────────────────────────────────

@router.message(Command("my_usage"))
async def cmd_my_usage(message: Message, user: User):
    from services.user import UserService
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        db_user = await user_svc.get_or_create_user(telegram_id=user.telegram_id)
        spent = db_user.total_generation_cost or 0.0
        generations = db_user.total_generations or 0
        remaining = user_svc.generation_budget_remaining(db_user)
        capped = user_svc.is_over_generation_cap(db_user)

    pct = min(spent / settings.DEEPSEEK_FREE_CAP, 1.0)
    filled = int(pct * 10)
    bar = "█" * filled + "░" * (10 - filled)
    status = "🔴 Limit reached" if capped else ("🟡 Approaching" if pct >= 0.8 else "🟢 Good")

    await message.answer(
        f"*📊 Free Generation Budget*\n\n"
        f"`[{bar}]` ${spent:.3f} / ${settings.DEEPSEEK_FREE_CAP:.2f}\n\n"
        f"Generations used: *{generations}*\n"
        f"Budget remaining: *${remaining:.3f}*\n"
        f"Status: {status}\n\n"
        f"_At $0.002/gen you can run ~{int(remaining / 0.002):,} more generations_\n\n"
        + ("⬆️ Upgrade to Pro ($79/mo) for unlimited. Use /subscribe." if capped
           else "💡 `/generate` and `/generate_ea` use this budget."),
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )


# ─── Strategy selector callbacks ──────────────────────────────────────────────

@router.callback_query(F.data == "strategy_webhook")
async def cb_strategy_webhook(callback: CallbackQuery, user: User):
    from TG_Bot.handlers.validate import send_webhook_setup
    await send_webhook_setup(callback.message, user)
    await callback.answer()


@router.callback_query(F.data == "strategy_generate")
async def cb_strategy_generate(callback: CallbackQuery, state: FSMContext, user: User):
    await callback.answer()
    await state.set_state(GeneratePineScriptSG.waiting_for_strategy)
    await callback.message.answer(
        "*🤖 AI Pine Script Generator*\n\n"
        "Describe your strategy in plain English 👇",
        parse_mode="Markdown",
        reply_markup=remove_keyboard(),
    )


@router.callback_query(F.data == "ea_generate")
async def cb_ea_generate(callback: CallbackQuery, state: FSMContext, user: User):
    await callback.answer()
    await state.set_state(GenerateMQL5SG.waiting_for_strategy)
    await callback.message.answer(
        "*🤖 AI MQL5 EA Generator*\n\n"
        "Describe your EA strategy in plain English 👇",
        parse_mode="Markdown",
        reply_markup=remove_keyboard(),
    )
