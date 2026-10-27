"""Sign-in and sign-out (ADR 0010): local password, OIDC (Microsoft Entra ID) and, in development only,
pick-an-identity. Every path ends in `start_session`, which stores the identity server-side."""

from __future__ import annotations

import logging
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict

from data2html.api.deps import SettingsDep
from data2html.auth import MaybeIdentityDep, dev_login_allowed, session_id
from data2html.auth.config import load_auth_config
from data2html.auth.dev import load_dev_identities
from data2html.auth.local import authenticate
from data2html.auth.oidc import OidcError, get_client, pkce_pair
from data2html.auth.session import COOKIE, sign
from data2html.auth.sessions import get_store
from data2html.i18n import get_lang, tr
from data2html.render.html import SECURITY_HEADERS, csp, render
from data2html.settings import Settings
from data2html.sources.base import Identity

log = logging.getLogger(__name__)

pages = APIRouter(tags=["auth"], include_in_schema=False)
api = APIRouter(prefix="/api", tags=["auth"])

# Failed local sign-ins allowed per user and per client address, shared by every worker (SQLite)
THROTTLE_LIMIT = 5
THROTTLE_WINDOW_S = 15 * 60

# Where a sign-in may return to: the studio's root or the viewer (never another site)
_NEXT = re.compile(r"^/(r(/[a-z][a-z0-9_]{0,62})?)?$")


def safe_next(next_url: str | None) -> str:
    return next_url if next_url and _NEXT.match(next_url) else "/"


def _html(body: str, settings: Settings, code: int = 200) -> HTMLResponse:
    headers = {**SECURITY_HEADERS, "Content-Security-Policy": csp(settings.echarts_url)}
    return HTMLResponse(body, status_code=code, headers=headers)


def _base_url(request: Request, settings: Settings) -> str:
    return (settings.public_url or str(request.base_url)).rstrip("/")


def _secure(request: Request, settings: Settings) -> bool:
    return request.url.scheme == "https" or (settings.public_url or "").startswith("https://")


def start_session(
    identity: Identity, request: Request, settings: Settings, response: Response
) -> Response:
    hours = load_auth_config(settings.auth_file).session_hours
    sid = get_store(settings.sessions_path).create(identity, hours * 3600)
    response.set_cookie(COOKIE, sign(sid, max_age_s=hours * 3600), max_age=hours * 3600, httponly=True,
                        samesite="strict", secure=_secure(request, settings), path="/")
    return response


def _login_page(request: Request, settings: Settings, next_url: str, *, error: str | None = None,
                code: int = 200) -> HTMLResponse:
    cfg = load_auth_config(settings.auth_file)
    dev = []
    if dev_login_allowed(request, settings):
        assert settings.dev_identities_file is not None
        dev = list(load_dev_identities(settings.dev_identities_file).values())
    body = render(
        "login.html", lang=get_lang(), title=tr("Sign in"), subtitle=tr("to your reports"), next=next_url,
        error=error,
        local=cfg.local, oidc_label=cfg.oidc.label if cfg.oidc else None, dev=dev,
        user_label=tr("User"), password_label=tr("Password"), submit=tr("Sign in"),
        oidc_button=tr("Sign in with {provider}", provider=cfg.oidc.label) if cfg.oidc else "",
        dev_title=tr("Development identities"),
        dev_hint=tr("Development only (localhost): pick who you are, no password."),
        no_groups=tr("no groups"), author_label=tr("author"),
        nothing=tr("No sign-in method is configured."),
    )
    return _html(body, settings, code)


@pages.get("/login")
def login_page(request: Request, settings: SettingsDep, next: str | None = None) -> Response:
    return _login_page(request, settings, safe_next(next))


