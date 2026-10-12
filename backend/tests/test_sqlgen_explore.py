from datetime import date

import duckdb
import pytest
from pydantic import ValidationError

from data2html.sqlgen.explore import (
    ColumnFilter,
    ComputedColumn,
    ExploreRequest,
    InvalidExplore,
    build_explore,
    parse_computed,
)
from data2html.sqlgen.validate import ensure_single_select

COLS = {"region": "VARCHAR", "monto": "DOUBLE", "fecha": "DATE", "cp": "VARCHAR"}


@pytest.fixture
def db():
    c = duckdb.connect()
    c.execute("""CREATE TABLE ventas AS SELECT * FROM (VALUES
        ('Norte', 10.0, DATE '2026-01-05', '01000'),
        ('Sur',   25.5, DATE '2026-02-10', '02000'),
        ('Norte', 5.0,  DATE '2026-03-15', NULL),
        ('100%_real', 7.0, DATE '2026-03-20', '03000')
    ) t(region, monto, fecha, cp)""")
    return c


def run(db, req: ExploreRequest, computed=()):
    q = build_explore(("ventas",), COLS, list(computed), req)
    ensure_single_select(q.page)
    rows = db.execute(q.page, q.params or None).fetchall()
    total = db.execute(q.count, q.params or None).fetchone()[0] if q.count else None
    return rows, total


def test_page_and_total(db):
    rows, total = run(db, ExploreRequest(limit=2, offset=1))
    assert len(rows) == 2 and total == 4


def test_sort_desc(db):
    rows, _ = run(db, ExploreRequest(sort=[{"column": "monto", "desc": True}]))
    assert [r[1] for r in rows] == [25.5, 10.0, 7.0, 5.0]


@pytest.mark.parametrize(("f", "expected"), [
    ({"column": "region", "op": "=", "value": "Norte"}, 2),
    ({"column": "monto", "op": ">", "value": 9}, 2),
    ({"column": "fecha", "op": ">=", "value": "2026-02-10"}, 3),
    ({"column": "fecha", "op": "between", "value": ["2026-01-01", "2026-02-28"]}, 2),
    ({"column": "region", "op": "in", "value": ["Sur", "Este"]}, 1),
    ({"column": "region", "op": "contains", "value": "ort"}, 2),
    ({"column": "region", "op": "starts_with", "value": "no"}, 2),
    ({"column": "cp", "op": "is_null"}, 1),
    ({"column": "cp", "op": "not_null"}, 3),
    ({"column": "monto", "op": "contains", "value": "5"}, 2),
])
def test_filters(db, f, expected):
    _, total = run(db, ExploreRequest(filters=[f]))
    assert total == expected


def test_like_wildcards_are_literal(db):
    _, total = run(db, ExploreRequest(filters=[{"column": "region", "op": "contains", "value": "%_"}]))
    assert total == 1  # only '100%_real', not everything


def test_search_only_text_columns(db):
    assert run(db, ExploreRequest(search="sur"))[1] == 1
    assert run(db, ExploreRequest(search="02000"))[1] == 1


def test_values_are_parameters_not_sql(db):
    evil = "x' OR 1=1; DROP TABLE ventas; --"
    req = ExploreRequest(filters=[{"column": "region", "op": "=", "value": evil}], search=evil)
    q = build_explore(("ventas",), COLS, [], req)
    assert "DROP" not in q.page and evil in q.params.values()
    assert run(db, ExploreRequest(filters=[{"column": "region", "op": "=", "value": evil}]))[1] == 0
    assert db.execute("SELECT count(*) FROM ventas").fetchone()[0] == 4


@pytest.mark.parametrize("col", ['region"; DROP TABLE ventas; --', "nope", "*"])
def test_unknown_columns_rejected(col):
    with pytest.raises(InvalidExplore):
        build_explore(("ventas",), COLS, [], ExploreRequest(filters=[{"column": col, "op": "is_null"}]))
    with pytest.raises(InvalidExplore):
        build_explore(("ventas",), COLS, [], ExploreRequest(sort=[{"column": col}]))


def test_computed_columns(db):
    cc = [ComputedColumn(name="con_iva", expr="monto * 1.16", type="DOUBLE"),
          ComputedColumn(name="mes", expr="strftime(fecha, '%Y-%m')", type="VARCHAR")]
    req = ExploreRequest(filters=[{"column": "con_iva", "op": ">", "value": 20}],
                         sort=[{"column": "mes"}], search="2026-02")
    rows, total = run(db, req, cc)
    assert total == 1
    assert float(rows[0][4]) == pytest.approx(29.58) and rows[0][5] == "2026-02"


@pytest.mark.parametrize(("expr", "msg"), [
    ("(SELECT max(monto) FROM ventas)", "SUBQUERY"),
    ("sum(monto)", "SUM"),
    ("row_number() OVER ()", "WINDOW"),
    ("read_text('C:/Windows/win.ini')", "not allowed"),
    ("getenv('PATH')", "not allowed"),
    ("current_setting('threads')", "not allowed"),
    ("otra.monto", "prefix"),
    ("nope + 1", "unknown column"),
    ("monto +", "invalid expression"),
    ("$p0", "PLACEHOLDER"),
])
def test_computed_rejects_unsafe(expr, msg):
    with pytest.raises(InvalidExplore, match=msg):
        parse_computed(expr, set(COLS))


def test_computed_name_clash():
    with pytest.raises(InvalidExplore, match="clashes"):
        build_explore(("ventas",), COLS, [ComputedColumn(name="monto", expr="1")], ExploreRequest())


def test_sort_has_deterministic_tiebreak():
    q = build_explore(("ventas",), COLS, [], ExploreRequest(sort=[{"column": "region"}]))
    assert 'ORDER BY "region" ASC, "monto", "fecha", "cp"' in q.page


@pytest.mark.parametrize("bad", [
    {"column": "a", "op": "=", "value": None},
    {"column": "a", "op": "=", "value": [1, 2]},
    {"column": "a", "op": "between", "value": [1]},
    {"column": "a", "op": "in", "value": []},
    {"column": "a", "op": "is_null", "value": 1},
    {"column": "a", "op": "like", "value": "x"},
])
def test_filter_shape_validation(bad):
    with pytest.raises(ValidationError):
        ColumnFilter.model_validate(bad)


def test_limit_is_capped():
    with pytest.raises(ValidationError):
        ExploreRequest(limit=5000)


def test_date_param_is_cast(db):
    rows, _ = run(db, ExploreRequest(filters=[{"column": "fecha", "op": "=", "value": "2026-01-05"}]))
    assert rows[0][2] == date(2026, 1, 5)


def test_qualified_relation():
    q = build_explore(("pg_dev", "public", "fact ventas"), COLS, [], ExploreRequest())
    assert 'FROM "pg_dev"."public"."fact ventas"' in q.page
    with pytest.raises(InvalidExplore):
        build_explore((), COLS, [], ExploreRequest())
