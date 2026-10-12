"""Editor SQL: ejecutar por páginas, cancelar, historial y consultas guardadas."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Annotated

import pyarrow as pa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from data2html import cancel
from data2html.api.deps import RegistryDep, SettingsDep
from data2html.api.explore import to_cell
from data2html.api.schemas import Cell, ExploreColumn
from data2html.settings import Settings
from data2html.sqlgen.freeform import MAX_PAGE, count_sql, page_sql, prepare_user_sql
from data2html.sqlstore import SQL_MAX, HistoryEntry, SavedName, SavedQuery, SqlStore

router = APIRouter(prefix="/api/sql", tags=["sql"])
jobs = APIRouter(prefix="/api", tags=["jobs"])


@lru_cache
def _store(settings: Settings) -> SqlStore:
    return SqlStore(settings.data_dir)


def get_store(settings: SettingsDep) -> SqlStore:
    return _store(settings)


StoreDep = Annotated[SqlStore, Depends(get_store)]


class SqlRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    sql: Annotated[str, Field(min_length=1, max_length=SQL_MAX)]
    query_id: Annotated[str, Field(pattern=cancel.QUERY_ID_RE.pattern)]
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=MAX_PAGE)] = 200
    with_total: bool = True
    timeout_s: Annotated[int | None, Field(ge=1)] = None


class SqlPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[ExploreColumn]
    rows: list[list[Cell]]
    offset: int
    total: int | None
    elapsed_ms: int


class SaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    sql: Annotated[str, Field(min_length=1, max_length=SQL_MAX)]


def duckdb_type(t: pa.DataType) -> str:
    """Tipo Arrow del resultado → nombre de tipo DuckDB (el mismo vocabulario que el catálogo)."""
    if pa.types.is_boolean(t):
        return "BOOLEAN"
    if pa.types.is_integer(t):
        return "BIGINT"
    if pa.types.is_floating(t):
        return "DOUBLE"
    if pa.types.is_decimal(t):
        return f"DECIMAL({t.precision},{t.scale})"
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "VARCHAR"
    if pa.types.is_date(t):
        return "DATE"
    if pa.types.is_timestamp(t):
        return "TIMESTAMP"
    return str(t).upper()


@router.post("/run")
def run(req: SqlRun, registry: RegistryDep, store: StoreDep, settings: SettingsDep) -> SqlPage:
    src = registry.get(req.source)
    timeout = min(req.timeout_s or settings.query_timeout_s, settings.query_timeout_s)
    first = req.offset == 0
    t0 = time.perf_counter()
    try:
        tables = {t.name: src.relation(t.name) for t in src.catalog()}
        q = prepare_user_sql(req.sql, tables)
        cancel.raise_if_cancelled(req.query_id)
        page = src.execute(page_sql(q, req.offset, req.limit), {}, identity=None, timeout_s=timeout,
                           query_id=req.query_id)
        total = None
        if req.with_total:
            cancel.raise_if_cancelled(req.query_id)
            counted = src.execute(count_sql(q), {}, identity=None, timeout_s=timeout, query_id=req.query_id)
            total = int(counted.column("n")[0].as_py())
    except Exception as e:
        if first:
            store.record(req.source, req.sql, ok=False, rows=None,
                         elapsed_ms=int((time.perf_counter() - t0) * 1000), error=str(e).split("\n")[0][:500])
        raise
    elapsed = int((time.perf_counter() - t0) * 1000)
    if first:
        store.record(req.source, req.sql, ok=True, rows=total if total is not None else page.num_rows,
                     elapsed_ms=elapsed)
    data = [[to_cell(v) for v in page.column(i).to_pylist()] for i in range(page.num_columns)]
    return SqlPage(
        columns=[ExploreColumn(name=f.name, type=duckdb_type(f.type), computed=False) for f in page.schema],
        rows=[list(r) for r in zip(*data, strict=True)],
        offset=req.offset,
        total=total,
        elapsed_ms=elapsed,
    )


@router.get("/history")
def history(store: StoreDep) -> list[HistoryEntry]:
    return store.history()


@router.get("/saved")
def list_saved(store: StoreDep) -> list[SavedQuery]:
    return store.saved()


@router.put("/saved/{name}")
def save(name: SavedName, body: SaveIn, store: StoreDep, registry: RegistryDep) -> SavedQuery:
    registry.get(body.source)  # 404 si la fuente no existe
    return store.save(name, body.source, body.sql)


@router.delete("/saved/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(name: str, store: StoreDep) -> None:
    if not store.delete(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"consulta guardada desconocida: {name!r}")


@jobs.post("/cancel/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_job(query_id: str, registry: RegistryDep) -> None:
    """Cancela una consulta del editor o un perfilado en curso. Idempotente."""
    cancel.check_id(query_id)
    cancel.request(query_id)
    for src in registry.all():
        src.cancel(query_id)
