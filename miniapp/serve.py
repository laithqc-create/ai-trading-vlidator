"""
miniapp/serve.py — Serve Mini App static files via FastAPI.

Routes:
  GET /app                → index.html (main Mini App)
  GET /app/pattern-rules  → pattern_editor.html
  GET /app/purchase.js    → purchase_patch.js
  GET /app/health         → health check

Register the Mini App URL in BotFather:
  /mybots → your bot → Bot Settings → Menu Button → URL:
  https://your-domain.com/app
"""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pathlib import Path

router = APIRouter(tags=["miniapp"])

MINIAPP_DIR = Path(__file__).parent

NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _inject_api_base(html: str, api_base: str) -> str:
    """
    Inject window.API_BASE before </head> so the Mini App works on any domain
    without hardcoding a URL in the static HTML file.
    """
    injection = f'<script>window.API_BASE = {repr(api_base)};</script>\n'
    if "</head>" in html:
        return html.replace("</head>", injection + "</head>", 1)
    # Fallback: prepend to <body>
    return html.replace("<body>", injection + "<body>", 1)


def _serve_html(filename: str, api_base: str = "") -> HTMLResponse:
    f = MINIAPP_DIR / filename
    if f.exists():
        content = f.read_text(encoding="utf-8")
        if api_base:
            content = _inject_api_base(content, api_base)
        return HTMLResponse(content=content, media_type="text/html", headers=NO_CACHE)
    return HTMLResponse("<h1>Not found</h1>", status_code=404)


def _get_api_base(request: Request) -> str:
    """
    Derive API base URL from the incoming request so the Mini App
    always calls back to the same domain it was served from.
    Falls back to settings.API_BASE_URL if configured.
    """
    try:
        from config.settings import settings
        if settings.API_BASE_URL and not settings.API_BASE_URL.startswith("https://example"):
            return settings.API_BASE_URL.rstrip("/")
    except Exception:
        pass
    # Derive from request: same scheme + host
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}"


@router.get("/app", response_class=HTMLResponse)
async def serve_miniapp(request: Request):
    return _serve_html("index.html", api_base=_get_api_base(request))


@router.get("/app/pattern-rules", response_class=HTMLResponse)
async def serve_pattern_editor(request: Request):
    return _serve_html("pattern_editor.html", api_base=_get_api_base(request))


@router.get("/app/login", response_class=HTMLResponse)
async def serve_login(request: Request):
    return _serve_html("login.html", api_base=_get_api_base(request))


@router.get("/app/indicators", response_class=HTMLResponse)
async def serve_indicator_selector(request: Request):
    return _serve_html("indicator_selector.html", api_base=_get_api_base(request))


@router.get("/app/purchase.js")
async def serve_purchase_js():
    f = MINIAPP_DIR / "purchase_patch.js"
    if f.exists():
        return Response(content=f.read_text(encoding="utf-8"),
                        media_type="application/javascript", headers=NO_CACHE)
    return Response("// not found", status_code=404)


@router.get("/app/health")
async def miniapp_health():
    return {"status": "ok", "miniapp": "AI Trade Validator"}
