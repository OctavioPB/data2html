"""Read-only agent API (`/api/agent/*`, ADR 0014): what the local MCP server calls for Claude.

Authentication: a personal access token (`Authorization: Bearer`), and nothing else; these routes do
not accept the session cookie, and no other route accepts the token. Every result is computed with the
token's identity and its RLS (never `author_preview`, not even for the author). What each source shows
is capped by `config/ai.yaml`: `none` hides it, `metadata` shows names and descriptions, `results` also
returns aggregated rows. Every call is logged without values.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from data2html.ai.config import AiConfig, Exposure, load_ai_config
from data2html.api.deps import MetaDep, RegistryDep, SettingsDep
from data2html.api.profile import get_profile
from data2html.api.reports import ReportsDep
from data2html.api.schemas import CatalogSource, Cell, ExploreColumn, TableOut
from data2html.api.semantic import StoreDep
from data2html.api.viewer import _visual_rows, can_read
from data2html.api.visual_data import run_visual
from data2html.auth import TokenIdentityDep
from data2html.i18n import tr
from data2html.profiling.models import TableProfile
from data2html.reports.store import ReportStore
from data2html.scrub import scrub
from data2html.semantic.store import ModelStore
from data2html.sources.base import Identity
from data2html.sources.errors import SourceUnavailable
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
from data2html.spec.models import FilterOp, Ident, Scalar

log = logging.getLogger("data2html.agent")
router = APIRouter(prefix="/api/agent", tags=["agent"], include_in_schema=False)

MAX_FILTERS = 10


def get_ai(settings: SettingsDep) -> AiConfig:
    return load_ai_config(settings.ai_file)


AiDep = Annotated[AiConfig, Depends(get_ai)]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WhoAmI(_Out):
    user_id: str
    author: bool


class AgentField(_Out):
    name: str
    type: str
    description: str


class AgentMeasure(_Out):
    name: str
    format: str
    description: str


class AgentModel(_Out):
    name: str
    source: str
    exposure: Exposure
    dimensions: list[AgentField]
    measures: list[AgentMeasure]


class AgentParam(_Out):
    name: str
    type: str
    default: Scalar | None
    label: str


class AgentVisual(_Out):
    id: str
    title: str
    mark: str
    measure: str
    dimension: str | None


class AgentReport(_Out):
    id: str
    title: str
    semantic_model: str
    exposure: Exposure
    params: list[AgentParam]
    visuals: list[AgentVisual]


class AgentFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: Ident
    op: FilterOp
    value: Scalar | list[Scalar]


class AgentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Ident
    measure: Ident
    dimension: Ident | None = None
    color: Ident | None = None
    time_grain: TimeGrain | None = None
    filters: list[AgentFilter] = Field(default_factory=list, max_length=MAX_FILTERS)
    limit: int | None = Field(default=None, ge=1)


class AgentResult(_Out):
    columns: list[ExploreColumn]
    rows: list[list[Cell]]
    truncated: bool
    as_of: str | None = None


def _audit(identity: Identity, action: str, target: str, rows: int | None = None) -> None:
    log.info("agent action=%s user=%s provider=%s target=%s rows=%s",
             action, identity.user_id, identity.provider, target, rows)


def _visible_models(identity: Identity, models: ModelStore, reports: ReportStore,
                    ai: AiConfig) -> dict[str, SemanticModel]:
    """The author sees every model; a reader, the models of the reports they can read. Sources with
    exposure `none` do not exist for the AI."""
    items, _ = models.list()
    if not identity.author:
        readable = {r.semantic_model for r in reports.list()[0] if can_read(r, identity)}
        items = [m for m in items if m.name in readable]
    return {m.name: m for m in items if ai.exposure(m.source) is not Exposure.none}


def _not_found_model(name: str) -> HTTPException:
    # same answer for "does not exist" and "not yours": no enumeration
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=tr("unknown semantic model: {name}", name=name))


def _require_results(ai: AiConfig, source: str) -> None:
    if ai.exposure(source) is not Exposure.results:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail=tr("source {source} does not share results with the AI", source=source))


def _require_author(identity: Identity) -> None:
    if not identity.author:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=tr("only the author can use this tool"))


def _cap(rows: list[list[Cell]], limit: int | None, ai: AiConfig) -> tuple[list[list[Cell]], bool]:
    n = min(limit or ai.max_rows, ai.max_rows)
    return rows[:n], len(rows) > n


@router.get("/whoami")
def whoami(identity: TokenIdentityDep) -> WhoAmI:
    return WhoAmI(user_id=identity.user_id, author=identity.author)


@router.get("/models")
def list_models(
    identity: TokenIdentityDep, models: StoreDep, reports: ReportsDep, ai: AiDep
) -> list[AgentModel]:
    """Dimensions and measures (names, types, descriptions). No SQL, tables or RLS rules."""
    visible = _visible_models(identity, models, reports, ai)
    _audit(identity, "models", "*", len(visible))
    return [
        AgentModel(
            name=m.name, source=m.source, exposure=ai.exposure(m.source),
            dimensions=[AgentField(name=k, type=d.type.value, description=d.description)
                        for k, d in m.dimensions.items()],
            measures=[AgentMeasure(name=k, format=x.format.value, description=x.description)
                      for k, x in m.measures.items()],
        )
        for m in visible.values()
    ]


@router.post("/query")
def query(
    body: AgentQuery, identity: TokenIdentityDep, models: StoreDep, reports: ReportsDep,
    registry: RegistryDep, settings: SettingsDep, ai: AiDep,
) -> AgentResult:
    """One measure by (optionally) one dimension and a colour, with filters: aggregated rows, built by
    sqlgen like any visual and run with the token's identity (RLS)."""
    model = _visible_models(identity, models, reports, ai).get(body.model)
    if model is None:
        raise _not_found_model(body.model)
    _require_results(ai, model.source)
    dim = model.dimensions.get(body.dimension) if body.dimension else None
    allowed = allowed_marks(dim.type if dim else None, has_color=body.color is not None)
    try:
        filters = tuple(Filter(dimension=f.dimension, op=f.op,
                               value=tuple(f.value) if isinstance(f.value, list) else f.value)
                        for f in body.filters)
        visual = Visual(id="agent", title="", mark=Mark.table if Mark.table in allowed else allowed[0],
                        measure=body.measure, dimension=body.dimension, color=body.color,
                        time_grain=body.time_grain, filters=filters, layout=Layout(x=0, y=0, w=12, h=4))
    except ValidationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="; ".join(str(err["msg"]) for err in e.errors())) from e
    draft = Report(id="agent", title="", semantic_model=model.name, visuals=(visual,))
    errors = validate_report(draft, model)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(errors))
    src = registry.get(model.source)
    computed = registry.computed(src.id, model.table)
    data, _sql = run_visual(visual, model, src, params={}, identity=identity,  # never author_preview
                            timeout_s=settings.query_timeout_s, computed=computed)
    rows, truncated = _cap(data.rows, body.limit, ai)
    _audit(identity, "query", f"{model.name}.{body.measure}", len(rows))
    return AgentResult(columns=data.columns, rows=rows, truncated=truncated)


