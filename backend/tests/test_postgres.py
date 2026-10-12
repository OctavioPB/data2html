"""Integration with the development Postgres: `docker compose up -d postgres`.

Skipped when there is no server. Variables (with the development docker-compose defaults):
D2H_TEST_PG_HOST, D2H_TEST_PG_PORT and PG_DEV_PASSWORD.
"""

import os
import socket

import pytest
from fastapi.testclient import TestClient

from data2html.api.main import app, get_settings
from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.postgres import PostgresSource
from data2html.sources.registry import PostgresConfig
from data2html.sqlgen.validate import UnsafeSQL

HOST = os.environ.get("D2H_TEST_PG_HOST", "localhost")
PORT = int(os.environ.get("D2H_TEST_PG_PORT", "5432"))


def _reachable() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not _reachable(), reason=f"no Postgres at {HOST}:{PORT} (docker compose up)"),
]


@pytest.fixture
def pg_env(monkeypatch):
    monkeypatch.setenv("PG_DEV_PASSWORD", os.environ.get("PG_DEV_PASSWORD", "d2h"))


@pytest.fixture
def pg(tmp_path, pg_env):
    s = Settings(data_dir=tmp_path, duckdb_memory_limit="256MB", duckdb_threads=1)
    cfg = PostgresConfig(type="postgres", host=HOST, port=PORT, database="d2h", user="d2h_reader",
                         password_env="PG_DEV_PASSWORD")  # noqa: S106 (a variable name, not a secret)
    src = PostgresSource("pg_dev", cfg, s, CatalogMeta(s.catalog_meta_path))
    yield src
    src.close()


@pytest.fixture
def client(tmp_path, pg_env):
    f = tmp_path / "sources.yaml"
    f.write_text(
        f"sources:\n  pg_dev:\n    type: postgres\n    host: {HOST}\n    port: {PORT}\n    database: d2h\n"
        "    user: d2h_reader\n    password_env: PG_DEV_PASSWORD\n",
        encoding="utf-8",
    )
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=tmp_path, sources_file=f)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_catalog(pg):
    (t,) = [t for t in pg.catalog() if t.name == "public.fact_ventas"]
    assert [(c.name, c.type) for c in t.columns][:3] == [
        ("pedido_id", "INTEGER"), ("fecha_venta", "DATE"), ("region_desc", "VARCHAR")]
    assert t.row_count is None
    assert pg.relation("public.fact_ventas") == ("pg_dev", "public", "fact_ventas")


def test_execute_with_params(pg):
    t = pg.execute("SELECT count(*) AS n FROM pg_dev.public.fact_ventas WHERE region_desc = $r",
                   {"r": "Norte"}, identity=None, timeout_s=10)
    assert t.column("n").to_pylist() == [12500]


@pytest.mark.parametrize("sql", [
    "DELETE FROM pg_dev.public.fact_ventas",
    "SELECT postgres_execute('pg_dev', 'DELETE FROM fact_ventas')",
    "SELECT * FROM postgres_scan('host=localhost dbname=d2h user=d2h', 'public', 'fact_ventas')",
    "SELECT * FROM postgres_query('pg_dev', 'SELECT 1')",
    "SELECT * FROM duckdb_secrets()",
])
def test_rejects_writes_and_escape_hatches(pg, sql):
    with pytest.raises(UnsafeSQL):
        pg.execute(sql, {}, identity=None, timeout_s=10)


def test_write_blocked_even_without_validation(pg):
    """Layer 2: READ_ONLY + locked sandbox, even if someone bypassed ensure_single_select."""
    cur = pg._cursor()
    try:
        for sql in ["DELETE FROM pg_dev.public.fact_ventas",
                    "ATTACH '' AS otra (TYPE postgres, SECRET pg_dev_secret)"]:
            with pytest.raises(Exception, match="(?i)cannot execute|disabled|permission"):
                cur.execute(sql)
        (secret,) = cur.execute("SELECT secret_string FROM duckdb_secrets()").fetchone()
        assert "password=redacted" in secret
    finally:
        cur.close()


