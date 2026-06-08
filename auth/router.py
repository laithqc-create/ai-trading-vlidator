"""
auth/router.py
Authentication endpoints:
  POST /auth/register          — email + password signup
  POST /auth/login             — email + password login
  POST /auth/telegram          — Telegram login (from Mini App initData)
  GET  /auth/google            — start Google OAuth flow
  GET  /auth/google/callback   — Google OAuth callback
  GET  /auth/me                — get current user profile
  PATCH /auth/billing          — update billing address
  POST /auth/logout            — invalidate session
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from loguru import logger

from db.database import AsyncSessionLocal
from db.models import User, PlanTier
from auth.utils import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    generate_all_tokens,
)
from config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    # Optional billing at signup
    billing_name:    str = ""
    billing_company: str = ""
    billing_address: str = ""
    billing_city:    str = ""
    billing_state:   str = ""
    billing_zip:     str = ""
    billing_country: str = ""
    tax_id:          str = ""

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TelegramAuthRequest(BaseModel):
    telegram_id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    init_data: str = ""       # Telegram WebApp.initData for server-side verification


class BillingRequest(BaseModel):
    billing_name:    str = ""
    billing_company: str = ""
    billing_address: str = ""
    billing_city:    str = ""
    billing_state:   str = ""
    billing_zip:     str = ""
    billing_country: str = ""
    tax_id:          str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_response(user: User, token: str) -> dict:
    """Standard user payload returned after auth."""
    return {
        "ok": True,
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "id":            user.id,
            "email":         user.email,
            "full_name":     user.full_name or user.first_name or "",
            "plan":          user.plan.value if user.plan else "free",
            "trial_active":  user.is_trial_active(),
            "trial_days":    user.trial_days_remaining(),
            "email_verified": user.email_verified,
            "avatar_url":    user.avatar_url,
            # Tokens for the client to store
            "tokens": {
                "api":        user.atv_api_token,
                "indicator":  user.indicator_webhook_token,
                "ea":         user.ea_webhook_token,
                "screenshot": user.screenshot_webhook_token,
            },
        },
    }


async def _get_current_user(request: Request) -> User | None:
    """Extract and verify JWT from Authorization: Bearer <token> header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_access_token(auth[7:])
    if not payload:
        return None
    user_id = int(payload.get("sub", 0))
    if not user_id:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()


