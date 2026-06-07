"""
auth/utils.py
Password hashing, JWT creation/verification, secure token generation.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import settings

# ── Password hashing ──────────────────────────────────────────────────────────
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────
_SECRET  = getattr(settings, "APP_SECRET_KEY", "change-me-in-production")
_ALG     = "HS256"
_EXPIRE  = 60 * 24 * 30  # 30 days (minutes)


def create_access_token(user_id: int, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_EXPIRE),
        **(extra or {}),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALG)


def decode_access_token(token: str) -> dict | None:
    """Returns payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALG])
    except JWTError:
        return None


# ── Webhook / API token generation ────────────────────────────────────────────
_ALPHA = string.ascii_letters + string.digits


def generate_token(prefix: str = "", length: int = 32) -> str:
    """Generate a URL-safe random token like 'atv_aBcD1234…'"""
    rand = "".join(secrets.choice(_ALPHA) for _ in range(length))
    return f"{prefix}{rand}" if prefix else rand


def generate_all_tokens() -> dict[str, str]:
    """Generate all four tokens for a new user."""
    return {
        "atv_api_token":            generate_token("atv_", 32),
        "indicator_webhook_token":  generate_token("ind_", 32),
        "ea_webhook_token":         generate_token("ea_",  32),
        "screenshot_webhook_token": generate_token("ss_",  32),
    }