@pages.post("/login")
def login_local(
    request: Request, settings: SettingsDep, user_id: Annotated[str, Form(max_length=64)],
    password: Annotated[str, Form(max_length=1024)], next: Annotated[str, Form(max_length=200)] = "/",
) -> Response:
    target = safe_next(next)
    if not load_auth_config(settings.auth_file).local:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    client = request.client.host if request.client else "?"
    keys = (f"user:{user_id.lower()}", f"ip:{client}")
    store = get_store(settings.sessions_path)
    if store.failures(keys, THROTTLE_WINDOW_S) >= THROTTLE_LIMIT:
        return _login_page(request, settings, target, code=429,
                           error=tr("Too many failed attempts. Try again in a few minutes."))
    identity = authenticate(settings.users_file, user_id.lower(), password)
    if identity is None:
        store.record_failure(keys, THROTTLE_WINDOW_S)
        log.info("failed local sign-in for %r from %s", user_id[:64], client)
        return _login_page(request, settings, target, code=401, error=tr("Wrong user or password."))
    store.clear_failures(keys)
    return start_session(identity, request, settings, RedirectResponse(target, status.HTTP_303_SEE_OTHER))


@pages.get("/login/oidc")
def login_oidc(request: Request, settings: SettingsDep, next: str | None = None) -> Response:
    cfg = load_auth_config(settings.auth_file).oidc
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    verifier, challenge = pkce_pair()
    nonce = secrets.token_urlsafe(24)
    state = get_store(settings.sessions_path).put_pending(
        {"nonce": nonce, "verifier": verifier, "next": safe_next(next)})
    try:
        url = get_client(cfg).authorize_url(f"{_base_url(request, settings)}/auth/callback", state, nonce,
                                            challenge)
    except (OidcError, OSError, ValueError) as e:
        log.warning("OIDC discovery failed: %s", e)
        return _login_page(request, settings, safe_next(next), code=502,
                           error=tr("The sign-in provider is not available. Try again later."))
    return RedirectResponse(url, status.HTTP_302_FOUND)


@pages.get("/auth/callback")
def oidc_callback(
    request: Request, settings: SettingsDep, state: str = "", code: str = "", error: str = "",
) -> Response:
    cfg = load_auth_config(settings.auth_file).oidc
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    pending = get_store(settings.sessions_path).pop_pending(state) if state else None
    failed = tr("Sign-in failed. Try again or contact the administrator.")
    if pending is None:
        return _login_page(request, settings, "/", code=400, error=failed)
    if error or not code:
        log.info("OIDC provider returned error %r", error[:100])
        return _login_page(request, settings, pending["next"], code=401, error=failed)
    client = get_client(cfg)
    try:
        token = client.exchange(code, pending["verifier"], f"{_base_url(request, settings)}/auth/callback")
        identity = client.identity(client.validate(token, pending["nonce"]))
    except (OidcError, OSError, ValueError) as e:
        log.warning("OIDC sign-in rejected: %s", e)
        return _login_page(request, settings, pending["next"], code=401, error=failed)
    # The provider's redirect is a cross-site navigation: a SameSite=Strict cookie would not be sent on a
    # redirect chained to it, so the browser continues from a page of ours instead.
    body = render("continue.html", lang=get_lang(), title=tr("Signed in"), next=pending["next"],
                  label=tr("Continue"))
    return start_session(identity, request, settings, _html(body, settings))


@pages.get("/dev/login")
def dev_login_page(next: str | None = None) -> Response:
    return RedirectResponse(f"/login?next={safe_next(next)}", status.HTTP_303_SEE_OTHER)


@pages.post("/dev/login")
def dev_login(
    request: Request, settings: SettingsDep, user_id: Annotated[str, Form(max_length=64)],
    next: Annotated[str, Form(max_length=200)] = "/",
) -> Response:
    if not dev_login_allowed(request, settings):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    assert settings.dev_identities_file is not None
    identity = load_dev_identities(settings.dev_identities_file).get(user_id)
    if identity is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=tr("unknown identity"))
    target = RedirectResponse(safe_next(next), status.HTTP_303_SEE_OTHER)
    return start_session(identity, request, settings, target)


@pages.post("/logout")
def logout(request: Request, settings: SettingsDep) -> Response:
    sid = session_id(request)
    if sid is not None:
        get_store(settings.sessions_path).delete(sid)  # revoked server-side, not just forgotten
    resp = RedirectResponse("/login", status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(COOKIE, path="/")
    return resp


class Me(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    email: str
    provider: str
    groups: list[str]
    author: bool


@api.get("/me")
def me(identity: MaybeIdentityDep) -> Me:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=tr("sign in to use the studio"))
    return Me(user_id=identity.user_id, email=identity.email, provider=identity.provider,
              groups=list(identity.groups), author=identity.author)
