"""
auth.py — Supabase JWT verification for per-user data.

A FastAPI dependency `current_user_id` reads the `Authorization: Bearer <token>` header,
verifies the Supabase-issued JWT locally (HS256 with the project's JWT secret), and
returns the user's id (the token's `sub`). If there is no/invalid token, it returns the
shared sentinel "public" — so the app keeps working for anonymous users (everyone shares
the "public" data), and only signed-in users get their own.

Setup: set SUPABASE_JWT_SECRET on the backend (Supabase → Settings → API → JWT Secret).
If it is not set, auth is effectively disabled and everyone is "public" (safe default).
"""

import os
from fastapi import Header

_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()
PUBLIC_USER = "public"

try:
    import jwt  # PyJWT
except Exception:  # pragma: no cover
    jwt = None


def _decode(token: str) -> str | None:
    if not (_JWT_SECRET and jwt and token):
        return None
    try:
        payload = jwt.decode(
            token, _JWT_SECRET, algorithms=["HS256"],
            audience="authenticated", options={"verify_aud": False},
        )
        return payload.get("sub")
    except Exception:
        return None


def current_user_id(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency → the signed-in user's id, or 'public' if anonymous.

    Usage:
        @app.get("/watchlist")
        def get_watchlist(user_id: str = Depends(current_user_id)):
            ...
    """
    if authorization and authorization.lower().startswith("bearer "):
        uid = _decode(authorization.split(" ", 1)[1].strip())
        if uid:
            return uid
    return PUBLIC_USER


def auth_enabled() -> bool:
    return bool(_JWT_SECRET and jwt)