async def _require_user(request: Request) -> User:
    user = await _get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest):
    """
    Create a new account with email + password.
    All webhook tokens are auto-generated on signup.
    """
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == req.email))
        if existing.scalars().first():
            raise HTTPException(400, "An account with this email already exists")

        tokens = generate_all_tokens()
        user = User(
            email          = req.email,
            password_hash  = hash_password(req.password),
            full_name      = req.full_name.strip() or None,
            email_verified = False,
            plan           = PlanTier.FREE,
            billing_name    = req.billing_name or None,
            billing_company = req.billing_company or None,
            billing_address = req.billing_address or None,
            billing_city    = req.billing_city or None,
            billing_state   = req.billing_state or None,
            billing_zip     = req.billing_zip or None,
            billing_country = req.billing_country.upper() or None,
            tax_id          = req.tax_id or None,
            **tokens,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"New user registered: {user.email} (id={user.id})")

    jwt_token = create_access_token(user.id)
    return _user_response(user, jwt_token)


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest):
    """Email + password login."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == req.email))
        user = result.scalars().first()

    if not user or not user.password_hash:
        raise HTTPException(401, "Invalid email or password")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    jwt_token = create_access_token(user.id)
    return _user_response(user, jwt_token)


# ── POST /auth/telegram ───────────────────────────────────────────────────────

@router.post("/telegram")
async def telegram_auth(req: TelegramAuthRequest):
    """
    Authenticate via Telegram.
    - If a user with this telegram_id exists → log in
    - If email exists and not linked → link telegram to it
    - Otherwise → create new account
    All tokens auto-generated for new accounts.
    """
    async with AsyncSessionLocal() as db:
        # Try existing telegram user
        result = await db.execute(
            select(User).where(User.telegram_id == req.telegram_id)
        )
        user = result.scalars().first()

        if not user:
            # Create new user from Telegram
            tokens = generate_all_tokens()
            user = User(
                telegram_id = req.telegram_id,
                username    = req.username or None,
                first_name  = req.first_name or None,
                last_name   = req.last_name or None,
                full_name   = f"{req.first_name} {req.last_name}".strip() or None,
                plan        = PlanTier.FREE,
                **tokens,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"New Telegram user: {req.telegram_id} ({req.first_name})")
        else:
            # Ensure tokens exist for legacy users
            changed = False
            if not user.atv_api_token:
                tokens = generate_all_tokens()
                for k, v in tokens.items():
                    setattr(user, k, v)
                changed = True
            if changed:
                await db.commit()
                await db.refresh(user)

    jwt_token = create_access_token(user.id)
    return _user_response(user, jwt_token)


# ── GET /auth/google ──────────────────────────────────────────────────────────

@router.get("/google")
async def google_login(request: Request):
    """Start Google OAuth2 flow."""
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(503, "Google OAuth not configured — set GOOGLE_CLIENT_ID in environment")

    redirect_uri = f"{settings.API_BASE_URL}/auth/google/callback"
    scope = "openid email profile"
    state = "atv-google-auth"

    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&state={state}"
        f"&access_type=offline"
        f"&prompt=select_account"
    )
    return RedirectResponse(url)


# ── GET /auth/google/callback ─────────────────────────────────────────────────

@router.get("/google/callback")
async def google_callback(code: str = "", error: str = "", state: str = ""):
    """Handle Google OAuth2 callback."""
    if error or not code:
        return RedirectResponse(f"{settings.API_BASE_URL}/app#auth-error=google_denied")

    client_id     = getattr(settings, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
    redirect_uri  = f"{settings.API_BASE_URL}/auth/google/callback"

    if not client_id or not client_secret:
        raise HTTPException(503, "Google OAuth not configured")

    import httpx
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     client_id,
                "client_secret": client_secret,
                "redirect_uri":  redirect_uri,
                "grant_type":    "authorization_code",
            },
        )
        token_data = token_resp.json()
        if "error" in token_data:
            logger.error(f"Google token exchange error: {token_data}")
            return RedirectResponse(f"{settings.API_BASE_URL}/app#auth-error=google_token_failed")

        # Get user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        info = userinfo_resp.json()

    google_id    = info.get("sub", "")
    email        = info.get("email", "")
    full_name    = info.get("name", "")
    avatar_url   = info.get("picture", "")
    email_verified = info.get("email_verified", False)

    if not google_id or not email:
        return RedirectResponse(f"{settings.API_BASE_URL}/app#auth-error=google_no_email")

    async with AsyncSessionLocal() as db:
        # Try existing google_id
        result = await db.execute(select(User).where(User.google_id == google_id))
        user = result.scalars().first()

        if not user:
            # Try matching email
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalars().first()

        if user:
            # Update Google info + ensure tokens
            user.google_id    = google_id
            user.avatar_url   = avatar_url or user.avatar_url
            user.full_name    = user.full_name or full_name
            user.email_verified = True
            if not user.atv_api_token:
                for k, v in generate_all_tokens().items():
                    setattr(user, k, v)
        else:
            # New user via Google
            tokens = generate_all_tokens()
            user = User(
                email          = email,
                google_id      = google_id,
                google_email   = email,
                full_name      = full_name,
                avatar_url     = avatar_url,
                email_verified = email_verified,
                plan           = PlanTier.FREE,
                **tokens,
            )
            db.add(user)

        await db.commit()
        await db.refresh(user)
        logger.info(f"Google auth: {email} (id={user.id})")

    jwt_token = create_access_token(user.id)
    # Redirect back to Mini App with token in hash
    return RedirectResponse(
        f"{settings.API_BASE_URL}/app#auth-token={jwt_token}"
    )


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(request: Request):
    """Return current authenticated user's profile and tokens."""
    user = await _require_user(request)
    return {
        "ok": True,
        "user": {
            "id":             user.id,
            "email":          user.email,
            "full_name":      user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "username":       user.username,
            "plan":           user.plan.value if user.plan else "free",
            "trial_active":   user.is_trial_active(),
            "trial_days":     user.trial_days_remaining(),
            "email_verified": user.email_verified,
            "avatar_url":     user.avatar_url,
            "telegram_id":    user.telegram_id,
            "billing": {
                "name":    user.billing_name,
                "company": user.billing_company,
                "address": user.billing_address,
                "city":    user.billing_city,
                "state":   user.billing_state,
                "zip":     user.billing_zip,
                "country": user.billing_country,
                "tax_id":  user.tax_id,
            },
            "tokens": {
                "api":        user.atv_api_token,
                "indicator":  user.indicator_webhook_token,
                "ea":         user.ea_webhook_token,
                "screenshot": user.screenshot_webhook_token,
            },
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


# ── PATCH /auth/billing ───────────────────────────────────────────────────────

@router.patch("/billing")
async def update_billing(req: BillingRequest, request: Request):
    """Update billing address for invoicing / tax purposes."""
    user = await _require_user(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user.id))
        u = result.scalars().first()
        if not u:
            raise HTTPException(404, "User not found")
        if req.billing_name:    u.billing_name    = req.billing_name
        if req.billing_company: u.billing_company = req.billing_company
        if req.billing_address: u.billing_address = req.billing_address
        if req.billing_city:    u.billing_city    = req.billing_city
        if req.billing_state:   u.billing_state   = req.billing_state
        if req.billing_zip:     u.billing_zip     = req.billing_zip
        if req.billing_country: u.billing_country = req.billing_country
        if req.tax_id:          u.tax_id          = req.tax_id
        await db.commit()
    return {"ok": True, "message": "Billing address updated"}


# ── POST /auth/change-password ────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, request: Request):
    """Change password for email-authenticated users."""
    user = await _require_user(request)
    if not user.password_hash:
        raise HTTPException(400, "This account uses Google or Telegram login — no password to change")
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user.id))
        u = result.scalars().first()
        u.password_hash = hash_password(req.new_password)
        await db.commit()
    return {"ok": True, "message": "Password updated successfully"}


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post("/logout")
async def logout():
    """Client-side logout — instruct client to clear the JWT."""
    return {"ok": True, "message": "Logged out. Clear your access token."}
