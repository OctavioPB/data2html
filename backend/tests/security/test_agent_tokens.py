"""Personal access tokens and the read-only agent API (ADR 0014): the token is the only way in, it opens
nothing else, every result carries the token owner's RLS (the author's too), and `config/ai.yaml` caps
what each source shows."""

import logging
import re
import sqlite3
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.auth.local import main as local_main
from data2html.auth.tokens import get_tokens
from data2html.settings import Settings
from data2html.sources.base import Identity

IDENTITIES = {
    "identities": {
        "norte": {"email": "n@example.com", "groups": ["Norte"]},
        "sur": {"email": "s@example.com", "groups": ["Sur"]},
        "autor": {"email": "a@example.com", "author": True, "groups": ["Norte"]},
    }
}
SECRET = re.compile(r'<code class="secret">(d2h_[A-Za-z0-9_-]+)</code>')


def use(settings: Settings) -> Settings:
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


@pytest.fixture
def agent_settings(viewer_settings, tmp_path):
    viewer_settings.dev_identities_file.write_text(yaml.safe_dump(IDENTITIES), encoding="utf-8")
    ai = tmp_path / "ai.yaml"
    ai.write_text(yaml.safe_dump({"exposure": {"csv": "results"}}), encoding="utf-8")
    yield use(Settings(**(viewer_settings.__dict__ | {"ai_file": ai})))
    app.dependency_overrides.clear()


