"""Integration with the development MySQL: `docker compose up -d mysql` (ADR 0011).

Skipped when there is no server. Variables (with the development docker-compose defaults):
D2H_TEST_MYSQL_HOST, D2H_TEST_MYSQL_PORT and MYSQL_DEV_PASSWORD (the SELECT-only `d2h_reader`).
"""

import os
import socket
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.mysql import MySQLSource
from data2html.sources.registry import MySQLConfig
from data2html.sqlgen.validate import UnsafeSQL

HOST = os.environ.get("D2H_TEST_MYSQL_HOST", "127.0.0.1")
PORT = int(os.environ.get("D2H_TEST_MYSQL_PORT", "3306"))
REGIONS = ["Bajío", "Centro", "Norte", "Sur"]


def _reachable() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.mysql,
    pytest.mark.skipif(not _reachable(), reason=f"no MySQL at {HOST}:{PORT} (docker compose up -d mysql)"),
]

SOURCES = (
    f"sources:\n  my_dev:\n    type: mysql\n    host: '{HOST}'\n    port: {PORT}\n    database: d2h\n"
    "    user: d2h_reader\n    password_env: MYSQL_DEV_PASSWORD\n    ssl_mode: disabled\n"
)


@pytest.fixture
def my_env(monkeypatch):
    monkeypatch.setenv("MYSQL_DEV_PASSWORD", os.environ.get("MYSQL_DEV_PASSWORD", "d2h"))


@pytest.fixture
def my(tmp_path, my_env):
    s = Settings(data_dir=tmp_path, duckdb_memory_limit="256MB", duckdb_threads=1)
    cfg = MySQLConfig(type="mysql", host=HOST, port=PORT, database="d2h", user="d2h_reader",
                      password_env="MYSQL_DEV_PASSWORD", ssl_mode="disabled")  # noqa: S106 (a variable name)
    src = MySQLSource("my_dev", cfg, s, CatalogMeta(s.catalog_meta_path))
    yield src
    src.close()


@pytest.fixture
def settings(tmp_path, my_env):
    f = tmp_path / "sources.yaml"
    f.write_text(SOURCES, encoding="utf-8")
    dev = tmp_path / "dev_identities.yaml"
    dev.write_text(yaml.safe_dump({"identities": {
        "sur": {"email": "s@x", "groups": ["Sur"]},
        "sur_minusculas": {"email": "m@x", "groups": ["sur"]},
        "bajio": {"email": "b@x", "groups": ["Bajío"]},
        "bajio_sin_acento": {"email": "c@x", "groups": ["Bajio"]},
    }}, allow_unicode=True), encoding="utf-8")
    s = Settings(data_dir=tmp_path, sources_file=f, content_dir=tmp_path / "content", dev_identities_file=dev,
                 dev_hosts=("testclient",))
    app.dependency_overrides[get_settings] = lambda: s
    yield s
    app.dependency_overrides.clear()


@pytest.fixture
def client(settings):
    return TestClient(app)


# ------------------------------------------------------------------ the source


def test_catalog_only_shows_the_database(my):
    tables = my.catalog()
    assert [t.name for t in tables] == ["d2h.fact_ventas"]  # no information_schema
    assert [(c.name, c.type) for c in tables[0].columns][:3] == [
        ("pedido_id", "INTEGER"), ("fecha_venta", "DATE"), ("region_desc", "VARCHAR")]
    assert my.relation("d2h.fact_ventas") == ("my_dev", "d2h", "fact_ventas")
    with pytest.raises(Exception, match="unknown table"):
        my.relation("information_schema.USER_PRIVILEGES")


def test_execute_with_params_and_accents(my):
    t = my.execute("SELECT count(*) AS n FROM my_dev.d2h.fact_ventas WHERE region_desc = $r",
                   {"r": "Bajío"}, identity=None, timeout_s=10)
    assert t.column("n").to_pylist() == [12500]


@pytest.mark.parametrize("sql", [
    "DELETE FROM my_dev.d2h.fact_ventas",
    "SELECT * FROM mysql_query('my_dev', 'SELECT 1')",
    "SELECT mysql_execute('my_dev', 'DELETE FROM fact_ventas')",
    "CALL mysql_clear_cache()",
    "SELECT * FROM duckdb_secrets()",
])
def test_rejects_writes_and_escape_hatches(my, sql):
    with pytest.raises(UnsafeSQL):
        my.execute(sql, {}, identity=None, timeout_s=10)


