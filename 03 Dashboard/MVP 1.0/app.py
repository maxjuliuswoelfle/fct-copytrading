"""
(C) app.py — Dashboard Entry Point

Starten mit: uvicorn app:app --host 0.0.0.0 --port 8443
"""

import os
import sys
import time
from collections import defaultdict

# Bot-Core Pfad hinzufuegen damit wir database.py importieren koennen
BOT_CORE_PATH = os.path.join(os.path.dirname(__file__), "..", "01 Bot-Core")
sys.path.insert(0, BOT_CORE_PATH)

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse

from db import get_db
from dash_auth import get_current_user, CSRF_COOKIE
from routes import auth_routes, dashboard_routes, api_routes, legal_routes, signup_routes, webhook_routes, welcome_routes
import secrets

app = FastAPI(title="Copy Trading Dashboard", docs_url=None, redoc_url=None)

# Static Files + Templates
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Routes
app.include_router(auth_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(api_routes.router, prefix="/api")
app.include_router(legal_routes.router)
app.include_router(signup_routes.router)
app.include_router(webhook_routes.router)
app.include_router(welcome_routes.router)


# ==========================================================================
# CSRF COOKIE MIDDLEWARE — sets csrf_token cookie if not present
# ==========================================================================
@app.middleware("http")
async def csrf_cookie_middleware(request: Request, call_next):
    response = await call_next(request)
    if not request.cookies.get(CSRF_COOKIE):
        response.set_cookie(
            CSRF_COOKIE, secrets.token_hex(32),
            httponly=False, samesite="strict", secure=True,
        )
    return response


# ==========================================================================
# SECURITY HEADERS MIDDLEWARE
# ==========================================================================
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://fast.wistia.com https://fast.wistia.net; "
        "style-src 'self' 'unsafe-inline' fonts.googleapis.com https://fast.wistia.com https://fast.wistia.net; "
        "font-src fonts.gstatic.com https://fast.wistia.com https://fast.wistia.net; "
        "img-src 'self' data: https://*.wistia.com https://*.wistia.net https://embedwistia-a.akamaihd.net https://embed-ssl.wistia.com; "
        "media-src 'self' blob: https://*.wistia.com https://*.wistia.net https://*.akamaihd.net https://*.cloudfront.net; "
        "connect-src 'self' https://*.wistia.com https://*.wistia.net https://*.akamaihd.net; "
        "frame-src https://fast.wistia.net https://fast.wistia.com;"
    )
    return response


# ==========================================================================
# RATE LIMITING MIDDLEWARE
# ==========================================================================
# Simple in-memory rate limiter — no external dependencies needed
_rate_limits: dict[str, list[float]] = defaultdict(list)

# Config: path -> (max_requests, window_seconds)
_RATE_CONFIG = {
    "/login": (5, 60),           # 5 attempts per minute
    "/signup/copytrading": (10, 3600),  # 10 per hour
    "/forgot-password": (5, 900), # 5 per 15 minutes
    "/resend-verification": (5, 900),
    "/signup/signals": (10, 3600), # 10 per hour
    "/welcome": (10, 3600),        # 10 per hour
}

def _is_rate_limited(ip: str, path: str) -> bool:
    """Check if IP is rate-limited for a given path."""
    config = _RATE_CONFIG.get(path)
    if not config:
        return False
    max_req, window = config
    key = f"{ip}:{path}"
    now = time.time()
    # Clean old entries
    _rate_limits[key] = [t for t in _rate_limits[key] if t > now - window]
    if len(_rate_limits[key]) >= max_req:
        return True
    _rate_limits[key].append(now)
    return False

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "POST" and request.url.path in _RATE_CONFIG:
        ip = request.client.host if request.client else "unknown"
        if _is_rate_limited(ip, request.url.path):
            return JSONResponse(
                status_code=429,
                content={"detail": "Zu viele Anfragen. Bitte versuche es später erneut."},
            )
    return await call_next(request)


# ==========================================================================
# ROUTES
# ==========================================================================
@app.get("/")
async def root():
    return RedirectResponse(url="/login")
