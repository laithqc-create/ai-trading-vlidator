"""
services/auth_helpers.py
Shared user-resolution helper used by main.py, pattern_editor, appbuilder,
marketplace, and any other router needing authenticated user context.

Triple-auth — accepts:
  • Authorization: Bearer <jwt>   (web login — email/Google/Telegram OAuth)
  • X-ATV-Token: <token>          (Chrome Extension standalone)
  • X-Telegram-User-Id: <int>     (Telegram Mini App)
"""
from fastapi import Request, HTTPException
from sqlalchemy import select
from db.models import User


async def resolve_user(request: Request, db, require: bool = True):
    """Returns User object or None (if require=False) / raises 401 (if require=True)."""
    from services.user import UserService
    user_svc = UserService(db)

    # 1. JWT Bearer (web login)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from auth.utils import decode_access_token
        payload = decode_access_token(auth_header[7:])
        if payload:
            user_id = int(payload.get("sub", 0))
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()
                if user:
                    return user

    # 2. ATV token (extension)
    token = request.headers.get("X-ATV-Token", "").strip()
    if token:
        user = await user_svc.get_user_by_token(token, token_type="any")
        if user:
            return user
        if require:
            raise HTTPException(401, "Invalid token")
        return None

    # 3. Telegram ID (Mini App)
    tid_str = request.headers.get("X-Telegram-User-Id", "").strip()
    if tid_str and tid_str.isdigit():
        return await user_svc.get_or_create_user(telegram_id=int(tid_str))

    if require:
        raise HTTPException(401, "Missing auth: provide Authorization Bearer, X-ATV-Token, or X-Telegram-User-Id")
    return None
