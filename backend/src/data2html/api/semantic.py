"""Semantic models and the visual builder (studio, single author)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import sqlglot
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from data2html.api.deps import RegistryDep, SettingsDep
from data2html.api.visual_data import VisualData, run_visual
from data2html.i18n import tr
from data2html.render.export import csv_response
from data2html.semantic.check import check_model
from data2html.semantic.store import ModelStore
from data2html.semantic.suggest import Suggestion, suggest_from_sql
from data2html.settings import Settings
from data2html.sources.errors import SourceError, SourceUnavailable
from data2html.sources.registry import SourceRegistry
from data2html.spec import (
    Filter,
    Layout,
    Mark,
    ParamType,
    ParamValueError,
    Report,
    SemanticModel,
    TimeGrain,
    Visual,
    coerce_param,
    validate_report,
)
from data2html.spec.models import Ident, Scalar

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
    broken: dict[str, str]  # YAML files that do not validate → error


class SuggestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    sql: Annotated[str, Field(min_length=1, max_length=100_000)]


class VisualDraft(BaseModel):
    """What the builder assembles: a Visual without id/title/layout (those come with reports, Phase 6)."""

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
    # declared types (the report editor sends them); otherwise inferred from the values
    param_types: dict[Ident, ParamType] = Field(default_factory=dict)


class VisualResult(VisualData):
    sql: str  # generated SQL, for the author's transparency


def model_errors(model: SemanticModel, registry: SourceRegistry, *, full: bool, timeout_s: int) -> list[str]:
    try:
        src = registry.get(model.source)
    except SourceError:
        return [tr("unknown source: {name}", name=repr(model.source))]
    try:
        return check_model(model, src, run_measures=full, timeout_s=timeout_s,
                           computed=registry.computed(src.id, model.table))
    except SourceUnavailable as e:
        return [tr("could not validate against the source: {error}", error=e)]


@router.get("")
def list_models(store: StoreDep, registry: RegistryDep, settings: SettingsDep) -> ModelList:
    models, broken = store.list()
    timeout = settings.query_timeout_s
    entries = [ModelEntry(model=m, errors=model_errors(m, registry, full=False, timeout_s=timeout))
               for m in models]
    return ModelList(models=entries, broken=broken)


@router.get("/{name}")
def get_model(name: Ident, store: StoreDep, registry: RegistryDep, settings: SettingsDep) -> ModelEntry:
    model = store.get(name)
    errors = model_errors(model, registry, full=True, timeout_s=settings.query_timeout_s)
    return ModelEntry(model=model, errors=errors)


@router.post("/check")
def check(model: SemanticModel, registry: RegistryDep, settings: SettingsDep) -> list[str]:
    """Validate without saving (live editor): shape + catalog + every measure run with WHERE false."""
    return model_errors(model, registry, full=True, timeout_s=settings.query_timeout_s)


@router.put("/{name}")
def put_model(
    name: Ident, model: SemanticModel, store: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> ModelEntry:
    if model.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=tr("the model name does not match"))
    errors = model_errors(model, registry, full=True, timeout_s=settings.query_timeout_s)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(errors))
    store.put(model)
    return ModelEntry(model=model, errors=[])


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(name: Ident, store: StoreDep) -> None:
    store.delete(name)


@router.post("/suggest")
def suggest(body: SuggestIn, registry: RegistryDep, store: StoreDep) -> Suggestion:
    """SQL editor query → proposed measure (+ dimension) for that table's model."""
    src = registry.get(body.source)
    tables = {t.name: {c.name: c.type for c in t.columns} for t in src.catalog()}
    models, _ = store.list()
    return suggest_from_sql(body.sql, source=src.id, tables=tables, models=models)


def _author_visual(
    req: VisualRequest, store: ModelStore, registry: SourceRegistry, settings: Settings
) -> tuple[VisualData, str]:
    model = store.get(req.model)
    src = registry.get(model.source)
    visual = Visual(id="draft", title="", layout=Layout(x=0, y=0, w=12, h=4),
                    **req.visual.model_dump(exclude_none=True))
    types = {k: req.param_types.get(k) or _infer_param_type(v) for k, v in req.params.items()}
    report = Report(id="draft", title="", semantic_model=model.name, params=dict(types), visuals=(visual,))
    errors = validate_report(report, model)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(errors))
    params: dict[str, object] = {k: coerce_param(t, req.params[k]) for k, t in types.items()}
    # the author's preview in the studio; the viewer passes the reader's identity instead
    return run_visual(visual, model, src, params=params, identity=None, author_preview=True,
                      timeout_s=settings.query_timeout_s, computed=registry.computed(src.id, model.table))


@visuals.post("/query")
def visual_query(
    req: VisualRequest, store: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> VisualResult:
    data, sql = _author_visual(req, store, registry, settings)
    return VisualResult(**data.model_dump(),
                        sql=sqlglot.transpile(sql, read="duckdb", write="duckdb", pretty=True)[0])


@visuals.post("/export.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def visual_export_csv(
    req: VisualRequest, store: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> Response:
    """The builder's/editor's visual as a CSV download (aggregated rows, as previewed by the author)."""
    data, _ = _author_visual(req, store, registry, settings)
    name = f"{req.model}-{req.visual.measure}" + (f"-{req.visual.dimension}" if req.visual.dimension else "")
    return csv_response(f"{name}.csv", [c.name for c in data.columns], data.rows)


def _infer_param_type(v: Scalar) -> ParamType:
    if isinstance(v, bool):
        return ParamType.bool
    if isinstance(v, int):
        return ParamType.int
    if isinstance(v, float):
        return ParamType.float
    try:
        coerce_param(ParamType.date, v)
        return ParamType.date
    except ParamValueError:
        return ParamType.str
