"""Catálogo: fuentes, tablas, descripciones editables y columnas calculadas."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from data2html.api.deps import MetaDep, RegistryDep, SettingsDep, SourceDep
from data2html.api.explore import resolve_computed
from data2html.api.schemas import Catalog, CatalogSource, ComputedIn, DescriptionsPatch, TableOut
from data2html.sources.errors import SourceUnavailable
from data2html.sqlgen.explore import ComputedColumn

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("")
def catalog(registry: RegistryDep, meta: MetaDep) -> Catalog:
    """Una fuente caída no tumba el catálogo: aparece con `status="error"`."""
    out = []
    for src in registry.all():
        try:
            tables = [TableOut.of(t, meta.get(src.id, t.name)) for t in src.catalog()]
            out.append(CatalogSource(id=src.id, kind=src.kind, status="ok", tables=tables))
        except SourceUnavailable as e:
            out.append(CatalogSource(id=src.id, kind=src.kind, status="error", error=str(e), tables=[]))
    return Catalog(sources=out)


@router.patch("/{source}/{table}")
def patch_descriptions(table: str, body: DescriptionsPatch, src: SourceDep, meta: MetaDep) -> TableOut:
    info = src.table_info(table)
    known = {c.name for c in info.columns} | {c.name for c in meta.get(src.id, table).computed}
    unknown = set(body.columns or {}) - known
    if unknown:
        raise HTTPException(422, detail=f"columnas desconocidas: {sorted(unknown)}")
    meta.update(src.id, table, description=body.description, columns=body.columns)
    return TableOut.of(src.table_info(table), meta.get(src.id, table))


@router.put("/{source}/{table}/computed", status_code=status.HTTP_200_OK)
def put_computed(
    table: str, body: ComputedIn, src: SourceDep, meta: MetaDep, settings: SettingsDep
) -> TableOut:
    """Crea o reemplaza una columna calculada. Se valida ejecutándola antes de guardarla."""
    col = resolve_computed(src, meta, table, ComputedColumn(name=body.name, expr=body.expr),
                           settings.query_timeout_s)
    tm = meta.put_computed(src.id, table, col)
    return TableOut.of(src.table_info(table), tm)


@router.delete("/{source}/{table}/computed/{name}")
def delete_computed(table: str, name: str, src: SourceDep, meta: MetaDep) -> TableOut:
    info = src.table_info(table)
    if name not in {c.name for c in meta.get(src.id, table).computed}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"columna calculada desconocida: {name!r}")
    return TableOut.of(info, meta.drop_computed(src.id, table, name))
