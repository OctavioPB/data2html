from datetime import date

import duckdb
import pytest

from data2html.sources.base import Identity
from data2html.spec import SemanticModel, Visual
from data2html.sqlgen.validate import ensure_single_select
from data2html.sqlgen.visual import VisualQueryError, build_visual_query

MODEL = SemanticModel.model_validate({
    "name": "ventas", "source": "csv", "table": "ventas",
    "dimensions": {
        "region": {"column": "region_desc", "type": "nominal"},
        "canal": {"column": "canal", "type": "nominal"},
        "fecha": {"column": "fecha_venta", "type": "temporal"},
    },
    "measures": {
        "venta_neta": {"sql": "SUM(monto - descuento)", "owner": "finanzas", "description": "x"},
        "pedidos": {"sql": "COUNT(*)", "owner": "comercial", "description": "x"},
    },
})
RLS_MODEL = SemanticModel.model_validate(
    MODEL.model_dump(mode="json") | {"rls": {"column": "region_desc", "claim": "groups"}}
)
TYPES = {"region_desc": "VARCHAR", "canal": "VARCHAR", "fecha_venta": "DATE", "monto": "DOUBLE"}


@pytest.fixture
def db():
    c = duckdb.connect()
    c.execute("""CREATE TABLE ventas AS SELECT * FROM (VALUES
        ('Norte', 'Web',    DATE '2026-01-05', 100.0, 10.0),
        ('Norte', 'Tienda', DATE '2026-01-20',  50.0,  0.0),
        ('Sur',   'Web',    DATE '2026-02-10', 300.0, 20.0),
        ('Centro','Tienda', DATE '2026-03-15',  80.0,  5.0)
    ) t(region_desc, canal, fecha_venta, monto, descuento)""")
    return c


def visual(**kw) -> Visual:
    return Visual.model_validate({"id": "v", "title": "t", "mark": "bar", "measure": "venta_neta",
                                  "layout": {"x": 0, "y": 0, "w": 6, "h": 3}} | kw)


def run(db, v, model=MODEL, **kw):
    q = build_visual_query(v, model, ("ventas",), column_types=TYPES, identity=kw.pop("identity", None),
                           author_preview=kw.pop("author_preview", True), **kw)
    ensure_single_select(q.sql)  # generated SQL also passes free-form SQL validation
    return db.execute(q.sql, q.params or None).fetchall(), q


def test_bar_by_region_ordered_by_measure(db):
    rows, q = run(db, visual(dimension="region"))
    assert rows == [("Sur", 280.0), ("Norte", 140.0), ("Centro", 75.0)]
    assert (q.dimension, q.measure) == ("region", "venta_neta")


def test_line_by_month(db):
    rows, _ = run(db, visual(mark="line", dimension="fecha", time_grain="month", measure="pedidos"))
    assert rows == [(date(2026, 1, 1), 2), (date(2026, 2, 1), 1), (date(2026, 3, 1), 1)]


def test_kpi_without_dimension(db):
    rows, _ = run(db, visual(mark="kpi"))
    assert rows == [(495.0,)]


def test_color(db):
    rows, q = run(db, visual(dimension="region", color="canal"))
    assert ("Norte", "Web", 90.0) in rows and q.color == "canal"


@pytest.mark.parametrize(("f", "expected"), [
    ({"dimension": "canal", "op": "eq", "value": "Web"}, 370.0),
    ({"dimension": "canal", "op": "neq", "value": "Web"}, 125.0),
    ({"dimension": "region", "op": "in", "value": ["Norte", "Centro"]}, 215.0),
    ({"dimension": "fecha", "op": "between", "value": ["2026-01-01", "2026-01-31"]}, 140.0),
    ({"dimension": "fecha", "op": "gte", "value": "2026-02-01"}, 355.0),
])
def test_fixed_filters(db, f, expected):
    rows, q = run(db, visual(mark="kpi", filters=[f]))
    assert rows == [(expected,)]
    assert "$p0" in q.sql


def test_param_filter_and_missing_param(db):
    v = visual(mark="kpi", filters=[{"dimension": "canal", "op": "eq", "param": "canal_elegido"}])
    rows, _ = run(db, v, report_params={"canal_elegido": "Tienda"})
    assert rows == [(125.0,)]
    with pytest.raises(VisualQueryError, match="canal_elegido"):
        run(db, v)


def test_filter_values_never_in_sql(db):
    evil = "Web' OR '1'='1"
    rows, q = run(db, visual(mark="kpi", filters=[{"dimension": "canal", "op": "eq", "value": evil}]))
    assert rows == [(None,)] and evil not in q.sql and evil in q.params.values()


def test_rls_requires_identity_unless_author_preview(db):
    with pytest.raises(VisualQueryError, match="identity"):
        run(db, visual(dimension="region"), model=RLS_MODEL, author_preview=False)
    rows, _ = run(db, visual(dimension="region"), model=RLS_MODEL, author_preview=True)
    assert len(rows) == 3  # the author sees everything


def test_rls_filters_by_reader_groups(db):
    reader = Identity(user_id="u1", email="u1@x", provider="local", groups=("Norte", "Centro"))
    rows, q = run(db, visual(dimension="region"), model=RLS_MODEL, identity=reader, author_preview=False)
    assert sorted(r[0] for r in rows) == ["Centro", "Norte"]
    assert "Norte" not in q.sql  # claims also travel as parameters
    nobody = Identity(user_id="u2", email="u2@x", provider="local", groups=())
    rows, _ = run(db, visual(dimension="region"), model=RLS_MODEL, identity=nobody, author_preview=False)
    assert rows == []


def test_rls_exact_recheck_for_loose_collation_sources(db):
    # MySQL (loose_collation): the pushed-down IN stays, plus a copy DuckDB cannot push down
    reader = Identity(user_id="u1", email="u1@x", provider="local", groups=("Norte",))
    rows, q = run(db, visual(dimension="region"), model=RLS_MODEL, identity=reader, author_preview=False,
                  rls_exact_recheck=True)
    assert [r[0] for r in rows] == ["Norte"]
    assert "(\"region_desc\" || '') IN ($p0)" in q.sql and q.params == {"p0": "Norte"}
    _, plain = run(db, visual(dimension="region"), model=RLS_MODEL, identity=reader, author_preview=False)
    assert "||" not in plain.sql


def test_unknown_names(db):
    with pytest.raises(VisualQueryError):
        run(db, visual(measure="margen"))
    with pytest.raises(VisualQueryError):
        run(db, visual(dimension="pais"))
    with pytest.raises(VisualQueryError, match="temporal"):
        run(db, visual(dimension="region", time_grain="month"))


def test_limit_and_qualified_relation():
    q = build_visual_query(visual(dimension="region"), MODEL, ("pg_dev", "public", "fact_ventas"),
                           column_types=TYPES, identity=None, author_preview=True, limit=50)
    assert 'FROM "pg_dev"."public"."fact_ventas"' in q.sql and q.sql.endswith("LIMIT 50")
