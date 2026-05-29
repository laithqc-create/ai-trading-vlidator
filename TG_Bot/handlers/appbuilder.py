"""
TG_Bot/handlers/appbuilder.py
Telegram interface for Product 4 — App Builder.
Register in TG_Bot/main.py:
  from TG_Bot.handlers.appbuilder import router as appbuilder_router
  dp.include_router(appbuilder_router)
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from loguru import logger

from db.database import AsyncSessionLocal
from services.user import UserService
from services.appbuilder_service import AppBuilderService, DISCLAIMER_TEXT
from services.deepseek import DeepSeekService

router = Router()


class BuildFSM(StatesGroup):
    waiting_project_name      = State()
    waiting_project_desc      = State()
    waiting_platform          = State()
    waiting_disclaimer_agree  = State()
    waiting_build_message     = State()


PLATFORM_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="MQL5 (MetaTrader 5)")],
        [KeyboardButton(text="MQL4 (MetaTrader 4)")],
        [KeyboardButton(text="Pine Script (TradingView)")],
        [KeyboardButton(text="Python")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

PLATFORM_MAP = {
    "MQL5 (MetaTrader 5)": "mql5",
    "MQL4 (MetaTrader 4)": "mql4",
    "Pine Script (TradingView)": "pine",
    "Python": "python",
}


# ── /build command ─────────────────────────────────────────────────────────────
@router.message(Command("build"))
async def cmd_build(message: Message, state: FSMContext):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        if not user.has_product_access(1):
            await message.answer(
                "🔒 The App Builder requires an active trial or paid plan.\n"
                "Use /trial to start your free trial or /subscribe to upgrade."
            )
            return

        # List existing projects
        svc = AppBuilderService(db)
        projects = await svc.list_projects(user.id)

    kb_rows = []
    for p in projects[:5]:
        kb_rows.append([InlineKeyboardButton(
            text=f"📁 {p.name} (v{p.current_version})",
            callback_data=f"build_open:{p.id}",
        )])
    kb_rows.append([InlineKeyboardButton(text="➕ New project", callback_data="build_new")])

    await message.answer(
        "🏗️ *App Builder*\n\nBuild your own trading app using AI agentic code generation.\n\n"
        + (f"You have *{len(projects)}* existing project(s).\n" if projects else "")
        + "Choose a project or start a new one:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
    )


# ── New project flow ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "build_new")
async def cb_build_new(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📝 *New project*\n\nWhat is the name of your trading app?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(BuildFSM.waiting_project_name)
    await callback.answer()


@router.message(BuildFSM.waiting_project_name)
async def fsm_project_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Name too short. Try again:")
        return
    await state.update_data(project_name=name)
    await message.answer(
        f"✅ Name: *{name}*\n\nDescribe what your app should do in plain English.\n\n"
        "Example: _An EA that buys when RSI < 30 and a bullish engulfing candle forms, "
        "with a 50-pip SL and 100-pip TP._",
        parse_mode="Markdown",
    )
    await state.set_state(BuildFSM.waiting_project_desc)


@router.message(BuildFSM.waiting_project_desc)
async def fsm_project_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    if len(desc) < 10:
        await message.answer("Description too short. Be more specific:")
        return
    await state.update_data(project_desc=desc)
    await message.answer("Choose the platform for your app:", reply_markup=PLATFORM_KB)
    await state.set_state(BuildFSM.waiting_platform)


@router.message(BuildFSM.waiting_platform)
async def fsm_platform(message: Message, state: FSMContext):
    platform_raw = message.text.strip()
    platform = PLATFORM_MAP.get(platform_raw)
    if not platform:
        await message.answer("Please use the keyboard to choose a platform.")
        return

    await state.update_data(platform=platform)
    data = await state.get_data()

    # Show disclaimer
    await message.answer(
        f"✅ Platform: *{platform_raw}*\n\n"
        "Before we start, you must read and agree to our terms:\n\n"
        f"```\n{DISCLAIMER_TEXT}\n```\n\n"
        "Type *AGREE* to confirm and begin building.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(BuildFSM.waiting_disclaimer_agree)


@router.message(BuildFSM.waiting_disclaimer_agree)
async def fsm_disclaimer(message: Message, state: FSMContext):
    if message.text.strip().upper() != "AGREE":
        await message.answer(
            "You must type *AGREE* (all caps) to confirm you've read the disclaimer.",
            parse_mode="Markdown",
        )
        return

    data = await state.get_data()
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        svc = AppBuilderService(db)

        project = await svc.create_project(
            user=user,
            name=data["project_name"],
            description=data["project_desc"],
            platform=data["platform"],
        )
        await svc.agree_disclaimer(project.id, user.id)
        await db.commit()
        project_id = str(project.id)

    await state.update_data(project_id=project_id)
    await message.answer(
        f"🚀 *Project created!*\n\n"
        f"*{data['project_name']}* — {data['platform'].upper()}\n\n"
        f"Now tell me what to build first. Be as detailed as you like.\n"
        f"You can say things like:\n"
        f"• _Build the entry logic_\n"
        f"• _Add a trailing stop loss_\n"
        f"• _Why did you use OnTick instead of OnTimer?_\n"
        f"• _Make the lot size dynamic based on account balance_\n\n"
        f"Send /done when you want to download your code.",
        parse_mode="Markdown",
    )
    await state.set_state(BuildFSM.waiting_build_message)


# ── Open existing project ─────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("build_open:"))
async def cb_build_open(callback: CallbackQuery, state: FSMContext):
    project_id = callback.data.split(":", 1)[1]
    await state.update_data(project_id=project_id)
    await callback.message.answer(
        "📁 Project loaded. What would you like to build or change?\n\n"
        "Send /done to download the current code.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(BuildFSM.waiting_build_message)
    await callback.answer()


# ── Agentic build loop ────────────────────────────────────────────────────────
@router.message(BuildFSM.waiting_build_message)
async def fsm_build_message(message: Message, state: FSMContext):
    text = message.text.strip()

    # /done command
    if text.lower() in ("/done", "done"):
        await cmd_done(message, state)
        return

    data = await state.get_data()
    project_id = data.get("project_id")
    if not project_id:
        await message.answer("No active project. Use /build to start.")
        await state.clear()
        return

    telegram_id = message.from_user.id
    thinking_msg = await message.answer("🤖 Thinking…")

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        svc = AppBuilderService(db)
        ds = DeepSeekService()

        try:
            from uuid import UUID
            step = await svc.build_step(
                project_id=UUID(project_id),
                user_id=user.id,
                user_message=text,
                deepseek_service=ds,
            )
            await db.commit()
        except Exception as e:
            await thinking_msg.edit_text(f"❌ Build error: {e}")
            return

    # Format response
    parts = []

    if step.agent_plan:
        parts.append(f"📋 *Plan*\n{step.agent_plan}")

    if step.agent_notes:
        parts.append(f"💬 *Notes*\n{step.agent_notes}")

    if step.warnings:
        warn_text = "\n".join(f"⚠️ {w}" for w in step.warnings)
        parts.append(f"*Warnings*\n{warn_text}")

    if step.full_code:
        # Show a code preview (first 800 chars)
        preview = step.full_code[:800]
        if len(step.full_code) > 800:
            preview += f"\n… (+{len(step.full_code) - 800} more chars)"
        parts.append(f"```\n{preview}\n```")

    response_text = "\n\n".join(parts) or "Step complete."

    # Telegram has 4096 char limit — split if needed
    if len(response_text) > 4000:
        for chunk in [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]:
            await message.answer(chunk, parse_mode="Markdown")
    else:
        await thinking_msg.edit_text(response_text, parse_mode="Markdown")

    await message.answer(
        f"Step {step.step_number} complete. What next? (or /done to download)",
    )


# ── /done — download code ─────────────────────────────────────────────────────
async def cmd_done(message: Message, state: FSMContext):
    data = await state.get_data()
    project_id = data.get("project_id")
    if not project_id:
        await message.answer("No active project.")
        return

    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        svc = AppBuilderService(db)

        from uuid import UUID
        project = await svc.get_project(UUID(project_id), user.id)

    if not project.current_code:
        await message.answer("No code generated yet. Send me a build instruction first.")
        return

    ext_map = {"mql5": "mq5", "mql4": "mq4", "pine": "pine", "python": "py"}
    ext = ext_map.get(project.platform, "txt")
    filename = f"{project.name.replace(' ', '_')}_v{project.current_version}.{ext}"

    # Send as document
    from io import BytesIO
    from aiogram.types import BufferedInputFile
    code_bytes = project.current_code.encode("utf-8")
    file = BufferedInputFile(code_bytes, filename=filename)

    await message.answer_document(
        document=file,
        caption=(
            f"📦 *{project.name}* v{project.current_version}\n"
            f"Platform: {project.platform.upper()}\n\n"
            "⚠️ Always test in a demo account before going live.\n\n"
            "Use /build to continue working on this project, or "
            "use /market to list it on the marketplace."
        ),
        parse_mode="Markdown",
    )
    await state.clear()
