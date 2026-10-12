"""Server-side message localization (English / Spanish).

User-facing messages are written in English inside `tr("...")`; `locales/es.py` maps each message
to Spanish. The language of the current request comes from `Accept-Language` (the studio sends the
user's choice) and lives in a ContextVar, so code deep in the stack (sources, sqlgen, the contract
validators) localizes without passing the language around.

`tests/test_i18n.py` scans the source tree: every `tr("...")` literal must have a Spanish entry with
the same `{placeholders}`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar
from typing import Any, Literal

Lang = Literal["en", "es"]
SUPPORTED: tuple[Lang, ...] = ("en", "es")
DEFAULT: Lang = "en"

_current: ContextVar[Lang] = ContextVar("d2h_lang", default=DEFAULT)


def get_lang() -> Lang:
    return _current.get()


def set_lang(lang: Lang) -> None:
    _current.set(lang)


def parse_accept_language(header: str | None) -> Lang:
    """First supported language in an `Accept-Language` header (`es-MX,es;q=0.9,en;q=0.8`)."""
    if not header:
        return DEFAULT
    ranked: list[tuple[float, int, str]] = []
    for i, part in enumerate(header.split(",")):
        tag, _sep, params = part.strip().partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        ranked.append((-q, i, tag.strip().lower().split("-")[0]))
    for _q, _i, base in sorted(ranked):
        if base in SUPPORTED:
            return base
    return DEFAULT


def tr(msgid: str, /, **params: object) -> str:
    """Localized message for the current request. `msgid` is the English text."""
    text = msgid
    if _current.get() == "es":
        from data2html.locales.es import ES

        text = ES.get(msgid, msgid)
    return text.format(**params) if params else text


Scope = MutableMapping[str, Any]
ASGIApp = Callable[[Scope, Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]]


class LanguageMiddleware:
    """Pure ASGI middleware: sets the request language before routing and body validation, and
    echoes it in `Content-Language`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Callable[[], Awaitable[Any]], send: Callable[[Any], Awaitable[None]]
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        lang = parse_accept_language(headers.get("accept-language"))
        token = _current.set(lang)

        async def send_with_language(message: Any) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"content-language", lang.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_language)
        finally:
            _current.reset(token)
