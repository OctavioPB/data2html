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
