import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from data2html import cancel
from data2html.api.main import app, get_settings
from data2html.api.profile import cache
from data2html.settings import Settings
from data2html.sqlgen.freeform import count_sql, page_sql, prepare_user_sql
from data2html.sqlgen.validate import UnsafeSQL

T = {"ventas": ("ventas",), "public.fact_ventas": ("pg", "public", "fact_ventas")}
CSV = b"region,monto\nNorte,10\nSur,20\nNorte,5\nCentro,7\n"


# ------------------------------------------------------------------ rewriting (pure)


@pytest.mark.parametrize(("sql", "expected"), [
    ("SELECT * FROM ventas", 'FROM "ventas"'),
    ("SELECT * FROM VENTAS v", 'FROM "ventas" AS v'),
    ("SELECT * FROM public.fact_ventas", 'FROM "pg"."public"."fact_ventas"'),
    ("SELECT * FROM pg.public.fact_ventas", 'FROM "pg"."public"."fact_ventas"'),
    ("WITH ventas AS (SELECT 1 AS a) SELECT * FROM ventas", "SELECT * FROM ventas"),  # CTE: left untouched
    ("SELECT * FROM ventas WHERE region IN (SELECT region FROM ventas)", 'IN (SELECT region FROM "ventas")'),
])
def test_rewrites_catalog_tables(sql, expected):
    assert expected in prepare_user_sql(sql, T).sql("duckdb")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM otra_tabla",
    "SELECT * FROM fact_ventas",                       # without the schema it is not a catalog name
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM system.main.duckdb_settings",
    "SELECT * FROM otra_db.public.fact_ventas",
    "WITH x AS (SELECT * FROM read_csv('C:/secreto.csv')) SELECT * FROM x",
    "SELECT (SELECT postgres_execute('pg', 'DROP TABLE t'))",
    "SELECT 1; DROP TABLE ventas",
    "INSERT INTO ventas VALUES ('x', 1)",
])
def test_rejects_unknown_tables_and_unsafe_sql(sql):
    with pytest.raises(UnsafeSQL):
        prepare_user_sql(sql, T)


def test_page_and_count_wrap_the_query():
    q = prepare_user_sql("SELECT region FROM ventas ORDER BY region", T)
    # an ordered query is paged in place, its order made total (ties broken by every column)
    assert page_sql(q, 400, 200).endswith("ORDER BY region, COLUMNS(*) LIMIT 200 OFFSET 400")
    unordered = prepare_user_sql("SELECT region FROM ventas", T)
    assert page_sql(unordered, 400, 200).endswith("AS _q LIMIT 200 OFFSET 400")
    assert count_sql(q).startswith("SELECT COUNT(*) AS n FROM (SELECT")
    with pytest.raises(UnsafeSQL):
        page_sql(q, 0, 5000)


# ------------------------------------------------------------------ API


@pytest.fixture
def client(tmp_path):
    cache.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=tmp_path, sources_file=None)
    c = TestClient(app)
    p = c.post("/api/csv/preview", files={"file": ("ventas.csv", CSV, "text/csv")}).json()
    cols = [{k: col[k] for k in ("name", "type", "date_format", "decimal_comma")} for col in p["columns"]]
    assert c.post("/api/csv/confirm", json={"upload_id": p["upload_id"], "table": "ventas",
                                            "columns": cols}).status_code == 201
    yield c
    app.dependency_overrides.clear()
    cache.clear()


def qid() -> str:
    return uuid.uuid4().hex


def run(client, sql, **kw):
    return client.post("/api/sql/run", json={"source": "csv", "sql": sql, "query_id": qid()} | kw)


def test_run_aggregate(client):
    r = run(client, "SELECT region, sum(monto) AS total FROM ventas GROUP BY region ORDER BY total DESC")
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == 3
    assert [c["name"] for c in page["columns"]] == ["region", "total"]
    types = [c["type"] for c in page["columns"]]
    assert types[0] == "VARCHAR" and types[1].startswith("DECIMAL")  # sum(BIGINT) → HUGEINT
    assert page["rows"] == [["Sur", 20], ["Norte", 15], ["Centro", 7]]


def test_paging(client):
    p1 = run(client, "SELECT * FROM ventas ORDER BY monto", limit=2).json()
    p2 = run(client, "SELECT * FROM ventas ORDER BY monto", limit=2, offset=2, with_total=False).json()
    assert [r[1] for r in p1["rows"] + p2["rows"]] == [5, 7, 10, 20]
    assert p1["total"] == 4 and p2["total"] is None


def test_errors_are_422_and_recorded(client):
    assert run(client, "SELECT * FROM no_existe").status_code == 422
    assert run(client, "DROP TABLE ventas").status_code == 422
    assert run(client, "SELECT nope FROM ventas").status_code == 422      # DuckDB binder
    assert client.post("/api/sql/run", json={"source": "otra", "sql": "SELECT 1", "query_id": qid()}
                       ).status_code == 404
    assert client.post("/api/sql/run", json={"source": "csv", "sql": "SELECT 1", "query_id": "x"}
                       ).status_code == 422
    h = client.get("/api/sql/history").json()
    assert [e["ok"] for e in h][:3] == [False, False, False]
    assert "nope" in h[0]["error"]


