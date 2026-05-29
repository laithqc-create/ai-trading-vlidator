"""
pattern_editor/endpoints.py
Per-pattern candle rule editor API.
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from db.database import AsyncSessionLocal
from services.user import UserService
from services.pattern_engine import SYSTEM_RULES, PATTERN_DESCRIPTIONS

router = APIRouter(prefix="/api/patterns", tags=["patterns"])

def _require_tg_id(request: Request) -> int:
    tid = request.headers.get("X-Telegram-User-Id", "")
    if not tid.isdigit():
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    return int(tid)

@router.get("")
async def get_patterns(request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        personal_rules = await user_svc.get_personal_rules_structured(user.id)

    patterns = []
    for name, sys_rule in SYSTEM_RULES.items():
        user_rule = personal_rules.get(name, {})
        patterns.append({
            "name":           name,
            "display_name":   name.replace("_", " ").title(),
            "description":    PATTERN_DESCRIPTIONS.get(name, ""),
            "enabled":        user_rule.get("enabled", sys_rule.enabled),
            "system_rule": {
                "min_body_ratio":   sys_rule.min_body_ratio,
                "max_wick_ratio":   sys_rule.max_wick_ratio,
                "min_engulf_ratio": sys_rule.min_engulf_ratio,
            },
            "user_rule": {
                "min_body_ratio":   user_rule.get("min_body_ratio"),
                "max_wick_ratio":   user_rule.get("max_wick_ratio"),
                "min_engulf_ratio": user_rule.get("min_engulf_ratio"),
            },
            "has_user_override": bool(user_rule),
        })

    return {
        "ok": True,
        "disclaimer": "This system is an analytical tool only. Pattern detection does not constitute financial advice.",
        "patterns": patterns,
    }

class PatternUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    min_body_ratio:   Optional[float] = None
    max_wick_ratio:   Optional[float] = None
    min_engulf_ratio: Optional[float] = None
    reset_to_system:  bool = False

@router.patch("/{pattern_name}")
async def update_pattern_rule(pattern_name: str, req: PatternUpdateRequest, request: Request):
    telegram_id = _require_tg_id(request)
    if pattern_name not in SYSTEM_RULES:
        raise HTTPException(404, f"Unknown pattern: {pattern_name}")
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        if req.reset_to_system:
            await user_svc.delete_pattern_rule(user.id, pattern_name)
            await db.commit()
            return {"ok": True, "message": f"'{pattern_name}' reset to system defaults."}
        update = {}
        if req.enabled is not None:           update["enabled"] = req.enabled
        if req.min_body_ratio is not None:    update["min_body_ratio"] = req.min_body_ratio
        if req.max_wick_ratio is not None:    update["max_wick_ratio"] = req.max_wick_ratio
        if req.min_engulf_ratio is not None:  update["min_engulf_ratio"] = req.min_engulf_ratio
        await user_svc.upsert_pattern_rule(user.id, pattern_name, update)
        await db.commit()
    return {"ok": True, "pattern": pattern_name, "updated": update}

@router.post("/reset")
async def reset_all_patterns(request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        await user_svc.delete_all_pattern_rules(user.id)
        await db.commit()
    return {"ok": True, "message": "All pattern rules reset to system defaults."}
