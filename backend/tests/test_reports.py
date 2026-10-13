import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.render.cache import TTLCache, cache_key
from data2html.render.theme import Theme, load_theme
from data2html.reports.store import ReportNotFound, ReportStore
from data2html.sources.base import Identity
from data2html.spec import Report, SemanticModel


@pytest.fixture
def client(viewer_settings):
    """The studio, with the CSV table and the model; no report published yet."""
    (viewer_settings.reports_dir / "regional.yaml").unlink()
    app.dependency_overrides[get_settings] = lambda: viewer_settings
    yield TestClient(app), viewer_settings
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ store


def test_store_roundtrip(tmp_path, report_dict):
    store = ReportStore(tmp_path / "reports")
    r = Report.model_validate(report_dict)
    store.put(r)
    assert store.get("regional") == r
    text = (tmp_path / "reports/regional.yaml").read_text(encoding="utf-8")
    assert text.startswith("# Report (data2html)") and "Por región" in text
    store.delete("regional")
    with pytest.raises(ReportNotFound):
        store.get("regional")


# ------------------------------------------------------------------ studio API (saving = publishing)


def test_api_report_lifecycle(client, report_dict):
    c, s = client
    r = c.put("/api/reports/regional", json=report_dict)
    assert r.status_code == 200, r.text
    assert (s.reports_dir / "regional.yaml").exists()
    listing = c.get("/api/reports").json()
    assert [e["report"]["id"] for e in listing["reports"]] == ["regional"]
    assert listing["reports"][0]["errors"] == []
    assert c.get("/api/reports/regional").json()["report"]["title"] == "Regional"
    assert c.put("/api/reports/otro", json=report_dict).status_code == 422  # id does not match
    assert c.delete("/api/reports/regional").status_code == 204
    assert c.get("/api/reports/regional").status_code == 404


@pytest.mark.parametrize("change", [
    {"semantic_model": "nope"},
    {"visual": {"measure": "margen"}},
    {"visual": {"mark": "line"}},                                 # region is nominal
    {"params": {"desde": "int"}},                                 # cannot filter a date
])
def test_invalid_report_is_never_written(client, report_dict, change):
    c, s = client
    if "visual" in change:
        report_dict["visuals"][0] |= change.pop("visual")
    r = c.put("/api/reports/regional", json=report_dict | change)
    assert r.status_code == 422
    assert not (s.reports_dir / "regional.yaml").exists()


def test_author_preview_with_declared_param_types(client):
    c, _ = client
    body = {
        "model": "ventas",
        "visual": {"mark": "bar", "measure": "venta", "dimension": "region",
                   "filters": [{"dimension": "fecha", "op": "gte", "param": "desde"}]},
        "params": {"desde": "2026-02-01"},
        "param_types": {"desde": "date"},
    }
    r = c.post("/api/visual/query", json=body)
    assert r.status_code == 200, r.text
    # the author sees every region (single-user studio, ADR 0008); readers get RLS in the viewer
    assert sorted(map(tuple, r.json()["rows"])) == [("Norte", 22222), ("Sur", 77777)]
    # without param_types an ISO date is inferred as a date
    r = c.post("/api/visual/query", json=body | {"param_types": {}})
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ cache and theme


def test_cache_key_includes_the_whole_identity(report_dict, viewer_settings):
    r = Report.model_validate(report_dict)
    model_file = viewer_settings.semantic_dir / "ventas.yaml"
    m = SemanticModel.model_validate(yaml.safe_load(model_file.read_text(encoding="utf-8")))
    a = Identity(user_id="u", email="u@x", provider="dev", groups=("Norte",))
    b = Identity(user_id="u", email="u@x", provider="dev", groups=("Sur",))
    key = lambda i, **kw: cache_key(report=r, model=m, visual_id="total", identity=i,  # noqa: E731
                                    params=kw.get("params", {}), cross=kw.get("cross", []))
    assert key(a) != key(b)
    assert key(a) != key(a, params={"desde": "2026-01-01"})
    assert key(a) != key(a, cross=[("canal", "Web")])
    assert key(a) == key(a)


def test_ttl_cache_expiry_and_lru():
    c: TTLCache[int] = TTLCache(ttl_s=1, max_entries=2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    c.put("c", 3)  # evicts the least recently used: b
    assert c.get("b") is None and c.get("a") == 1
    c._items["a"] = (time.monotonic() - 1, 1)  # expired
    assert c.get("a") is None
    off: TTLCache[int] = TTLCache(ttl_s=0, max_entries=2)
    off.put("a", 1)
    assert off.get("a") is None


def test_theme_file_and_defaults(tmp_path):
    assert load_theme(None) == Theme()
    f = tmp_path / "theme.yaml"
    f.write_text("currency: USD\npalette: {light: ['#000000'], dark: ['#ffffff']}\n", encoding="utf-8")
    t = load_theme(f)
    assert t.currency == "USD" and t.palette.light == ("#000000",)
    with pytest.raises(ValueError):
        Theme.model_validate({"font": "x; } body { display: none"})


def test_repo_theme_is_valid():
    load_theme(Path(__file__).resolve().parents[2] / "config/theme.yaml")
