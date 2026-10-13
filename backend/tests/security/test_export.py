"""Visual → CSV (Phase 8): the download holds exactly what the reader sees (RLS, parameters,
cross-filters), is never cached by proxies, and cannot smuggle spreadsheet formulas."""

import csv
import io

from fastapi.testclient import TestClient

from data2html.api.main import app
from data2html.render.export import BOM, safe_cell, to_csv


def reader(user_id: str) -> TestClient:
    c = TestClient(app)
    c.post("/dev/login", data={"user_id": user_id, "next": "/r/regional"}, follow_redirects=False)
    return c


def parse(body: bytes) -> list[list[str]]:
    text = body.decode("utf-8")
    assert text.startswith(BOM)
    return list(csv.reader(io.StringIO(text[1:])))


def test_formula_injection_is_neutralized():
    for evil in ["=HYPERLINK(\"http://x\")", "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1"]:
        assert safe_cell(evil) == "'" + evil
    assert safe_cell(-5) == -5 and safe_cell("Norte") == "Norte" and safe_cell(None) == ""
    rows = parse(to_csv(["región", "=x"], [["Bajío", 1.5], ["=cmd|' /C calc'!A0", None]]))
    assert rows == [["región", "'=x"], ["Bajío", "1.5"], ["'=cmd|' /C calc'!A0", ""]]


def test_viewer_csv_is_the_readers_data(viewer_app):
    norte, sur = reader("norte"), reader("sur")
    r = norte.get("/api/r/regional/visuals/por_region.csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="regional-por_region.csv"'
    assert r.headers["cache-control"] == "private, no-store"
    assert parse(r.content) == [["region", "venta"], ["Norte", "33333"]]
    assert parse(sur.get("/api/r/regional/visuals/por_region.csv").content)[1:] == [["Sur", "77777"]]
    # parameters and cross-filters apply to the download too
    r = norte.get("/api/r/regional/visuals/total.csv", params={"p.desde": "2026-02-01", "cf": "canal:Tienda"})
    assert parse(r.content)[1:] == [["22222"]]


def test_viewer_csv_requires_session_and_access(viewer_app, publish, report_dict):
    assert TestClient(app).get("/api/r/regional/visuals/total.csv").status_code == 401
    publish(report_dict | {"id": "solo_sur", "access": ["Sur"]})
    assert reader("norte").get("/api/r/solo_sur/visuals/total.csv").status_code == 403
    assert reader("norte").get("/api/r/regional/visuals/total.csv", params={"user": "sur"}).status_code == 422


def test_studio_csv_is_the_author_preview(viewer_app):
    body = {"model": "ventas", "visual": {"mark": "bar", "measure": "venta", "dimension": "region"}}
    r = viewer_app.post("/api/visual/export.csv", json=body)  # the author bypass from conftest
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == 'attachment; filename="ventas-venta-region.csv"'
    assert sorted(parse(r.content)[1:]) == [["Norte", "33333"], ["Sur", "77777"]]
