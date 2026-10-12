"""Server-side localization: catalog completeness and request-language handling."""

import ast
import string
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.i18n import parse_accept_language, set_lang, tr
from data2html.locales.es import ES
from data2html.settings import Settings

SRC = Path(__file__).resolve().parents[1] / "src/data2html"
MESSAGE_CALLS = {"tr", "_Failure"}  # functions whose first argument is an English msgid


def _msgids() -> dict[str, str]:
    """Every literal msgid in the source tree → where it is used."""
    found: dict[str, str] = {}
    for path in SRC.rglob("*.py"):
        if "locales" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            is_msg_call = (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                           and node.func.id in MESSAGE_CALLS and node.args)
            if is_msg_call and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                found[node.args[0].value] = f"{path.relative_to(SRC)}:{node.lineno}"
    return found


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_message_has_a_spanish_translation():
    missing = {m: where for m, where in _msgids().items() if m not in ES}
    assert not missing, f"add these to locales/es.py: {missing}"


def test_no_unused_spanish_entries():
    unused = set(ES) - set(_msgids())
    assert not unused, f"remove from locales/es.py (no longer used): {sorted(unused)}"


@pytest.mark.parametrize("msgid", sorted(ES))
def test_placeholders_match(msgid):
    assert _fields(msgid) == _fields(ES[msgid])


@pytest.mark.parametrize(("header", "lang"), [
    (None, "en"), ("", "en"), ("es", "es"), ("es-MX,es;q=0.9,en;q=0.8", "es"),
    ("en-US,en;q=0.9,es;q=0.8", "en"), ("fr-FR,fr;q=0.9", "en"), ("fr,es;q=0.5", "es"),
    ("en;q=0.2,es;q=0.9", "es"), ("ES", "es"),
])
def test_parse_accept_language(header, lang):
    assert parse_accept_language(header) == lang


def test_tr_formats_in_both_languages():
    set_lang("en")
    assert tr("the file exceeds {mb} MB", mb=5) == "the file exceeds 5 MB"
    set_lang("es")
    try:
        assert tr("the file exceeds {mb} MB", mb=5) == "el archivo supera 5 MB"
        assert tr("{ratio:.0%} null values", ratio=0.25) == "25% de nulos"
    finally:
        set_lang("en")


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=tmp_path, sources_file=None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_errors_follow_accept_language(client):
    en = client.post("/api/explore/csv/nope", json={})
    es = client.post("/api/explore/csv/nope", json={}, headers={"Accept-Language": "es-MX,es;q=0.9"})
    assert en.status_code == es.status_code == 404
    assert en.json()["detail"] == "unknown table: 'nope'"
    assert es.json()["detail"] == "tabla desconocida: 'nope'"
    assert en.headers["content-language"] == "en" and es.headers["content-language"] == "es"


def test_contract_validation_is_localized(client):
    bad = {"model": "x", "visual": {"mark": "bar", "measure": "m",
                                    "filters": [{"dimension": "d", "op": "eq"}]}}
    es = client.post("/api/visual/query", json=bad, headers={"Accept-Language": "es"})
    assert es.status_code == 422
    assert "exactamente uno" in str(es.json()["detail"])


def test_language_does_not_leak_between_requests(client):
    client.post("/api/explore/csv/nope", json={}, headers={"Accept-Language": "es"})
    assert client.post("/api/explore/csv/nope", json={}).json()["detail"] == "unknown table: 'nope'"
