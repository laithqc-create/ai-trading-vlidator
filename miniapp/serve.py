"""
miniapp/serve.py — Serve the Telegram Mini App static files via FastAPI.

The Mini App is a single HTML file served at /app
Telegram WebApp opens it via the bot's menu button URL.

Register the Mini App URL in BotFather:
  /mybots → your bot → Bot Settings → Menu Button → set URL to:
  https://your-domain.com/app
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import os

router = APIRouter(tags=["miniapp"])

MINIAPP_DIR = Path(__file__).parent


@router.get("/app", response_class=HTMLResponse)
async def serve_miniapp():
    """Serve the Telegram Mini App."""
    html_file = MINIAPP_DIR / "index.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    return HTMLResponse("<h1>Mini App not found</h1>", status_code=404)


@router.get("/app/health")
async def miniapp_health():
    return {"status": "ok", "miniapp": "Trade Genius"}