def test_history_only_first_page(client):
    run(client, "SELECT * FROM ventas", limit=1)
    run(client, "SELECT * FROM ventas", limit=1, offset=1)
    h = client.get("/api/sql/history").json()
    assert len(h) == 1 and h[0]["rows"] == 4 and h[0]["ok"]


def test_saved_queries(client):
    body = {"source": "csv", "sql": "SELECT count(*) FROM ventas"}
    assert client.put("/api/sql/saved/Conteo de ventas", json=body).status_code == 200
    assert client.put("/api/sql/saved/Otra", json=body | {"source": "otra"}).status_code == 404
    assert client.put("/api/sql/saved/a%2Fb", json=body).status_code in (404, 422)
    assert [q["name"] for q in client.get("/api/sql/saved").json()] == ["Conteo de ventas"]
    assert client.delete("/api/sql/saved/Conteo de ventas").status_code == 204
    assert client.delete("/api/sql/saved/Conteo de ventas").status_code == 404


SLOW = "SELECT sum(i * i) FROM range(100000000000) t(i)"


def test_cancel_running_query(client):
    query_id = qid()
    result = {}

    def worker():
        result["r"] = client.post("/api/sql/run", json={"source": "csv", "sql": SLOW, "query_id": query_id})

    t = threading.Thread(target=worker)
    started = time.perf_counter()
    t.start()
    time.sleep(0.8)
    assert client.post(f"/api/cancel/{query_id}").status_code == 204
    t.join(timeout=20)
    assert result["r"].status_code == 504
    assert result["r"].json()["detail"] == "query cancelled"
    assert time.perf_counter() - started < 10


def test_cancelled_before_start(client):
    query_id = qid()
    cancel.request(query_id)
    r = client.post("/api/sql/run", json={"source": "csv", "sql": "SELECT 1", "query_id": query_id})
    assert r.status_code == 504


def test_timeout_is_capped(client):
    r = run(client, SLOW, timeout_s=1)
    assert r.status_code == 504
    assert "1 s time limit" in r.json()["detail"]


def test_profile_accepts_query_id_and_can_be_cancelled(client):
    query_id = qid()
    assert client.get("/api/profile/csv/ventas", params={"query_id": query_id}).status_code == 200
    cache.clear()
    cancel.request(query_id)
    assert client.get("/api/profile/csv/ventas", params={"query_id": query_id}).status_code == 504
    assert client.get("/api/profile/csv/ventas", params={"query_id": "../x"}).status_code == 422


# ------------------------------------------------------------------ deterministic pages with ties


@pytest.mark.parametrize(("sql", "tail"), [
    ("SELECT * FROM t ORDER BY x DESC", 'ORDER BY "x" DESC, COLUMNS(*) LIMIT 2 OFFSET 2'),
    ("SELECT x, count(*) AS n FROM t GROUP BY x ORDER BY n DESC", "ORDER BY n DESC, 1, 2 LIMIT 2 OFFSET 2"),
    ("SELECT DISTINCT y FROM t ORDER BY y", "ORDER BY y, 1 LIMIT 2 OFFSET 2"),
])
def test_page_sql_breaks_ties(sql, tail):
    from data2html.sqlgen.freeform import page_sql
    from data2html.sqlgen.validate import ensure_single_select

    out = page_sql(ensure_single_select(sql), 2, 2)
    assert out.replace('"', "").endswith(tail.replace('"', "")), out
    ensure_single_select(out)  # the paged SQL still passes validation


def test_pages_with_ties_never_repeat_or_skip_rows():
    import duckdb

    from data2html.sqlgen.freeform import page_sql
    from data2html.sqlgen.validate import ensure_single_select

    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT i % 3 AS x, i AS y FROM range(300) r(i)")  # 100-way ties on x
    q = ensure_single_select("SELECT * FROM t ORDER BY x DESC")
    seen = [row for off in range(0, 300, 7) for row in con.execute(page_sql(q, off, 7)).fetchall()]
    assert len(seen) == 300 and len(set(seen)) == 300
    assert [r[0] for r in seen] == sorted((r[0] for r in seen), reverse=True)  # the user's order holds


def test_queries_without_order_or_with_their_own_limit_are_wrapped():
    from data2html.sqlgen.freeform import page_sql
    from data2html.sqlgen.validate import ensure_single_select

    wrapped = ["SELECT * FROM t", "SELECT * FROM t ORDER BY x LIMIT 5",
               "SELECT x, * FROM t GROUP BY ALL ORDER BY x"]
    for sql in wrapped:
        assert page_sql(ensure_single_select(sql), 0, 2).startswith("SELECT * FROM (")
