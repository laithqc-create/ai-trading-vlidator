"""
services/appbuilder_service.py
Agentic app-builder service.

The agent works in a loop:
  1. PLAN  — breaks the user request into numbered sub-tasks
  2. CODE  — writes/edits code for each sub-task
  3. REVIEW — checks the code for obvious bugs and risk flags
  4. RESPOND — sends plan + code + notes back to the user

The user can then:
  - Accept the step and ask for the next one
  - Refine ("make the SL dynamic instead of fixed")
  - Ask why ("why did you use iMA instead of iCustom?")

All iterations are stored as AppBuildStep rows so the full
conversation + code history is preserved.
"""

from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models_appbuilder import AppProject, AppBuildStep, BuildStatus
from db.models import User, PlanTier


DISCLAIMER_TEXT = """
IMPORTANT — PLEASE READ BEFORE PROCEEDING

This App Builder is a CODE WRITING TOOL ONLY.

• All code produced is for educational and technical purposes.
• Our system writes code based on your instructions. It does NOT provide
  financial advice, trading recommendations, or investment guidance.
• You are solely and entirely responsible for:
    – Testing all code in a demo/simulation environment before live use
    – Any trades executed by code you deploy
    – Any financial outcome, profit or loss, resulting from your use of this code
• We make no warranties about the correctness, profitability, or fitness
  of any generated code for any purpose.
• By proceeding you confirm you understand and accept full responsibility.

Type AGREE to confirm and start building.
""".strip()

SYSTEM_PROMPT = """You are an expert algorithmic trading developer and code architect.
You write production-quality MQL5, MQL4, Pine Script, and Python trading code.

You operate in AGENTIC MODE. For each user request you MUST:

STEP 1 — PLAN
Output a numbered list of sub-tasks required to implement the request.
Be specific: name every function, variable, and logic block you will create or change.

STEP 2 — CODE
Write the complete implementation. For changes to existing code, show a clearly
marked diff (lines starting with + for additions, - for removals).
For new files, write the full file.

STEP 3 — REVIEW
List any:
  - Potential runtime errors or edge cases
  - Risk management gaps (e.g. no stop loss, no max drawdown check)
  - Platform-specific pitfalls (e.g. MQL5 OnTick vs OnTimer, broker spread)
  - Anything the user should test specifically in demo first

STEP 4 — NOTES
A short plain-English summary of what was built and what the user should do next.

IMPORTANT RULES:
- Never make financial recommendations. You write code, not trading advice.
- Always include basic risk management (SL/TP) unless the user explicitly removes it.
- Always include a disclaimer comment at the top of generated MQL5/MQL4 files.
- If the user asks for something dangerous (e.g. no SL, unlimited lot size scaling),
  include a WARNING in the REVIEW section but still write the code if they insist.
- Output your response as valid JSON matching this schema:
  {
    "plan": "1. ...\n2. ...",
    "code_diff": "...",
    "full_code": "...",
    "agent_notes": "...",
    "warnings": ["...", "..."]
  }
"""