def test_write_blocked_even_without_validation(my):
    """Layer 2: READ_ONLY + locked sandbox, even if someone bypassed ensure_single_select."""
    cur = my._cursor()
    try:
        attach = "ATTACH '' AS otra (TYPE mysql, SECRET my_dev_secret)"
        for sql in ["DELETE FROM my_dev.d2h.fact_ventas", attach]:
            with pytest.raises(Exception, match="(?i)cannot execute|disabled|permission"):
                cur.execute(sql)
        (secret,) = cur.execute("SELECT secret_string FROM duckdb_secrets()").fetchone()
        assert "d2h" not in secret.split("password=")[-1][:3]  # the password is redacted
    finally:
        cur.close()


def test_wrong_password_is_a_generic_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("MYSQL_BAD", "nope")
    s = Settings(data_dir=tmp_path)
    cfg = MySQLConfig(type="mysql", host=HOST, port=PORT, database="d2h", user="d2h_reader",
                      password_env="MYSQL_BAD", ssl_mode="disabled")  # noqa: S106
    src = MySQLSource("bad", cfg, s, CatalogMeta(s.catalog_meta_path))
    with pytest.raises(Exception, match="could not connect to source 'bad'") as e:
        src.catalog()
    assert "nope" not in str(e.value) and "d2h_reader" not in str(e.value)


# ------------------------------------------------------------------ the API


def test_api_catalog_explore_profile_and_sql(client):
    cat = client.get("/api/catalog").json()["sources"]
    my = next(s for s in cat if s["id"] == "my_dev")
    assert my["status"] == "ok" and my["kind"] == "mysql"
    assert [t["name"] for t in my["tables"]] == ["d2h.fact_ventas"]

    r = client.post("/api/explore/my_dev/d2h.fact_ventas", json={
        "filters": [{"column": "region_desc", "op": "=", "value": "Bajío"}],
        "sort": [{"column": "monto_bruto", "desc": True}], "limit": 5,
    })
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 12500

    from data2html.api.profile import cache

    cache.clear()
    p = client.get("/api/profile/my_dev/d2h.fact_ventas").json()
    region = next(c for c in p["columns"] if c["name"] == "region_desc")
    assert sorted(v["value"] for v in region["top"]) == REGIONS

    r = client.post("/api/sql/run", json={
        "source": "my_dev", "query_id": "test-my-sql-0001",
        "sql": "SELECT region_desc, count(*) AS n FROM d2h.fact_ventas GROUP BY 1 ORDER BY 1",
    })
    assert r.status_code == 200, r.text
    assert [row[0] for row in r.json()["rows"]] == REGIONS


def _publish(settings: Settings) -> None:
    example = Path(__file__).resolve().parents[2] / "examples/semantic/ventas.yaml"
    model = yaml.safe_load(example.read_text(encoding="utf-8"))
    model |= {"source": "my_dev", "table": "d2h.fact_ventas"}
    settings.semantic_dir.mkdir(parents=True)
    text = yaml.safe_dump(model, allow_unicode=True)
    (settings.semantic_dir / "ventas.yaml").write_text(text, encoding="utf-8")
    report = {"id": "regional", "title": "Regional", "semantic_model": "ventas", "visuals": [
        {"id": "por_region", "title": "x", "mark": "bar", "dimension": "region", "measure": "pedidos",
         "layout": {"x": 0, "y": 0, "w": 6, "h": 4}}]}
    settings.reports_dir.mkdir(parents=True)
    (settings.reports_dir / "regional.yaml").write_text(yaml.safe_dump(report), encoding="utf-8")


def _rows_as(user: str) -> list:
    c = TestClient(app)
    c.post("/dev/login", data={"user_id": user, "next": "/r/regional"}, follow_redirects=False)
    r = c.get("/api/r/regional/visuals/por_region")
    assert r.status_code == 200, r.text
    return r.json()["rows"]


def test_viewer_rls_is_exact_despite_mysql_collation(settings):
    """MySQL's utf8mb4_0900_ai_ci ignores case and accents, and DuckDB pushes the filter down: without the
    exact re-check, a group "sur" or "Bajio" would see the rows of "Sur" or "Bajío"."""
    _publish(settings)
    assert _rows_as("sur") == [["Sur", 12500]]
    assert _rows_as("bajio") == [["Bajío", 12500]]
    assert _rows_as("sur_minusculas") == []
    assert _rows_as("bajio_sin_acento") == []


def test_author_preview_on_mysql(client, settings):
    _publish(settings)
    r = client.post("/api/visual/query", json={"model": "ventas", "visual": {
        "mark": "bar", "measure": "pedidos", "dimension": "region"}})
    assert r.status_code == 200, r.text
    assert sorted(row[0] for row in r.json()["rows"]) == REGIONS
    assert '"my_dev"."d2h"."fact_ventas"' in r.json()["sql"]