@router.get("/reports")
def list_reports(
    identity: TokenIdentityDep, models: StoreDep, reports: ReportsDep, ai: AiDep
) -> list[AgentReport]:
    """The reports this person can open at /r, with their parameters and visuals."""
    by_name = {m.name: m for m in models.list()[0]}
    out = []
    for r in reports.list()[0]:
        model = by_name.get(r.semantic_model)
        if model is None or not can_read(r, identity) or ai.exposure(model.source) is Exposure.none:
            continue
        params = [AgentParam(name=n, type=r.param(n).type.value, default=r.param(n).default,
                             label=r.param(n).label) for n in r.params]
        visuals = [AgentVisual(id=v.id, title=v.title, mark=v.mark.value, measure=v.measure,
                               dimension=v.dimension) for v in r.visuals]
        out.append(AgentReport(id=r.id, title=r.title, semantic_model=r.semantic_model,
                               exposure=ai.exposure(model.source), params=params, visuals=visuals))
    _audit(identity, "reports", "*", len(out))
    return out


@router.get("/reports/{report_id}/visuals/{visual_id}")
def report_visual(
    report_id: Ident, visual_id: Ident, request: Request, identity: TokenIdentityDep, reports: ReportsDep,
    models: StoreDep, registry: RegistryDep, settings: SettingsDep, ai: AiDep,
) -> AgentResult:
    """Exactly what this person sees in that visual at /r/<id> (`p.<param>=value`, `cf=dim:value`)."""
    report = reports.get(report_id)
    model = models.get(report.semantic_model)
    if ai.exposure(model.source) is Exposure.none or not can_read(report, identity):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=tr("unknown report: {id}", id=report_id))
    _require_results(ai, model.source)
    data = _visual_rows(report_id, visual_id, request, identity, reports, models, registry, settings)
    rows, truncated = _cap(data.rows, None, ai)
    _audit(identity, "report_visual", f"{report_id}.{visual_id}", len(rows))
    return AgentResult(columns=data.columns, rows=rows, truncated=truncated, as_of=data.as_of)


@router.get("/tables")
def tables(
    identity: TokenIdentityDep, registry: RegistryDep, meta: MetaDep, ai: AiDep
) -> list[CatalogSource]:
    """Author only: the catalog of every source the AI may see (names, types, descriptions)."""
    _require_author(identity)
    out = []
    for src in registry.all():
        if ai.exposure(src.id) is Exposure.none:
            continue
        try:
            items = [TableOut.of(t, meta.get(src.id, t.name)) for t in src.catalog()]
            out.append(CatalogSource(id=src.id, kind=src.kind, status="ok", tables=items))
        except SourceUnavailable as e:
            out.append(CatalogSource(id=src.id, kind=src.kind, status="error", error=scrub(str(e)),
                                     tables=[]))
    _audit(identity, "tables", "*", len(out))
    return out


@router.get("/profile/{source}/{table}")
def profile(
    source: Ident, table: str, identity: TokenIdentityDep, registry: RegistryDep, meta: MetaDep,
    settings: SettingsDep, ai: AiDep,
) -> TableProfile:
    """Author only: the EDA profile (sampled on remote sources). Needs `results` exposure."""
    _require_author(identity)
    _require_results(ai, source)
    result = get_profile(table=table, src=registry.get(source), meta=meta, settings=settings)
    _audit(identity, "profile", f"{source}.{table}", result.rows)
    return result