class AppBuilderService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Project management ────────────────────────────────────────────────────

    async def create_project(
        self,
        user: User,
        name: str,
        description: str,
        platform: str = "mql5",
    ) -> AppProject:
        """Create a new app project. disclaimer_agreed starts False."""
        project = AppProject(
            user_id=user.id,
            name=name,
            description=description,
            platform=platform.lower(),
            status=BuildStatus.IDLE,
            disclaimer_agreed=False,
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def agree_disclaimer(self, project_id: UUID, user_id: int) -> AppProject:
        """Mark disclaimer as agreed. Required before first build step."""
        project = await self._get_project(project_id, user_id)
        project.disclaimer_agreed = True
        project.agreed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return project

    async def list_projects(self, user_id: int) -> list[AppProject]:
        result = await self.db.execute(
            select(AppProject)
            .where(AppProject.user_id == user_id)
            .order_by(AppProject.updated_at.desc())
        )
        return result.scalars().all()

    async def get_project(self, project_id: UUID, user_id: int) -> AppProject:
        return await self._get_project(project_id, user_id)

    # ── Agentic build step ────────────────────────────────────────────────────

    async def build_step(
        self,
        project_id: UUID,
        user_id: int,
        user_message: str,
        deepseek_service,         # injected — your existing DeepSeekService instance
    ) -> AppBuildStep:
        """
        Run one agentic build iteration.
        Returns the completed AppBuildStep with plan, code, notes, warnings.
        """
        project = await self._get_project(project_id, user_id)

        if not project.disclaimer_agreed:
            raise ValueError("Disclaimer not agreed. User must agree before building.")

        # Count existing steps
        steps_result = await self.db.execute(
            select(AppBuildStep)
            .where(AppBuildStep.project_id == project_id)
            .order_by(AppBuildStep.step_number)
        )
        existing_steps = steps_result.scalars().all()
        step_number = len(existing_steps) + 1

        # Create the step record (status=PLANNING)
        step = AppBuildStep(
            project_id=project_id,
            step_number=step_number,
            user_message=user_message,
            status=BuildStatus.PLANNING,
        )
        self.db.add(step)
        await self.db.flush()

        # Build message history for the agent
        messages = self._build_messages(project, existing_steps, user_message)

        # Call DeepSeek
        project.status = BuildStatus.CODING
        await self.db.flush()

        try:
            raw_response = await deepseek_service.chat(messages)
            parsed = self._parse_agent_response(raw_response)

            step.agent_plan   = parsed.get("plan", "")
            step.code_diff    = parsed.get("code_diff", "")
            step.full_code    = parsed.get("full_code", "")
            step.agent_notes  = parsed.get("agent_notes", "")
            step.warnings     = parsed.get("warnings", [])
            step.status       = BuildStatus.DONE

            # Update project with latest code
            if step.full_code:
                project.current_code    = step.full_code
                project.current_version = step_number

            project.status = BuildStatus.DONE

        except Exception as e:
            step.status        = BuildStatus.ERROR
            step.error_message = str(e)
            project.status     = BuildStatus.ERROR
            logger.error(f"AppBuilder step error: {e}")
            raise

        await self.db.flush()
        return step

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_messages(
        self,
        project: AppProject,
        history: list[AppBuildStep],
        user_message: str,
    ) -> list[dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Seed the context with the original project description
        messages.append({
            "role": "user",
            "content": (
                f"Project: {project.name}\n"
                f"Platform: {project.platform.upper()}\n"
                f"Description: {project.description}\n\n"
                f"Start building this application."
            ),
        })

        # Replay prior steps so the agent has full context
        for step in history:
            if step.status == BuildStatus.DONE:
                messages.append({"role": "user", "content": step.user_message})
                agent_recap = json.dumps({
                    "plan": step.agent_plan,
                    "code_diff": step.code_diff,
                    "full_code": step.full_code,
                    "agent_notes": step.agent_notes,
                    "warnings": step.warnings,
                })
                messages.append({"role": "assistant", "content": agent_recap})

        # Append current user message
        messages.append({"role": "user", "content": user_message})
        return messages

    def _parse_agent_response(self, raw: str) -> dict:
        """Parse JSON from agent response. Falls back to partial extraction."""
        # Strip markdown fences
        clean = re.sub(r"```json|```", "", raw).strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Fallback: treat entire response as agent_notes
            logger.warning("AppBuilder: could not parse JSON response, using raw text")
            return {
                "plan": "",
                "code_diff": "",
                "full_code": raw,
                "agent_notes": raw,
                "warnings": [],
            }

    async def _get_project(self, project_id: UUID, user_id: int) -> AppProject:
        result = await self.db.execute(
            select(AppProject)
            .where(AppProject.id == project_id, AppProject.user_id == user_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise ValueError(f"Project {project_id} not found for user {user_id}")
        return project

    @staticmethod
    def get_disclaimer_text() -> str:
        return DISCLAIMER_TEXT
