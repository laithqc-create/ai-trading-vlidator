"""
appbuilder/endpoints.py
FastAPI router for Product 4 — App Builder.
Mount in main.py with:
  from appbuilder.endpoints import router as appbuilder_router
  app.include_router(appbuilder_router)
"""

from __future__ import annotations
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from loguru import logger

from db.database import AsyncSessionLocal
from db.models import PlanTier
from services.user import UserService
from services.appbuilder_service import AppBuilderService, DISCLAIMER_TEXT
from services.deepseek import DeepSeekService

router = APIRouter(prefix="/api/appbuilder", tags=["appbuilder"])

PRODUCT4_PLANS = (PlanTier.PRO,)   # Product 4 is PRO-only (or active trial)


def _require_tg_id(request: Request) -> int:
    tid = request.headers.get("X-Telegram-User-Id", "")
    if not tid.isdigit():
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    return int(tid)


async def _require_access(telegram_id: int, db) -> "User":
    user_svc = UserService(db)
    user = await user_svc.get_or_create_user(telegram_id=telegram_id)
    # Allow trial users and PRO
    if not (user.has_product_access(1) or user.plan == PlanTier.PRO):
        # Product 4 is available to all paid/trial users
        pass
    if not user.has_product_access(1):
        raise HTTPException(403, "App Builder requires an active trial or paid plan")
    return user


# ── GET /api/appbuilder/disclaimer ────────────────────────────────────────────
@router.get("/disclaimer")
async def get_disclaimer():
    return {"disclaimer": DISCLAIMER_TEXT}


# ── POST /api/appbuilder/projects ─────────────────────────────────────────────
class CreateProjectRequest(BaseModel):
    name: str
    description: str
    platform: str = "mql5"   # mql5 | pine | python