def test_api_catalog_and_explore(client):
    cat = client.get("/api/catalog").json()["sources"]
    pg = next(s for s in cat if s["id"] == "pg_dev")
    assert pg["status"] == "ok" and pg["kind"] == "postgres"
    assert "public.fact_ventas" in [t["name"] for t in pg["tables"]]

    r = client.post("/api/explore/pg_dev/public.fact_ventas", json={
        "filters": [{"column": "region_desc", "op": "=", "value": "Sur"},
                    {"column": "fecha_venta", "op": ">=", "value": "2026-01-01"}],
        "sort": [{"column": "monto_bruto", "desc": True}], "limit": 5,
    })
    assert r.status_code == 200, r.text
    page = r.json()
    assert len(page["rows"]) == 5 and 0 < page["total"] < 12500
    montos = [row[4] for row in page["rows"]]
    assert montos == sorted(montos, reverse=True)


def test_api_computed_column_on_postgres(client):
    r = client.put("/api/catalog/pg_dev/public.fact_ventas/computed",
                   json={"name": "neto", "expr": "monto_bruto - descuento"})
    assert r.status_code == 200, r.text
    page = client.post("/api/explore/pg_dev/public.fact_ventas",
                       json={"sort": [{"column": "neto", "desc": True}], "limit": 1}).json()
    assert page["columns"][-1]["name"] == "neto" and page["columns"][-1]["computed"]


def test_api_unknown_table_and_schema(client):
    assert client.post("/api/explore/pg_dev/public.no_existe", json={}).status_code == 404
    assert client.post("/api/explore/pg_dev/otro.fact_ventas", json={}).status_code == 404


def test_api_profile_postgres(client):
    from data2html.api.profile import cache

    cache.clear()
    r = client.get("/api/profile/pg_dev/public.fact_ventas")
    assert r.status_code == 200, r.text
    p = r.json()
    # 50k rows < 100k sample: it fits entirely and is not flagged as sampled
    assert (p["rows"], p["sampled"], p["sample_size"]) == (50000, False, 100000)
    region = next(c for c in p["columns"] if c["name"] == "region_desc")
    assert sorted(v["count"] for v in region["top"]) == [12500] * 4
    pedido = next(c for c in p["columns"] if c["name"] == "pedido_id")
    assert "possible_id" in [w["code"] for w in pedido["warnings"]]


def test_sql_editor_on_postgres(client):
    r = client.post("/api/sql/run", json={
        "source": "pg_dev", "query_id": "test-pg-sql-0001",
        "sql": "SELECT region_desc, count(*) AS n FROM public.fact_ventas GROUP BY 1 ORDER BY 1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [["Bajío", 12500], ["Centro", 12500], ["Norte", 12500], ["Sur", 12500]]
    escape = client.post("/api/sql/run", json={
        "source": "pg_dev", "query_id": "test-pg-sql-0002",
        "sql": "SELECT * FROM pg_catalog.pg_user",
    })
    assert escape.status_code == 422


def test_demo_fase5_venta_neta_por_region(client):
    """Phase 5 demo with the repo's example model: bars → table → pie, same numbers."""
    from pathlib import Path

    import yaml

    example = Path(__file__).resolve().parents[2] / "examples/semantic/ventas.yaml"
    model = yaml.safe_load(example.read_text(encoding="utf-8")) | {"source": "pg_dev"}
    assert client.post("/api/semantic/check", json=model).json() == []
    assert client.put("/api/semantic/ventas", json=model).status_code == 200

    results = {}
    for mark in ("bar", "table", "pie"):
        r = client.post("/api/visual/query", json={"model": "ventas", "visual": {
            "mark": mark, "measure": "venta_neta", "dimension": "region"}})
        assert r.status_code == 200, r.text
        results[mark] = r.json()
    assert results["bar"]["rows"] == results["table"]["rows"] == results["pie"]["rows"]
    assert sorted(r[0] for r in results["bar"]["rows"]) == ["Bajío", "Centro", "Norte", "Sur"]
    assert results["bar"]["allowed_marks"] == ["table", "bar", "pie"]
    assert '"pg_dev"."public"."fact_ventas"' in results["bar"]["sql"]
