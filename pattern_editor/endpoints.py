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
from services.auth_helpers import resolve_user
from services.pattern_engine import SYSTEM_RULES, PATTERN_DESCRIPTIONS, PATTERN_CATEGORIES

router = APIRouter(prefix="/api/patterns", tags=["patterns"])

@router.get("")
async def get_patterns(request: Request):
    async with AsyncSessionLocal() as db:
        user = await resolve_user(request, db, require=True)
        user_svc = UserService(db)
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
        "categories": PATTERN_CATEGORIES,
        "total": len(patterns),
    }

class PatternUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    min_body_ratio:   Optional[float] = None
    max_wick_ratio:   Optional[float] = None
    min_engulf_ratio: Optional[float] = None
    reset_to_system:  bool = False

@router.patch("/{pattern_name}")
async def update_pattern_rule(pattern_name: str, req: PatternUpdateRequest, request: Request):
    if pattern_name not in SYSTEM_RULES:
        raise HTTPException(404, f"Unknown pattern: {pattern_name}")
    async with AsyncSessionLocal() as db:
        user = await resolve_user(request, db, require=True)
        user_svc = UserService(db)
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
    async with AsyncSessionLocal() as db:
        user = await resolve_user(request, db, require=True)
        user_svc = UserService(db)
        await user_svc.delete_all_pattern_rules(user.id)
        await db.commit()
    return {"ok": True, "message": "All pattern rules reset to system defaults."}


# ════════════════════════════════════════════════════════════════════════════
# INDICATOR PREFERENCES
# ════════════════════════════════════════════════════════════════════════════
from services.indicator_engine import INDICATOR_DEFAULTS, INDICATOR_GROUPS, INDICATOR_DISPLAY
from typing import Optional as Opt

# Separate router (no /api/patterns prefix) — mounted directly at /api/indicators*
indicators_router = APIRouter(tags=["indicators"])


@indicators_router.get("/api/indicators")
async def get_indicators(request: Request):
    """
    Return all 30+ indicators with defaults and user settings.
    Called by Mini App indicator selector and extension settings tab.
    
    If user is authenticated: return user's saved preferences
    If not authenticated: return all indicators with system defaults
    """
    async with AsyncSessionLocal() as db:
        user = await resolve_user(request, db, require=False)  # Optional auth
        
        enabled = None
        settings = {}
        
        if user:
            user_svc = UserService(db)
            enabled = await user_svc.get_enabled_indicators(user.id)
            settings = await user_svc.get_indicator_settings(user.id)

    indicators = []
    for name, defaults in INDICATOR_DEFAULTS.items():
        group = next((g for g, names in INDICATOR_GROUPS.items() if name in names), "other")
        indicators.append({
            "name":     name,
            "display":  INDICATOR_DISPLAY.get(name, name),
            "group":    group,
            "enabled":  (enabled is None) or (name in (enabled or [])),
            "defaults": defaults,
            "settings": settings.get(name, {}),
        })

    return {
        "ok": True,
        "indicators": indicators,
        "groups": {g: {"label": g.replace("_", " ").title(),
                       "names": names}
                   for g, names in INDICATOR_GROUPS.items()},
    }


class IndicatorPrefRequest(BaseModel):
    enabled: Opt[list] = None      # None = all; [] = none; ["rsi","macd"] = subset
    settings: Opt[dict] = None     # {name: {period: 21}} etc.


@indicators_router.post("/api/indicators/prefs")
async def save_indicator_prefs(req: IndicatorPrefRequest, request: Request):
    """Save user's indicator enabled list and custom settings."""
    async with AsyncSessionLocal() as db:
        user = await resolve_user(request, db, require=True)
        user_svc = UserService(db)
        await user_svc.upsert_indicator_prefs(user.id,
                                               enabled=req.enabled,
                                               settings=req.settings)
        await db.commit()
    return {"ok": True, "message": "Indicator preferences saved."}


@indicators_router.post("/api/indicators/reset")
async def reset_indicator_prefs(request: Request):
    """Reset all indicator preferences to system defaults."""
    async with AsyncSessionLocal() as db:
        user = await resolve_user(request, db, require=True)
        user_svc = UserService(db)
        await user_svc.upsert_indicator_prefs(user.id, enabled=None, settings={})
        await db.commit()
    return {"ok": True, "message": "Indicator preferences reset to defaults."}
