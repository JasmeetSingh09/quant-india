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
import time
from fastapi import Header

_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()
PUBLIC_USER = "public"

try:
    import jwt  # PyJWT
except Exception:  # pragma: no cover
    jwt = None


_SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_JWKS_CACHE: dict = {"at": 0.0, "client": None}
_JWKS_TTL = 60 * 60


def _jwks_client():
    """
    PyJWKClient for the project's public keys, so ES256/RS256 tokens verify.

    Supabase migrated projects from a shared HS256 secret to asymmetric JWT
    Signing Keys. A project mid-migration can issue either, so we support both
    rather than assuming — verifying only HS256 would reject every new token and
    silently drop those users back into the shared "public" bucket.
    """
    if not (jwt and _SUPABASE_URL):
        return None
    now = time.time()
    if _JWKS_CACHE["client"] and now - _JWKS_CACHE["at"] < _JWKS_TTL:
        return _JWKS_CACHE["client"]
    try:
        from jwt import PyJWKClient
        c = PyJWKClient(f"{_SUPABASE_URL}/auth/v1/.well-known/jwks.json",
                        cache_keys=True, lifespan=_JWKS_TTL)
        _JWKS_CACHE.update(at=now, client=c)
        return c
    except Exception:
        return None


def _decode_payload(token: str) -> dict | None:
    """Verify against the legacy HS256 secret first, then the project's JWKS."""
    if not (jwt and token):
        return None

    if _JWT_SECRET:
        try:
            return jwt.decode(
                token, _JWT_SECRET, algorithms=["HS256"],
                audience="authenticated", options={"verify_aud": False},
            )
        except Exception:
            pass      # may simply be an asymmetric token — try JWKS below

    client = _jwks_client()
    if client:
        try:
            key = client.get_signing_key_from_jwt(token).key
            return jwt.decode(
                token, key, algorithms=["ES256", "RS256"],
                audience="authenticated", options={"verify_aud": False},
            )
        except Exception:
            return None
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


def _verification_configured() -> bool:
    return bool(jwt and (_JWT_SECRET or _SUPABASE_URL))


def _decode(token: str) -> str | None:
    payload = _decode_payload(token)
    if payload:
        return payload.get("sub")

    sub = _unverified_sub(token)
    if not sub:
        return None

    if not _verification_configured():
        # Nothing is configured — documented stopgap, separate on the raw sub.
        return sub

    # Verification IS configured but this token failed it. Returning "public"
    # here would drop every such user back into one shared bucket — the exact
    # privacy bug we are fixing. Namespacing keeps them separated AND means a
    # forged token can never address a verified user's rows, since no verified
    # id ever carries this prefix.
    return f"unverified:{sub}"


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
    if payload is None and not _JWT_SECRET and jwt and token:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
        except Exception:
            payload = None
    if not payload:
        return None

    email = _email_from_claims(payload)
    if email:
        return email

    # The token verified but carried no address. Supabase does not always put
    # `email` in the JWT — it depends on the signing key and how the account was
    # created — so ask the auth server, using the caller's own token as the
    # credential. No service key, and a user can only ever fetch themselves.
    return _email_from_supabase(token)


def _email_from_claims(payload: dict) -> str | None:
    """Where Supabase actually puts the address, in the order it tends to."""
    for value in (payload.get("email"),
                  (payload.get("user_metadata") or {}).get("email"),
                  (payload.get("app_metadata") or {}).get("email"),
                  payload.get("preferred_username")):
        if isinstance(value, str) and "@" in value:
            return value.strip()
    return None


_EMAIL_CACHE: dict[str, tuple[float, str | None]] = {}


def _email_from_supabase(token: str) -> str | None:
    """
    GET /auth/v1/user with the caller's token. Cached for a few minutes because
    this sits on a request dependency and must not add a network hop per call.
    """
    if not (_SUPABASE_URL and token):
        return None
    key = token[-32:]
    hit = _EMAIL_CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < 600:
        return hit[1]

    email = None
    try:
        import requests
        headers = {"Authorization": f"Bearer {token}"}
        anon = os.getenv("SUPABASE_ANON_KEY", "").strip()
        # Supabase's gateway wants an apikey; the user's own JWT is accepted as
        # one when no anon key is configured.
        headers["apikey"] = anon or token
        r = requests.get(f"{_SUPABASE_URL}/auth/v1/user", headers=headers, timeout=6)
        if r.status_code == 200:
            body = r.json()
            email = _email_from_claims(body if isinstance(body, dict) else {})
    except Exception:
        email = None

    if len(_EMAIL_CACHE) > 500:
        _EMAIL_CACHE.clear()
    _EMAIL_CACHE[key] = (now, email)
    return email


def auth_enabled() -> bool:
    return bool(_JWT_SECRET and jwt)


def auth_status() -> dict:
    """Surfaced on / so a misconfigured deploy is visible instead of silent."""
    if not jwt:
        return {"verified": False,
                "detail": "PyJWT not installed — users cannot be told apart"}
    if not (_JWT_SECRET or _SUPABASE_URL):
        # Names only, never values — enough to catch a typo'd or unsaved key
        # without ever exposing the secret itself.
        seen = sorted(k for k in os.environ if "SUPA" in k.upper())
        return {"verified": False,
                "detail": "Neither SUPABASE_JWT_SECRET nor SUPABASE_URL is set — "
                          "users are separated by unverified token claims, which "
                          "is a stopgap, not a security boundary.",
                "supabase_env_keys_present": seen,
                "hint": ("No SUPABASE* variable reached the process. Check the key "
                         "spelling in Render and that the change was saved and "
                         "redeployed.") if not seen else
                        f"Found {seen} — check spelling against SUPABASE_JWT_SECRET "
                        "and SUPABASE_URL."}
    modes = []
    if _JWT_SECRET:
        modes.append("HS256 (legacy secret)")
    if _SUPABASE_URL:
        modes.append("ES256/RS256 (JWKS)" if _jwks_client() else "JWKS unreachable")
    return {"verified": True, "modes": modes,
            "detail": "Tokens failing verification are namespaced 'unverified:' "
                      "and can never address a verified user's data."}
