"""`/tokens`: a signed-in person creates and revokes their personal access tokens (ADR 0014).

Session cookie + same-origin check (CSRF, app-wide), like every other form. The secret is shown once,
in the response to the POST that created it (never in a URL, never stored in clear).
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from data2html.api.deps import SettingsDep
from data2html.api.login import _base_url
from data2html.auth import MaybeIdentityDep
from data2html.auth.tokens import DEFAULT_DAYS, MAX_DAYS, MAX_PER_USER, NAME_MAX, TooManyTokens, get_tokens
from data2html.i18n import get_lang, tr
from data2html.render.html import SECURITY_HEADERS, csp, render
from data2html.settings import Settings
from data2html.sources.base import Identity

pages = APIRouter(tags=["tokens"], include_in_schema=False)


def _day(t: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _page(request: Request, identity: Identity, settings: Settings, *, secret: str | None = None,
          error: str | None = None, code: int = 200) -> HTMLResponse:
    items = [
        {"id": t.id, "name": t.name,
         "meta": tr("created {created} · expires {expires}", created=_day(t.created),
                    expires=_day(t.expires)),
         "used": tr("last used {date}", date=_day(t.last_used)) if t.last_used else tr("never used")}
        for t in get_tokens(settings.sessions_path).list(identity.provider, identity.user_id)
    ]
    body = render(
        "tokens.html", lang=get_lang(), title=tr("Access tokens"), subtitle=tr("for Claude Desktop"),
        intro=tr("A token lets the data2html MCP server ask for your data on your behalf, with your "
                 "permissions. Anyone holding it can read what you can read: keep it secret."),
        tokens=items, secret=secret, error=error, base_url=_base_url(request, settings),
        user=tr("Signed in as {user}", user=identity.user_id),
        once=tr("Copy this token now: it will not be shown again."),
        config_label=tr("Claude Desktop configuration"),
        name_label=tr("Name"), days_label=tr("Valid for (days)"), default_days=DEFAULT_DAYS,
        max_days=MAX_DAYS, name_max=NAME_MAX, create=tr("Create token"), active=tr("Active tokens"),
        none=tr("No active tokens."),
        revoke=tr("Revoke"), back=tr("Back to reports"),
    )
    headers = {**SECURITY_HEADERS, "Content-Security-Policy": csp(settings.echarts_url),
               "Cache-Control": "no-store"}
    return HTMLResponse(body, status_code=code, headers=headers)


def _signed_in(identity: Identity | None) -> Identity:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=tr("sign in to manage your tokens"))
    return identity


@pages.get("/tokens")
def tokens_page(request: Request, identity: MaybeIdentityDep, settings: SettingsDep) -> Response:
    if identity is None:
        return RedirectResponse("/login?next=/tokens", status.HTTP_303_SEE_OTHER)
    return _page(request, identity, settings)


@pages.post("/tokens")
def create_token(
    request: Request, identity: MaybeIdentityDep, settings: SettingsDep,
    name: Annotated[str, Form(max_length=NAME_MAX)] = "",
    days: Annotated[int, Form(ge=1, le=MAX_DAYS)] = DEFAULT_DAYS,
) -> Response:
    who = _signed_in(identity)
    try:
        _id, secret = get_tokens(settings.sessions_path).create(who, name, days)
    except TooManyTokens:
        error = tr("you already have the maximum of {max} tokens", max=MAX_PER_USER)
        return _page(request, who, settings, error=error, code=409)
    return _page(request, who, settings, secret=secret)


@pages.post("/tokens/{token_id}/revoke")
def revoke_token(token_id: str, identity: MaybeIdentityDep, settings: SettingsDep) -> Response:
    who = _signed_in(identity)
    store = get_tokens(settings.sessions_path)
    if not store.revoke(token_id[:16], provider=who.provider, user_id=who.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=tr("unknown token"))
    return RedirectResponse("/tokens", status.HTTP_303_SEE_OTHER)
