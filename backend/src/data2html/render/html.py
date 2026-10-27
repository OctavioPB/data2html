"""Viewer HTML (html-renderer skill). The page carries NO data: layout, visuals, allowed marks and
chrome strings only; each visual fetches its aggregated rows with the reader's session.

Embedded JSON escapes `<`, `>` and `&` (`\u003c`…) so no value can close the `<script>` element;
Jinja2 autoescapes everything else.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from data2html.settings import ECHARTS_SRI

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# `<`, `>`, `&` and the JS line separators U+2028/U+2029 become JSON escapes (backslash + uXXXX)
_ESCAPES = {c: chr(92) + f"u{c:04x}" for c in (0x3C, 0x3E, 0x26, 0x2028, 0x2029)}


def safe_json(data: object) -> Markup:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return Markup(text.translate(_ESCAPES))  # noqa: S704 - escaped; inside <script type="application/json">


def render(template: str, **context: object) -> str:
    from data2html import __version__

    return _env.get_template(template).render(version=__version__, **context)


def csp(echarts_url: str) -> str:
    parts = urlsplit(echarts_url)
    script_origin = f"{parts.scheme}://{parts.netloc}" if parts.netloc else ""
    return "; ".join([
        "default-src 'none'",
        f"script-src 'self' {script_origin}".strip(),
        "style-src 'self'",
        "font-src 'self'",  # brand fonts, self-hosted (ADR 0013)
        "img-src 'self' data:",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # same-origin, not no-referrer: with no-referrer browsers send `Origin: null` on POST and the CSRF
    # check (auth.check_origin) would refuse our own forms. Other sites still get no referrer.
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}

ECHARTS_INTEGRITY = ECHARTS_SRI
