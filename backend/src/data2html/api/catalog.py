"""Catalog: sources, tables, editable descriptions and computed columns."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from data2html.api.deps import MetaDep, RegistryDep, SettingsDep, SourceDep
from data2html.api.explore import resolve_computed
from data2html.api.schemas import Catalog, CatalogSource, ComputedIn, DescriptionsPatch, TableOut
from data2html.i18n import tr
from data2html.sources.errors import SourceUnavailable
from data2html.sqlgen.explore import ComputedColumn

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("")
def catalog(registry: RegistryDep, meta: MetaDep) -> Catalog:
    """A source that is down does not take the catalog down: it shows up with `status="error"`."""
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
        raise HTTPException(422, detail=tr("unknown columns: {names}", names=sorted(unknown)))
    meta.update(src.id, table, description=body.description, columns=body.columns)
    return TableOut.of(src.table_info(table), meta.get(src.id, table))


@router.put("/{source}/{table}/computed", status_code=status.HTTP_200_OK)
def put_computed(
    table: str, body: ComputedIn, src: SourceDep, meta: MetaDep, settings: SettingsDep
) -> TableOut:
    """Create or replace a computed column. It is validated by running it before it is saved."""
    col = resolve_computed(src, meta, table, ComputedColumn(name=body.name, expr=body.expr),
                           settings.query_timeout_s)
    tm = meta.put_computed(src.id, table, col)
    return TableOut.of(src.table_info(table), tm)


@router.delete("/{source}/{table}/computed/{name}")
def delete_computed(table: str, name: str, src: SourceDep, meta: MetaDep) -> TableOut:
    info = src.table_info(table)
    if name not in {c.name for c in meta.get(src.id, table).computed}:
        detail = tr("unknown computed column: {name}", name=repr(name))
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=detail)
    return TableOut.of(info, meta.drop_computed(src.id, table, name))
