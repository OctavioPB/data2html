"""Identity. The ONLY place it comes from (security-rls skill, invariant 1; ADR 0010).

A sign-in (local password, OIDC, or a development identity) creates a server-side session; the cookie
carries its signed random id. On every request:
- `local` and `dev` identities are re-read from their files (removing a user revokes access at once;
  development identities also require `D2H_DEV_IDENTITIES=1` and a localhost client);
- `oidc` identities are the snapshot taken from the validated `id_token` at sign-in.

Nothing in headers, query parameters or bodies can set or change the identity. The one exception is
the read-only agent API (`/api/agent/*`, ADR 0014): it takes a personal access token as
`Authorization: Bearer` (and nothing else), which stands for the identity it was created for.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from data2html.api.deps import SettingsDep
from data2html.auth.config import load_auth_config
from data2html.auth.dev import load_dev_identities
from data2html.auth.local import load_users, to_identity
from data2html.auth.session import COOKIE, verify
from data2html.auth.sessions import get_store
from data2html.auth.tokens import get_tokens
from data2html.i18n import tr
from data2html.settings import Settings
from data2html.sources.base import Identity

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def dev_login_allowed(request: Request, settings: Settings) -> bool:
    host = request.client.host if request.client else None
    return settings.dev_identities_file is not None and host in settings.dev_hosts


def session_id(request: Request) -> str | None:
    return verify(request.cookies.get(COOKIE))


def resolve_identity(request: Request, settings: Settings) -> Identity | None:
    """The session cookie's identity. `Authorization` is ignored here: tokens only open /api/agent."""
    sid = session_id(request)
    if sid is None:
        return None
    stored = get_store(settings.sessions_path).get(sid)
    return _live(stored, request, settings) if stored is not None else None


def resolve_token_identity(request: Request, settings: Settings) -> Identity | None:
    """`Authorization: Bearer d2h_…` (personal access token, ADR 0014). Only the agent API calls this."""
    scheme, _, secret = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secret:
        return None
    stored = get_tokens(settings.sessions_path).get(secret.strip())
    return _live(stored, request, settings) if stored is not None else None


def _live(stored: Identity, request: Request, settings: Settings) -> Identity | None:
    """The identity a session or token stands for, re-checked against its provider right now."""
    if stored.provider == "dev":
        if not dev_login_allowed(request, settings):
            return None
        assert settings.dev_identities_file is not None  # checked by dev_login_allowed
        return load_dev_identities(settings.dev_identities_file).get(stored.user_id)
    if stored.provider == "local":
        if not load_auth_config(settings.auth_file).local:
            return None
        user = load_users(settings.users_file).get(stored.user_id)
        return to_identity(stored.user_id, user) if user else None
    if stored.provider == "oidc":
        return stored if load_auth_config(settings.auth_file).oidc is not None else None
    return None


def current_identity(request: Request, settings: SettingsDep) -> Identity | None:
    return resolve_identity(request, settings)


def require_identity(identity: Annotated[Identity | None, Depends(current_identity)]) -> Identity:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=tr("sign in to see this report"))
    return identity


def require_token(request: Request, settings: SettingsDep) -> Identity:
    identity = resolve_token_identity(request, settings)
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=tr("a valid access token is required"),
                            headers={"WWW-Authenticate": "Bearer"})
    return identity


def require_author(identity: Annotated[Identity | None, Depends(current_identity)]) -> Identity:
    """The studio is single-author (ADR 0005): every studio route requires the author role."""
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=tr("sign in to use the studio"))
    if not identity.author:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=tr("your account cannot use the studio"))
    return identity


def check_origin(request: Request, settings: SettingsDep) -> None:
    """CSRF defence for cookie-authenticated requests (with `SameSite=Strict`): a browser request that
    changes state must come from this same origin. Requests without `Origin` are not from a browser
    form/script of another site (browsers always send it on cross-origin POST/PUT/PATCH/DELETE)."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    host = request.headers.get("host", "")
    allowed = {f"{request.url.scheme}://{host}", *load_auth_config(settings.auth_file).trusted_origins}
    if settings.public_url:
        allowed.add(settings.public_url.rstrip("/"))
    if origin.rstrip("/") not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=tr("cross-site request refused"))


IdentityDep = Annotated[Identity, Depends(require_identity)]
MaybeIdentityDep = Annotated[Identity | None, Depends(current_identity)]
AuthorDep = Annotated[Identity, Depends(require_author)]
TokenIdentityDep = Annotated[Identity, Depends(require_token)]
