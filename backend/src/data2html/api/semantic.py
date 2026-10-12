"""Modelos semánticos y constructor de visuales (studio, autor único)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import sqlglot
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from data2html.api.deps import RegistryDep, SettingsDep
from data2html.api.explore import to_cell
from data2html.api.schemas import Cell, ExploreColumn
from data2html.api.sql import duckdb_type
from data2html.semantic.check import check_model
from data2html.semantic.store import ModelStore
from data2html.semantic.suggest import Suggestion, suggest_from_sql
from data2html.settings import Settings
from data2html.sources.errors import SourceError, SourceUnavailable
from data2html.spec import (
    Filter,
    Layout,
    Mark,
    Report,
    SemanticModel,
    TimeGrain,
    Visual,
    allowed_marks,
    validate_report,
)
from data2html.spec.models import Ident, Scalar
from data2html.sqlgen.visual import build_visual_query

router = APIRouter(prefix="/api/semantic", tags=["semantic"])
visuals = APIRouter(prefix="/api/visual", tags=["visual"])


@lru_cache
def _store(settings: Settings) -> ModelStore:
    return ModelStore(settings.semantic_dir)


def get_store(settings: SettingsDep) -> ModelStore:
    return _store(settings)


StoreDep = Annotated[ModelStore, Depends(get_store)]


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: SemanticModel
    errors: list[str]


class ModelList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: list[ModelEntry]
    broken: dict[str, str]  # archivos YAML que no validan → error


class SuggestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    sql: Annotated[str, Field(min_length=1, max_length=100_000)]


class VisualDraft(BaseModel):
    """Lo que arma el constructor: un Visual sin id/título/layout (eso llega con los reportes, Fase 6)."""

    model_config = ConfigDict(extra="forbid")
    mark: Mark
    measure: Ident
    dimension: Ident | None = None
    time_grain: TimeGrain | None = None
    color: Ident | None = None
    filters: list[Filter] = Field(default_factory=list)


class VisualRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Ident
    visual: VisualDraft
    params: dict[Ident, Scalar] = Field(default_factory=dict)


class VisualResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[ExploreColumn]
    rows: list[list[Cell]]
    sql: str  # SQL generado, para transparencia del autor
    allowed_marks: list[Mark]


def _check(model: SemanticModel, registry: RegistryDep, *, full: bool, timeout_s: int) -> list[str]:
    try:
        src = registry.get(model.source)
    except SourceError:
        return [f"fuente desconocida: '{model.source}'"]
    try:
        return check_model(model, src, run_measures=full, timeout_s=timeout_s)
    except SourceUnavailable as e:
        return [f"no se pudo validar contra la fuente: {e}"]


@router.get("")
def list_models(store: StoreDep, registry: RegistryDep, settings: SettingsDep) -> ModelList:
    models, broken = store.list()
    entries = [ModelEntry(model=m, errors=_check(m, registry, full=False, timeout_s=settings.query_timeout_s))
               for m in models]
    return ModelList(models=entries, broken=broken)


@router.get("/{name}")
def get_model(name: Ident, store: StoreDep, registry: RegistryDep, settings: SettingsDep) -> ModelEntry:
    model = store.get(name)
    errors = _check(model, registry, full=True, timeout_s=settings.query_timeout_s)
    return ModelEntry(model=model, errors=errors)


@router.post("/check")
def check(model: SemanticModel, registry: RegistryDep, settings: SettingsDep) -> list[str]:
    """Valida sin guardar (editor en vivo): forma + catálogo + cada medida ejecutada con WHERE false."""
    return _check(model, registry, full=True, timeout_s=settings.query_timeout_s)


@router.put("/{name}")
def put_model(
    name: Ident, model: SemanticModel, store: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> ModelEntry:
    if model.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="el nombre del modelo no coincide")
    errors = _check(model, registry, full=True, timeout_s=settings.query_timeout_s)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(errors))
    store.put(model)
    return ModelEntry(model=model, errors=[])


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(name: Ident, store: StoreDep) -> None:
    store.delete(name)


@router.post("/suggest")
def suggest(body: SuggestIn, registry: RegistryDep, store: StoreDep) -> Suggestion:
    """Consulta del editor SQL → medida (+ dimensión) propuesta para el modelo de esa tabla."""
    src = registry.get(body.source)
    tables = {t.name: {c.name: c.type for c in t.columns} for t in src.catalog()}
    models, _ = store.list()
    return suggest_from_sql(body.sql, source=src.id, tables=tables, models=models)


@visuals.post("/query")
def visual_query(
    req: VisualRequest, store: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> VisualResult:
    model = store.get(req.model)
    src = registry.get(model.source)
    visual = Visual(id="borrador", title="", layout=Layout(x=0, y=0, w=12, h=4),
                    **req.visual.model_dump(exclude_none=True))
    report = Report(id="borrador", title="", semantic_model=model.name,
                    params={k: type(v).__name__ for k, v in req.params.items()}, visuals=(visual,))
    errors = validate_report(report, model)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(errors))

    info = src.table_info(model.table)
    q = build_visual_query(
        visual, model, src.relation(model.table),
        column_types={c.name: c.type for c in info.columns},
        report_params=dict(req.params),
        # vista previa del autor en el studio; el visor (Fase 6) pasa la identidad del lector
        identity=None, author_preview=True,
    )
    table = src.execute(q.sql, q.params, identity=None, timeout_s=settings.query_timeout_s)
    data = [[to_cell(v) for v in table.column(i).to_pylist()] for i in range(table.num_columns)]
    dim = model.dimensions.get(visual.dimension) if visual.dimension else None
    return VisualResult(
        columns=[ExploreColumn(name=f.name, type=duckdb_type(f.type), computed=False) for f in table.schema],
        rows=[list(r) for r in zip(*data, strict=True)],
        sql=sqlglot.transpile(q.sql, read="duckdb", write="duckdb", pretty=True)[0],
        allowed_marks=allowed_marks(dim.type if dim else None, has_color=visual.color is not None),
    )
