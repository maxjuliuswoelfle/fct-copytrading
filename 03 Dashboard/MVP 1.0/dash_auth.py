"""
(C) auth.py — Authentifizierung fuer das Dashboard

Einfaches Session-basiertes Auth mit bcrypt Passwort-Hashing.
"""

import secrets
from datetime import datetime, timedelta
from fastapi import Request, HTTPException

import bcrypt

from db import get_db

SESSION_COOKIE = "session_token"
CSRF_COOKIE = "csrf_token"
SESSION_DAYS = 7


def hash_password(password: str) -> str:
    """Passwort mit bcrypt hashen."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Passwort gegen Hash pruefen."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session(customer_id: str) -> str:
    """Neue Session erstellen und Token zurueckgeben."""
    db = get_db()
    token = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(days=SESSION_DAYS)).isoformat()
    db.set_session(customer_id, token, expires)
    return token


def get_current_user(request: Request) -> dict | None:
    """Aktuellen User aus Session-Cookie laden. None wenn nicht eingeloggt."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    db = get_db()
    return db.get_user_by_session(token)


def require_auth(request: Request) -> dict:
    """Wirft 401 wenn nicht eingeloggt."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Nicht eingeloggt")
    return user


def generate_csrf(request: Request, response=None) -> str:
    """CSRF-Token generieren oder bestehenden aus Cookie lesen."""
    token = request.cookies.get(CSRF_COOKIE)
    if not token:
        token = secrets.token_hex(32)
        if response:
            response.set_cookie(
                CSRF_COOKIE, token,
                httponly=False,  # JS muss lesen koennen
                samesite="strict",
                secure=True,
            )
    return token


def verify_csrf(request: Request, form_token: str) -> bool:
    """CSRF-Token aus Form gegen Cookie pruefen (Double-Submit Pattern)."""
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not form_token:
        return False
    return secrets.compare_digest(cookie_token, form_token)
