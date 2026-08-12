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


def _decode_payload(token: str) -> dict | None:
    if not (_JWT_SECRET and jwt and token):
        return None
    try:
        return jwt.decode(
            token, _JWT_SECRET, algorithms=["HS256"],
            audience="authenticated", options={"verify_aud": False},
        )
    except Exception:
        return None


def _unverified_sub(token: str) -> str | None:
    """
    Read `sub` WITHOUT checking the signature.

    Only used when SUPABASE_JWT_SECRET is unset. Without it every signed-in user
    collapsed to the shared "public" id, which meant they all read and wrote the
    same watchlist, portfolio and simulations — one user could see another's
    data. Separating on the unverified `sub` fixes that immediately.

    This is NOT a security boundary: an unverified token can be forged, so a
    determined attacker could still address someone else's rows. It is strictly
    better than co-mingling everyone by default, and it is a stopgap — set
    SUPABASE_JWT_SECRET to get real verification.
    """
    if not (jwt and token):
        return None
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get("sub")
    except Exception:
        return None


def _decode(token: str) -> str | None:
    payload = _decode_payload(token)
    if payload:
        return payload.get("sub")
    if not _JWT_SECRET:
        return _unverified_sub(token)
    return None      # secret IS set and the token failed verification — reject


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def current_user_id(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency → the signed-in user's id, or 'public' if anonymous.

    Usage:
        @app.get("/watchlist")
        def get_watchlist(user_id: str = Depends(current_user_id)):
            ...
    """
    uid = _decode(_bearer(authorization))
    return uid or PUBLIC_USER


def current_user_email(authorization: str | None = Header(default=None)) -> str | None:
    """FastAPI dependency → the signed-in user's email (from the JWT), or None
    if anonymous. Used to route alert emails to the logged-in user."""
    token = _bearer(authorization)
    payload = _decode_payload(token)
    if payload:
        return payload.get("email")
    if not _JWT_SECRET and jwt and token:
        try:
            return jwt.decode(token, options={"verify_signature": False}).get("email")
        except Exception:
            return None
    return None


def auth_enabled() -> bool:
    return bool(_JWT_SECRET and jwt)


def auth_status() -> dict:
    """Surfaced on / so a misconfigured deploy is visible instead of silent."""
    if not jwt:
        return {"verified": False,
                "detail": "PyJWT not installed — users cannot be told apart"}
    if not _JWT_SECRET:
        return {"verified": False,
                "detail": "SUPABASE_JWT_SECRET not set — users are separated by "
                          "unverified token claims, which is a stopgap, not a "
                          "security boundary. Set it in the Render dashboard."}
    return {"verified": True, "detail": "Supabase JWTs verified (HS256)"}