def session(user_id: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/dev/login", data={"user_id": user_id, "next": "/tokens"}, follow_redirects=False)
    assert r.status_code == 303
    return c


def new_token(user_id: str, **form) -> str:
    r = session(user_id).post("/tokens", data={"name": "Claude Desktop", "days": 30} | form)
    assert r.status_code == 200, r.text
    m = SECRET.search(r.text)
    assert m is not None
    return m.group(1)


def agent(secret: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {secret}"})


def query(client: TestClient, **body) -> dict:
    r = client.post("/api/agent/query", json={"model": "ventas", "measure": "venta"} | body)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ tokens


def test_tokens_page_needs_a_session(agent_settings):
    r = TestClient(app).get("/tokens", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/tokens"
    assert TestClient(app).post("/tokens", data={"days": 30}).status_code == 401


def test_secret_shown_once_and_stored_hashed(agent_settings):
    c = session("norte")
    created = c.post("/tokens", data={"name": "mi laptop", "days": 7})
    secret = SECRET.search(created.text).group(1)
    assert created.headers["cache-control"] == "no-store"
    listing = c.get("/tokens").text
    assert "mi laptop" in listing and secret not in listing
    db = sqlite3.connect(agent_settings.sessions_path)
    dump = "\n".join(db.iterdump())
    assert secret not in dump and secret[4:] not in dump


def test_cross_site_token_creation_is_refused(agent_settings):
    r = session("norte").post("/tokens", data={"days": 30}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_bearer_only_opens_the_agent_api(agent_settings):
    secret = new_token("norte")
    assert agent(secret).get("/api/agent/whoami").json() == {"user_id": "norte", "author": False}
    # the token does not open the viewer
    assert agent(secret).get("/api/r/regional/visuals/total").status_code == 401
    assert agent(secret).get("/r/regional", follow_redirects=False).status_code == 303
    # and the session cookie does not open the agent API
    assert session("norte").get("/api/agent/whoami").status_code == 401


@pytest.mark.real_auth
def test_author_token_does_not_open_the_studio(agent_settings):
    secret = new_token("autor")
    assert agent(secret).get("/api/agent/whoami").json()["author"] is True
    assert agent(secret).get("/api/catalog").status_code == 401
    assert agent(secret).post("/api/semantic/check", json={}).status_code == 401


@pytest.mark.parametrize("header", ["Bearer nope", "Bearer d2h_nope", "Basic d2h_x", "d2h_x", "Bearer ",
                                    "Bearer d2h_" + "x" * 500])
def test_bad_tokens(agent_settings, header):
    r = TestClient(app).get("/api/agent/whoami", headers={"Authorization": header})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_revoke_own_token_only(agent_settings):
    secret = new_token("norte")
    token_id = get_tokens(agent_settings.sessions_path).list("dev", "norte")[0].id
    assert session("sur").post(f"/tokens/{token_id}/revoke", follow_redirects=False).status_code == 404
    assert agent(secret).get("/api/agent/whoami").status_code == 200
    assert session("norte").post(f"/tokens/{token_id}/revoke", follow_redirects=False).status_code == 303
    assert agent(secret).get("/api/agent/whoami").status_code == 401


def test_expired_token(agent_settings):
    store = get_tokens(agent_settings.sessions_path)
    norte = Identity(user_id="norte", email="n@example.com", provider="dev", groups=("Norte",))
    _id, secret = store.create(norte, "old", 1, now=time.time() - 2 * 86400)
    assert agent(secret).get("/api/agent/whoami").status_code == 401


def test_days_are_capped(agent_settings):
    assert session("norte").post("/tokens", data={"days": 91}).status_code == 422
    assert session("norte").post("/tokens", data={"days": 0}).status_code == 422


def test_local_user_is_rechecked_on_every_call(agent_settings, tmp_path, capsys):
    users = tmp_path / "users.yaml"
    pw = tmp_path / "pw.txt"
    pw.write_text("a long enough password\n", encoding="utf-8")
    use(Settings(**(agent_settings.__dict__ | {"users_file": users})))
    with pw.open(encoding="utf-8") as stdin, pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.stdin", stdin)
        args = ["add-user", "ana", "--groups", "Sur", "--password-stdin", "--file", str(users)]
        assert local_main(args) == 0
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("D2H_DATA_DIR", str(agent_settings.data_dir))
        assert local_main(["token", "create", "ana", "--file", str(users)]) == 0
    secret = capsys.readouterr().out.strip().splitlines()[-1]
    assert query(agent(secret))["rows"] == [[77777]]
    # removing the user kills their tokens at once
    users.write_text("users: {}\n", encoding="utf-8")
    assert agent(secret).get("/api/agent/whoami").status_code == 401


def test_dev_tokens_need_dev_identities_enabled(agent_settings):
    secret = new_token("norte")
    use(Settings(**(agent_settings.__dict__ | {"dev_identities_file": None})))
    assert agent(secret).get("/api/agent/whoami").status_code == 401


# ------------------------------------------------------------------ RLS and exposure


def test_each_token_gets_its_own_rls(agent_settings):
    norte, sur = agent(new_token("norte")), agent(new_token("sur"))
    assert query(norte, dimension="region")["rows"] == [["Norte", 33333]]
    assert query(sur, dimension="region")["rows"] == [["Sur", 77777]]
    assert query(norte)["rows"] == [[33333]]


def test_the_author_also_gets_rls(agent_settings):
    assert query(agent(new_token("autor")), dimension="region")["rows"] == [["Norte", 33333]]


def test_filters_cannot_widen_rls(agent_settings):
    norte = agent(new_token("norte"))
    assert query(norte, filters=[{"dimension": "region", "op": "eq", "value": "Sur"}])["rows"] == [[None]]
    since_feb = [{"dimension": "fecha", "op": "gte", "value": "2026-02-01"}]
    rows = query(norte, dimension="canal", filters=since_feb)
    assert rows["rows"] == [["Tienda", 22222]]


def test_report_visual_is_what_the_reader_sees(agent_settings):
    norte = agent(new_token("norte"))
    r = norte.get("/api/agent/reports/regional/visuals/por_region", params={"p.desde": "2026-02-01"})
    assert r.json()["rows"] == [["Norte", 22222]]
    assert norte.get("/api/agent/reports/regional/visuals/por_region",
                     params={"user_id": "sur"}).status_code == 422


def test_reports_and_models_follow_report_access(agent_settings, publish, report_dict):
    publish(report_dict | {"access": ["Sur"]})
    norte, sur, autor = (agent(new_token(u)) for u in ("norte", "sur", "autor"))
    assert norte.get("/api/agent/reports").json() == []
    assert norte.get("/api/agent/models").json() == []
    assert norte.post("/api/agent/query", json={"model": "ventas", "measure": "venta"}).status_code == 404
    assert norte.get("/api/agent/reports/regional/visuals/total").status_code == 404
    assert [r["id"] for r in sur.get("/api/agent/reports").json()] == ["regional"]
    assert [m["name"] for m in autor.get("/api/agent/models").json()] == ["ventas"]  # the author: all


def test_models_show_no_sql_tables_or_rls(agent_settings):
    body = agent(new_token("norte")).get("/api/agent/models").text
    assert "venta" in body and "region" in body
    for secret_bit in ["SUM(monto)", "monto", "claim", "groups", "rls", '"table"']:
        assert secret_bit not in body


def test_metadata_exposure_by_default(agent_settings):
    use(Settings(**(agent_settings.__dict__ | {"ai_file": None})))
    norte = agent(new_token("norte"))
    models = norte.get("/api/agent/models").json()
    assert models[0]["exposure"] == "metadata"
    r = norte.post("/api/agent/query", json={"model": "ventas", "measure": "venta"})
    assert r.status_code == 403 and "csv" in r.json()["detail"]
    assert norte.get("/api/agent/reports/regional/visuals/total").status_code == 403


def test_none_exposure_hides_the_source(agent_settings, tmp_path):
    ai = tmp_path / "none.yaml"
    ai.write_text(yaml.safe_dump({"exposure": {"csv": "none"}}), encoding="utf-8")
    use(Settings(**(agent_settings.__dict__ | {"ai_file": ai})))
    autor = agent(new_token("autor"))
    assert autor.get("/api/agent/models").json() == []
    assert autor.get("/api/agent/reports").json() == []
    assert autor.get("/api/agent/tables").json() == []
    assert autor.get("/api/agent/reports/regional/visuals/total").status_code == 404


def test_author_only_tools(agent_settings):
    norte, autor = agent(new_token("norte")), agent(new_token("autor"))
    assert norte.get("/api/agent/tables").status_code == 403
    assert norte.get("/api/agent/profile/csv/ventas").status_code == 403
    tables = autor.get("/api/agent/tables").json()
    assert tables[0]["id"] == "csv" and tables[0]["tables"][0]["name"] == "ventas"
    assert autor.get("/api/agent/profile/csv/ventas").json()["rows"] == 4


def test_row_cap(agent_settings, tmp_path):
    ai = tmp_path / "cap.yaml"
    ai.write_text(yaml.safe_dump({"exposure": {"csv": "results"}, "max_rows": 1}), encoding="utf-8")
    use(Settings(**(agent_settings.__dict__ | {"ai_file": ai})))
    out = query(agent(new_token("autor")), dimension="canal")
    assert len(out["rows"]) == 1 and out["truncated"] is True


@pytest.mark.parametrize("body", [
    {"measure": "nope"},
    {"dimension": "nope"},
    {"measure": "SUM(monto)"},
    {"filters": [{"dimension": "fecha", "op": "between", "value": ["2026-01-01"]}]},
    {"filters": [{"dimension": "canal", "op": "eq", "value": "Web"}] * 11},
    {"sql": "SELECT 1"},
])
def test_query_rejections(agent_settings, body):
    autor = agent(new_token("autor"))
    r = autor.post("/api/agent/query", json={"model": "ventas", "measure": "venta"} | body)
    assert r.status_code == 422


def test_audit_log_has_no_values(agent_settings, caplog):
    norte = agent(new_token("norte"))
    with caplog.at_level(logging.INFO, logger="data2html.agent"):
        query(norte, dimension="region")
    assert "action=query user=norte" in caplog.text
    assert "33333" not in caplog.text and "Norte" not in caplog.text
