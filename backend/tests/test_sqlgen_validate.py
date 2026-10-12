import pytest

from data2html.sqlgen.validate import UnsafeSQL, ensure_single_select


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "SELECT 1 UNION ALL SELECT 2",
])
def test_accepts_single_query(sql):
    ensure_single_select(sql)


@pytest.mark.parametrize("sql", [
    "", "DELETE FROM t", "SELECT 1; DROP TABLE t", "CREATE TABLE x AS SELECT 1",
    "PRAGMA version", "SET threads = 1", "SELEC 1 FROM",
])
def test_rejects_everything_else(sql):
    with pytest.raises(UnsafeSQL):
        ensure_single_select(sql)


@pytest.mark.parametrize(("sql", "fn"), [
    ("SELECT * FROM postgres_scan('host=evil', 'public', 't')", "postgres_scan"),
    ("SELECT * FROM postgres_query('pg', 'select 1')", "postgres_query"),
    ("SELECT postgres_execute('pg', 'DROP TABLE t')", "postgres_execute"),
    ("SELECT * FROM read_csv('C:/secreto.csv')", "read_csv"),
    ("SELECT * FROM t WHERE a IN (SELECT * FROM read_parquet('x'))", "read_parquet"),
    ("SELECT * FROM glob('*')", "glob"),
    ("SELECT * FROM duckdb_secrets()", "duckdb_secrets"),
    ("SELECT current_setting('threads')", "current_setting"),
    ("SELECT getenv('PG_DEV_PASSWORD')", "getenv"),
    ("SELECT * FROM query('SELECT 1')", "query"),
    ("SELECT * FROM mi_funcion_rara()", "mi_funcion_rara"),
])
def test_rejects_dangerous_functions(sql, fn):
    with pytest.raises(UnsafeSQL, match=fn):
        ensure_single_select(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM range(10)",
    "SELECT * FROM pg_dev.public.fact_ventas WHERE upper(region_desc) = $p0",
    "SELECT strftime(fecha, '%Y'), count(*) FROM t GROUP BY 1",
])
def test_allows_normal_queries(sql):
    ensure_single_select(sql)
