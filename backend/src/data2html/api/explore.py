"""Explorador tipo Excel: una página de filas por petición, nunca la tabla completa."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid

from fastapi import APIRouter
from sqlglot import exp

from data2html.api.deps import MetaDep, SettingsDep, SourceDep
from data2html.api.schemas import Cell, ExploreColumn, ExplorePage
from data2html.sources.base import DataSource
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sqlgen.explore import ComputedColumn, ExploreRequest, InvalidExplore, build_explore

router = APIRouter(prefix="/api/explore", tags=["explore"])

_JS_SAFE_INT = 2**53 - 1


def to_cell(v: object) -> Cell:
    """Valor Arrow → celda JSON. Enteros fuera del rango seguro de JS viajan como texto."""
    if v is None or isinstance(v, str | bool | float):
        return v
    if isinstance(v, int):
        return v if abs(v) <= _JS_SAFE_INT else str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.date | dt.datetime | dt.time):
        return v.isoformat()
    if isinstance(v, bytes):
        return f"<binario, {len(v)} bytes>"
    if isinstance(v, list | dict):
        return json.dumps(v, default=str, ensure_ascii=False)
    return str(v)


def run_explore(
    src: DataSource, meta: CatalogMeta, table: str, req: ExploreRequest, timeout_s: int
) -> ExplorePage:
    info = src.table_info(table)
    computed = meta.get(src.id, table).computed
    types = {c.name: c.type for c in info.columns}
    q = build_explore(src.relation(table), types, computed, req)
    page = src.execute(q.page, q.params, identity=None, timeout_s=timeout_s, query_id=uuid.uuid4().hex)
    total = None
    if q.count:
        counted = src.execute(q.count, q.params, identity=None, timeout_s=timeout_s)
        total = int(counted.column("n")[0].as_py())

    computed_names = {c.name for c in computed}
    types |= {c.name: c.type for c in computed}
    data = [[to_cell(v) for v in page.column(i).to_pylist()] for i in range(page.num_columns)]
    return ExplorePage(
        columns=[ExploreColumn(name=n, type=types.get(n, ""), computed=n in computed_names)
                 for n in page.column_names],
        rows=[list(r) for r in zip(*data, strict=True)],
        offset=req.offset,
        total=total,
    )


def resolve_computed(
    src: DataSource, meta: CatalogMeta, table: str, col: ComputedColumn, timeout_s: int
) -> ComputedColumn:
    """Valida la expresión ejecutándola sobre una fila y devuelve la columna con su tipo DuckDB."""
    info = src.table_info(table)
    if col.name in {c.name for c in info.columns}:
        raise InvalidExplore(f"ya existe una columna {col.name!r}")
    others = [c for c in meta.get(src.id, table).computed if c.name != col.name]
    q = build_explore(src.relation(table), {c.name: c.type for c in info.columns}, [*others, col],
                      ExploreRequest(limit=1, with_total=False))
    probe = exp.select(exp.func("typeof", exp.column(exp.to_identifier(col.name, quoted=True))).as_("t"))
    sql = probe.from_(exp.maybe_parse(q.page, dialect="duckdb").subquery("_p")).sql("duckdb")
    res = src.execute(sql, q.params, identity=None, timeout_s=timeout_s)
    type_ = res.column("t")[0].as_py() if res.num_rows else ""
    return col.model_copy(update={"type": type_ or "VARCHAR"})


@router.post("/{source}/{table}")
def explore(
    table: str, req: ExploreRequest, src: SourceDep, meta: MetaDep, settings: SettingsDep
) -> ExplorePage:
    return run_explore(src, meta, table, req, settings.query_timeout_s)
