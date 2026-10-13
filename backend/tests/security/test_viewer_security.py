"""Mandatory viewer security tests (security-rls skill): two identities, same report, same parameters →
different results, each with only its own rows. Plus: identity only from the session, access by group,
cache keyed by identity, no data in the HTML, escaped embedded JSON, cross-filters cannot widen RLS."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.auth import session
from data2html.settings import Settings


def reader(user_id: str | None) -> TestClient:
    c = TestClient(app)
    if user_id is not None:
        r = c.post("/dev/login", data={"user_id": user_id, "next": "/r/regional"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/r/regional"
    return c


def rows(client: TestClient, visual: str = "por_region", **query) -> list:
    r = client.get(f"/api/r/regional/visuals/{visual}", params=query)
    assert r.status_code == 200, r.text
    return r.json()["rows"]


# ------------------------------------------------------------------ RLS per identity


def test_two_identities_same_report_different_rows(viewer_app):
    norte, sur = reader("norte"), reader("sur")
    assert rows(norte) == [["Norte", 33333]]
    assert rows(sur) == [["Sur", 77777]]
    # repeated (now served from the cache): still each one's own rows
    assert rows(norte) == [["Norte", 33333]]
    assert rows(sur) == [["Sur", 77777]]
    assert rows(norte, visual="total") == [[33333]]
    assert rows(reader("ambas")) == [["Sur", 77777], ["Norte", 33333]]


def test_data_responses_are_never_cached_by_proxies(viewer_app):
    r = reader("norte").get("/api/r/regional/visuals/total")
    assert r.headers["cache-control"] == "private, no-store" and "Cookie" in r.headers["vary"]


def test_identity_without_groups_sees_nothing(viewer_app):
    assert rows(reader("nadie"), visual="total") == [[None]]


def test_parameters_apply_inside_rls(viewer_app):
    norte = reader("norte")
    assert rows(norte, **{"p.desde": "2026-02-01"}) == [["Norte", 22222]]
    r = norte.get("/api/r/regional/visuals/por_region", params={"p.desde": "febrero"})
    assert r.status_code == 422 and "date" in r.json()["detail"]


# ------------------------------------------------------------------ identity only from the session


def test_without_session(viewer_app):
    anon = reader(None)
    assert anon.get("/api/r/regional/visuals/por_region").status_code == 401
    r = anon.get("/r/regional", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/r/regional"


@pytest.mark.parametrize("query", [{"user_id": "sur"}, {"groups": "Sur"}, {"identity": "sur"}])
def test_identity_cannot_come_from_query(viewer_app, query):
    r = reader("norte").get("/api/r/regional/visuals/por_region", params=query)
    assert r.status_code == 422


def test_identity_cannot_come_from_headers(viewer_app):
    norte = reader("norte")
    r = norte.get("/api/r/regional/visuals/por_region",
                  headers={"X-User": "sur", "X-Groups": "Sur", "X-Forwarded-User": "sur",
                           "Remote-User": "sur"})
    assert r.json()["rows"] == [["Norte", 33333]]
    anon = reader(None)
    assert anon.get("/api/r/regional/visuals/por_region", headers={"X-User": "sur"}).status_code == 401


def test_tampered_or_forged_cookie(viewer_app):
    c = TestClient(app)
    good = session.sign("norte")
    payload, sig = good.split(".")
    forged_payload = session._b64(json.dumps({"u": "sur", "exp": 9999999999}).encode())
    for value in [f"{forged_payload}.{sig}", f"{payload}.{sig[:-2]}xx", "sur", "", "a.b.c"]:
        c.cookies.set(session.COOKIE, value)
        assert c.get("/api/r/regional/visuals/por_region").status_code == 401


def test_session_unit():
    t = session.sign("norte", now=1000)
    assert session.verify(t, now=1001) == "norte"
    assert session.verify(t, now=1000 + session.MAX_AGE_S + 1) is None  # expired
    assert session.verify(None) is None and session.verify("x" * 2000) is None


def test_dev_identities_disabled(viewer_settings):
    off = Settings(**(viewer_settings.__dict__ | {"dev_identities_file": None}))
    app.dependency_overrides[get_settings] = lambda: off
    try:
        c = TestClient(app)
        assert c.post("/dev/login", data={"user_id": "norte"}).status_code == 404
        assert "/dev/login" not in c.get("/login").text  # no development identities offered
        c.cookies.set(session.COOKIE, session.sign("norte"))  # a validly signed cookie does not help
        assert c.get("/api/r/regional/visuals/por_region").status_code == 401
        assert c.get("/r/regional", follow_redirects=False).headers["location"] == "/login?next=/r/regional"
    finally:
        app.dependency_overrides.clear()


def test_dev_identities_only_from_allowed_hosts(viewer_settings):
    # TestClient connects as "testclient": outside the allowed hosts
    remote = Settings(**(viewer_settings.__dict__ | {"dev_hosts": ("127.0.0.1",)}))
    app.dependency_overrides[get_settings] = lambda: remote
    try:
        c = TestClient(app)
        assert c.post("/dev/login", data={"user_id": "norte"}).status_code == 404
        c.cookies.set(session.COOKIE, session.sign("norte"))
        assert c.get("/api/r/regional/visuals/por_region").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_login_rejects_unknown_identity_and_open_redirects(viewer_app):
    c = TestClient(app)
    assert c.post("/dev/login", data={"user_id": "root"}).status_code == 400
    for evil in ["https://evil.example", "//evil.example", "/r/../api", "/\\evil"]:
        r = c.post("/dev/login", data={"user_id": "norte", "next": evil}, follow_redirects=False)
        assert r.headers["location"] == "/"


# ------------------------------------------------------------------ access by group


def test_access_groups(viewer_app, publish, report_dict):
    publish(report_dict | {"id": "solo_sur", "access": ["Sur"]})
    norte, sur = reader("norte"), reader("sur")
    assert norte.get("/api/r/solo_sur/visuals/total").status_code == 403
    assert norte.get("/r/solo_sur").status_code == 403
    assert sur.get("/api/r/solo_sur/visuals/total").json()["rows"] == [[77777]]
    index = norte.get("/r").text
    assert "/r/regional" in index and "/r/solo_sur" not in index
    assert "/r/solo_sur" in sur.get("/r").text


# ------------------------------------------------------------------ cross-filters


def test_cross_filter_cannot_widen_rls(viewer_app):
    norte = reader("norte")
    assert rows(norte, visual="total", cf="region:Sur") == [[None]]  # AND with RLS: nothing
    assert rows(norte, visual="total", cf="canal:Web") == [[11111]]


@pytest.mark.parametrize("cf", ["fecha:2026-01-05", "monto:1", "region", "nope:x", "region:" + "x" * 600])
def test_cross_filter_rejections(viewer_app, cf):
    r = reader("norte").get("/api/r/regional/visuals/total", params={"cf": cf})
    assert r.status_code == 422


def test_unknown_parameter_and_visual(viewer_app):
    norte = reader("norte")
    assert norte.get("/api/r/regional/visuals/total", params={"p.otro": "1"}).status_code == 422
    assert norte.get("/api/r/regional/visuals/nope").status_code == 404
    assert norte.get("/api/r/nope/visuals/total").status_code == 404


# ------------------------------------------------------------------ the HTML


def test_page_has_no_data_and_strict_headers(viewer_app):
    r = reader("norte").get("/r/regional")
    assert r.status_code == 200
    html = r.text
    for value in ["11111", "22222", "33333", "44444", "77777", "SUM(monto)", "region_desc"]:
        assert value not in html
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self' https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert 'integrity="sha384-' in html


def test_embedded_json_is_escaped(viewer_app, publish, report_dict):
    evil = "</script><script>alert(1)</script> & <b>"
    publish(report_dict | {"title": evil})
    html = reader("norte").get("/r/regional").text
    assert "<script>alert(1)" not in html
    assert "<b>" not in html
    blob = re.search(r'<script type="application/json" id="d2h-view">(.*?)</script>', html, re.S)
    assert blob is not None and json.loads(blob.group(1))["title"] == evil


# ------------------------------------------------------------------ snapshot reports (per reader)


def test_snapshot_is_per_reader_and_frozen(viewer_app, viewer_settings, publish, report_dict):
    import os

    import duckdb

    publish(report_dict | {"id": "foto", "mode": "snapshot"})
    norte, sur = reader("norte"), reader("sur")
    first = norte.get("/api/r/foto/visuals/total").json()
    assert first["rows"] == [[33333]] and first["as_of"]
    assert sur.get("/api/r/foto/visuals/total").json()["rows"] == [[77777]]  # never another reader's
    # the source changes (every amount doubles): the snapshot does not
    parquet = viewer_settings.csv_dir / "ventas.parquet"
    duckdb.sql(f"COPY (SELECT * REPLACE (monto * 2 AS monto) FROM read_parquet('{parquet}')) "  # noqa: S608 - test setup
               f"TO '{parquet}.new' (FORMAT parquet)")
    os.replace(f"{parquet}.new", parquet)
    again = norte.get("/api/r/foto/visuals/total").json()
    assert again["rows"] == [[33333]] and again["as_of"] == first["as_of"]
    # republishing (new content) takes a new snapshot
    publish(report_dict | {"id": "foto", "mode": "snapshot", "title": "Foto v2"})
    assert norte.get("/api/r/foto/visuals/total").json()["rows"] == [[66666]]
    # a live report always reads the source and has no as_of
    live = norte.get("/api/r/regional/visuals/total").json()
    assert live["rows"] == [[66666]] and live["as_of"] is None


def test_snapshot_refresh_hours_is_snapshot_only(report_dict):
    import pytest as _pytest
    from pydantic import ValidationError

    from data2html.spec import Report

    Report.model_validate(report_dict | {"mode": "snapshot", "refresh_hours": 24})
    with _pytest.raises(ValidationError, match="refresh_hours"):
        Report.model_validate(report_dict | {"refresh_hours": 24})
