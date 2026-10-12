"""Catálogo: tablas, descripciones editables y columnas calculadas."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from data2html.api.deps import CsvDep, MetaDep, SettingsDep, check_source, http_error
from data2html.api.explore import resolve_computed
from data2html.api.schemas import Catalog, CatalogSource, ComputedIn, DescriptionsPatch, TableOut
from data2html.sources.csv_source import CsvError
from data2html.sqlgen.explore import ComputedColumn, InvalidExplore

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("")
def catalog(csv: CsvDep, meta: MetaDep) -> Catalog:
    tables = [TableOut.of(t, meta.get(csv.id, t.name)) for t in csv.catalog()]
    return Catalog(sources=[CatalogSource(id=csv.id, kind="csv", tables=tables)])


@router.patch("/{source}/{table}")
def patch_descriptions(
    source: str, table: str, body: DescriptionsPatch, csv: CsvDep, meta: MetaDep
) -> TableOut:
    check_source(source, csv)
    try:
        info = csv.table_info(table)
    except CsvError as e:
        raise http_error(e) from e
    known = {c.name for c in info.columns} | {c.name for c in meta.get(source, table).computed}
    unknown = set(body.columns or {}) - known
    if unknown:
        raise HTTPException(422, detail=f"columnas desconocidas: {sorted(unknown)}")
    meta.update(source, table, description=body.description, columns=body.columns)
    return TableOut.of(csv.table_info(table), meta.get(source, table))


@router.put("/{source}/{table}/computed", status_code=status.HTTP_200_OK)
def put_computed(
    source: str, table: str, body: ComputedIn, csv: CsvDep, meta: MetaDep, settings: SettingsDep
) -> TableOut:
    """Crea o reemplaza una columna calculada. Se valida ejecutándola antes de guardarla."""
    check_source(source, csv)
    try:
        col = resolve_computed(csv, meta, table, ComputedColumn(name=body.name, expr=body.expr),
                               settings.query_timeout_s)
        tm = meta.put_computed(source, table, col)
        return TableOut.of(csv.table_info(table), tm)
    except CsvError as e:
        raise http_error(e) from e
    except InvalidExplore as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e


@router.delete("/{source}/{table}/computed/{name}")
def delete_computed(source: str, table: str, name: str, csv: CsvDep, meta: MetaDep) -> TableOut:
    check_source(source, csv)
    try:
        info = csv.table_info(table)
    except CsvError as e:
        raise http_error(e) from e
    if name not in {c.name for c in meta.get(source, table).computed}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"columna calculada desconocida: {name!r}")
    return TableOut.of(info, meta.drop_computed(source, table, name))