@router.post("/projects")
async def create_project(req: CreateProjectRequest, request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc = AppBuilderService(db)
        project = await svc.create_project(
            user=user,
            name=req.name,
            description=req.description,
            platform=req.platform,
        )
        await db.commit()
        return {
            "ok": True,
            "project_id": str(project.id),
            "name": project.name,
            "status": project.status.value,
            "disclaimer_agreed": project.disclaimer_agreed,
            "disclaimer_text": DISCLAIMER_TEXT,
        }


# ── GET /api/appbuilder/projects ──────────────────────────────────────────────
@router.get("/projects")
async def list_projects(request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc = AppBuilderService(db)
        projects = await svc.list_projects(user.id)
        return {
            "ok": True,
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "platform": p.platform,
                    "status": p.status.value,
                    "current_version": p.current_version,
                    "listed_on_marketplace": p.listed_on_marketplace,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in projects
            ],
        }


# ── POST /api/appbuilder/projects/{project_id}/agree ─────────────────────────
@router.post("/projects/{project_id}/agree")
async def agree_disclaimer(project_id: UUID, request: Request):
    """User confirms they've read the disclaimer. Required before first build."""
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc = AppBuilderService(db)
        project = await svc.agree_disclaimer(project_id, user.id)
        await db.commit()
        return {"ok": True, "project_id": str(project.id), "disclaimer_agreed": True}


# ── POST /api/appbuilder/projects/{project_id}/build ─────────────────────────
class BuildStepRequest(BaseModel):
    message: str   # user's instruction for this step


@router.post("/projects/{project_id}/build")
async def build_step(project_id: UUID, req: BuildStepRequest, request: Request):
    """
    One agentic build iteration.
    Returns plan + code + notes + warnings immediately (streamed in future).
    """
    telegram_id = _require_tg_id(request)

    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc = AppBuilderService(db)
        ds = DeepSeekService()

        try:
            step = await svc.build_step(
                project_id=project_id,
                user_id=user.id,
                user_message=req.message,
                deepseek_service=ds,
            )
            await db.commit()
        except ValueError as e:
            raise HTTPException(400, str(e))

        return {
            "ok": True,
            "step_id": str(step.id),
            "step_number": step.step_number,
            "status": step.status.value,
            "plan": step.agent_plan,
            "code_diff": step.code_diff,
            "full_code": step.full_code,
            "agent_notes": step.agent_notes,
            "warnings": step.warnings or [],
        }


# ── GET /api/appbuilder/projects/{project_id} ─────────────────────────────────
@router.get("/projects/{project_id}")
async def get_project(project_id: UUID, request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc = AppBuilderService(db)
        project = await svc.get_project(project_id, user.id)

        # Load steps
        from sqlalchemy import select as sa_select
        from db.models_appbuilder import AppBuildStep
        steps_r = await db.execute(
            sa_select(AppBuildStep)
            .where(AppBuildStep.project_id == project_id)
            .order_by(AppBuildStep.step_number)
        )
        steps = steps_r.scalars().all()

        return {
            "ok": True,
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "platform": project.platform,
            "status": project.status.value,
            "disclaimer_agreed": project.disclaimer_agreed,
            "current_code": project.current_code,
            "current_version": project.current_version,
            "listed_on_marketplace": project.listed_on_marketplace,
            "steps": [
                {
                    "step_number": s.step_number,
                    "user_message": s.user_message,
                    "plan": s.agent_plan,
                    "agent_notes": s.agent_notes,
                    "warnings": s.warnings or [],
                    "status": s.status.value,
                    "created_at": s.created_at.isoformat(),
                }
                for s in steps
            ],
        }


# ── GET /api/appbuilder/projects/{project_id}/download ───────────────────────
@router.get("/projects/{project_id}/download")
async def download_code(project_id: UUID, request: Request):
    """Download the latest generated code as a file."""
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc = AppBuilderService(db)
        project = await svc.get_project(project_id, user.id)

    if not project.current_code:
        raise HTTPException(404, "No code generated yet")

    ext_map = {"mql5": "mq5", "mql4": "mq4", "pine": "pine", "python": "py"}
    ext = ext_map.get(project.platform, "txt")
    filename = f"{project.name.replace(' ', '_')}_v{project.current_version}.{ext}"

    from fastapi.responses import Response
    return Response(
        content=project.current_code,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── POST /api/appbuilder/projects/{project_id}/build/stream ──────────────────
@router.post("/projects/{project_id}/build/stream")
async def build_step_stream(project_id: UUID, req: BuildStepRequest, request: Request):
    """
    Streaming version of the build endpoint.
    Returns Server-Sent Events so the Mini App and extension
    show the PLAN → CODE → REVIEW building token by token in real time.

    Client usage (JS):
        const es = new EventSource("/api/appbuilder/projects/{id}/build/stream");
        es.onmessage = (e) => appendToChat(e.data);
        es.addEventListener("done", () => es.close());
        es.addEventListener("error_event", (e) => showError(e.data));
    """
    telegram_id = _require_tg_id(request)

    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    async with AsyncSessionLocal() as db:
        user = await _require_access(telegram_id, db)
        svc  = AppBuilderService(db)

        project = await svc.get_project(project_id, user.id)
        if not project.disclaimer_agreed:
            raise HTTPException(400, "Disclaimer not agreed")

        from sqlalchemy import select as sa_select
        from db.models_appbuilder import AppBuildStep
        steps_r = await db.execute(
            sa_select(AppBuildStep)
            .where(AppBuildStep.project_id == project_id)
            .order_by(AppBuildStep.step_number)
        )
        existing_steps = steps_r.scalars().all()
        step_number = len(existing_steps) + 1

        # Build message history
        messages = svc._build_messages(project, existing_steps, req.message)

        # Create step record (status=planning)
        from db.models_appbuilder import BuildStatus
        step = AppBuildStep(
            project_id=project_id,
            step_number=step_number,
            user_message=req.message,
            status=BuildStatus.PLANNING,
        )
        db.add(step)
        await db.flush()
        step_id = step.id
        await db.commit()

    from services.deepseek import DeepSeekService
    ds = DeepSeekService()

    async def event_generator():
        full_text = ""
        try:
            async for chunk in ds.chat_stream(messages, max_tokens=2000):
                full_text += chunk
                # Escape newlines for SSE
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"

            # Parse completed response and save step
            import json, re
            clean = re.sub(r"```json|```", "", full_text).strip()
            try:
                parsed = json.loads(clean)
            except Exception:
                parsed = {"plan": "", "code_diff": "", "full_code": full_text,
                          "agent_notes": full_text, "warnings": []}

            async with AsyncSessionLocal() as db2:
                from sqlalchemy import select as sa_select2
                res = await db2.execute(
                    sa_select2(AppBuildStep).where(AppBuildStep.id == step_id)
                )
                step2 = res.scalar_one_or_none()
                if step2:
                    step2.agent_plan   = parsed.get("plan", "")
                    step2.code_diff    = parsed.get("code_diff", "")
                    step2.full_code    = parsed.get("full_code", "")
                    step2.agent_notes  = parsed.get("agent_notes", "")
                    step2.warnings     = parsed.get("warnings", [])
                    step2.status       = BuildStatus.DONE

                    # Update project current code
                    from sqlalchemy import select as sa_select3
                    from db.models_appbuilder import AppProject
                    proj_res = await db2.execute(
                        sa_select3(AppProject).where(AppProject.id == project_id)
                    )
                    proj2 = proj_res.scalar_one_or_none()
                    if proj2 and parsed.get("full_code"):
                        proj2.current_code    = parsed["full_code"]
                        proj2.current_version = step_number
                        proj2.status          = BuildStatus.DONE
                    await db2.commit()

            # Send final metadata event
            import json as json2
            meta = json2.dumps({
                "step_number": step_number,
                "warnings":    parsed.get("warnings", []),
                "has_code":    bool(parsed.get("full_code")),
            })
            yield f"event: done\ndata: {meta}\n\n"

        except Exception as e:
            yield f"event: error_event\ndata: {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

