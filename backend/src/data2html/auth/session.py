"""Signed session cookie: `base64url(payload).base64url(HMAC-SHA256)`.

The cookie only carries the random id of a server-side session (`sessions.py`) and an expiry; the
identity lives on the server, so a cookie can never grant groups or roles. The key comes from the
environment (`D2H_SESSION_SECRET`, ≥ 32 characters; required in production); without it, a random
per-process key is used, which is fine for development (sessions end when the server restarts).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

COOKIE = "d2h_session"
MAX_AGE_S = 8 * 3600

_fallback_key = secrets.token_bytes(32)


def _key() -> bytes:
    env = os.environ.get("D2H_SESSION_SECRET", "")
    return env.encode() if len(env) >= 32 else _fallback_key


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig(payload: str) -> str:
    return _b64(hmac.new(_key(), payload.encode(), hashlib.sha256).digest())


def sign(subject: str, *, now: float | None = None, max_age_s: int = MAX_AGE_S) -> str:
    exp = int((now if now is not None else time.time()) + max_age_s)
    payload = _b64(json.dumps({"u": subject, "exp": exp}, separators=(",", ":")).encode())
    return f"{payload}.{_sig(payload)}"


def verify(token: str | None, *, now: float | None = None) -> str | None:
    """Subject (session id) of a valid, unexpired token; None otherwise (never raises)."""
    if not token or token.count(".") != 1 or len(token) > 1024:
        return None
    payload, sig = token.split(".")
    if not hmac.compare_digest(sig, _sig(payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
        user_id, exp = data["u"], data["exp"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(user_id, str) or not isinstance(exp, int):
        return None
    if exp < (now if now is not None else time.time()):
        return None
    return user_id
