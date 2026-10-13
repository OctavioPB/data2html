"""Live viewer `/r/<id>` (multi-reader). Every response is computed with the reader's identity, which
comes only from `data2html.auth` (security-rls skill; sign-in lives in `api/login.py`). The HTML carries
no data; each visual asks `/api/r/<id>/visuals/<visual>` and gets aggregated rows filtered by RLS.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from data2html import __version__
from data2html.api.deps import RegistryDep, SettingsDep
from data2html.api.reports import ReportsDep
from data2html.api.semantic import StoreDep
from data2html.api.visual_data import VisualData, run_visual
from data2html.auth import IdentityDep, MaybeIdentityDep
from data2html.i18n import get_lang, tr
from data2html.render.cache import TTLCache, cache_key
from data2html.render.export import csv_response
from data2html.render.html import ECHARTS_INTEGRITY, SECURITY_HEADERS, csp, render, safe_json
from data2html.render.snapshots import get_snapshots
from data2html.render.strings import viewer_strings
from data2html.render.theme import load_theme
from data2html.reports.store import ReportNotFound, ReportStore
from data2html.semantic.store import ModelStore
from data2html.settings import Settings
from data2html.sources.base import Identity
from data2html.sources.registry import SourceRegistry
from data2html.spec import (
    FieldType,
    Filter,
    ParamValueError,
    Report,
    SemanticModel,
    allowed_marks,
    coerce_param,
)
from data2html.spec.models import FilterOp, Ident, Mode

pages = APIRouter(tags=["viewer"], include_in_schema=False)
api = APIRouter(prefix="/api/r", tags=["viewer"])

STATIC_DIR = Path(__file__).resolve().parents[1] / "render/static"
static = StaticFiles(directory=STATIC_DIR)

MAX_CROSS_FILTERS = 10
_NOBODY = Identity(user_id="", email="", provider="")  # for hashing the report's content alone
_CROSS_TYPES = (FieldType.nominal, FieldType.ordinal)


@lru_cache
def _cache(settings: Settings) -> TTLCache[VisualData]:
    return TTLCache(settings.viewer_cache_ttl_s, settings.viewer_cache_max_entries)


def can_read(report: Report, identity: Identity) -> bool:
    """`access` empty = any authenticated reader; otherwise at least one shared group."""
    return not report.access or bool(set(report.access) & set(identity.groups))


def _html(body: str, settings: Settings, code: int = 200) -> HTMLResponse:
    headers = {**SECURITY_HEADERS, "Content-Security-Policy": csp(settings.echarts_url)}
    return HTMLResponse(body, status_code=code, headers=headers)


def _message(settings: Settings, code: int, title: str, text: str, *, login: bool = False) -> HTMLResponse:
    body = render("message.html", lang=get_lang(), title=title, text=text,
                  login_url="/login" if login else None, login_label=tr("Sign in"))
    return _html(body, settings, code)


# ------------------------------------------------------------------ pages


@pages.get("/r")
def report_index(
    request: Request, identity: MaybeIdentityDep, reports: ReportsDep, settings: SettingsDep
) -> Response:
    if identity is None:
        return _signin_required(request, settings, "/r")
    items, _ = reports.list()
    readable = [r for r in items if can_read(r, identity)]
    body = render("index.html", lang=get_lang(), reports=readable, user=identity.user_id,
                  title=tr("Reports"), empty=tr("No reports available for you."),
                  signed_in=tr("Signed in as {user}", user=identity.user_id), sign_out=tr("Sign out"))
    return _html(body, settings)


def _signin_required(request: Request, settings: Settings, next_url: str) -> Response:
    if request.method == "GET":
        return RedirectResponse(f"/login?next={next_url}", status_code=status.HTTP_303_SEE_OTHER)
    return _message(settings, 401, tr("Sign in required"), tr("sign in to see this report"), login=True)


def _view(report: Report, model: SemanticModel, identity: Identity, settings: Settings) -> dict[str, object]:
    """What the page needs to draw itself — no rows, no SQL, no RLS details."""
    visuals = []
    for v in report.visuals:
        dim = model.dimensions.get(v.dimension) if v.dimension else None
        visuals.append({
            "id": v.id, "title": v.title, "mark": v.mark.value, "measure": v.measure,
            "dimension": v.dimension, "color": v.color, "layout": v.layout.model_dump(),
            "grain": v.time_grain.value if v.time_grain else None,
            "allowed": [m.value for m in allowed_marks(dim.type if dim else None,
                                                       has_color=v.color is not None)],
            "format": model.measures[v.measure].format.value,
            "crossFilter": dim is not None and dim.type in _CROSS_TYPES and v.time_grain is None,
        })
    return {
        "id": report.id,
        "title": report.title,
        "params": {name: report.param(name).model_dump(mode="json") for name in report.params},
        "visuals": visuals,
        "user": identity.user_id,
        "theme": load_theme(settings.theme_file).model_dump(mode="json"),
        "strings": viewer_strings(),
        "version": __version__,
    }


@pages.get("/r/{report_id}")
def report_page(
    report_id: Ident, request: Request, identity: MaybeIdentityDep, reports: ReportsDep, models: StoreDep,
    settings: SettingsDep,
) -> Response:
    if identity is None:
        return _signin_required(request, settings, f"/r/{report_id}")
    try:
        report = reports.get(report_id)
    except ReportNotFound:
        return _message(settings, 404, tr("Not found"), tr("unknown report: {id}", id=report_id))
    if not can_read(report, identity):
        return _message(settings, 403, tr("No access"), tr("you do not have access to this report"))
    model = models.get(report.semantic_model)
    view = safe_json(_view(report, model, identity, settings))
    body = render("report.html", lang=get_lang(), title=report.title, view=view,
                  echarts_url=settings.echarts_url, echarts_integrity=ECHARTS_INTEGRITY)
    return _html(body, settings)


# ------------------------------------------------------------------ data


def _bad(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=msg)


def parse_query(
    request: Request, report: Report, model: SemanticModel
) -> tuple[dict[str, object], list[tuple[str, str]]]:
    """`p.<name>=value` report parameters (typed, declared only) and `cf=<dimension>:<value>`
    cross-filters (nominal/ordinal dimensions of the model, equality only). Anything else → 422."""
    given: dict[str, str] = {}
    cross: list[tuple[str, str]] = []
    for key, value in request.query_params.multi_items():
        if key.startswith("p."):
            name = key[2:]
            if name not in report.params:
                raise _bad(tr("unknown parameter: {name}", name=name[:64]))
            if name in given:
                raise _bad(tr("repeated parameter: {name}", name=name))
            given[name] = value
        elif key == "cf":
            dim, sep, val = value.partition(":")
            d = model.dimensions.get(dim)
            if not sep or d is None or d.type not in _CROSS_TYPES:
                raise _bad(tr("invalid cross-filter: {value}", value=value[:80]))
            if len(val) > 500:
                raise _bad(tr("invalid cross-filter: {value}", value=value[:80]))
            cross.append((dim, val))
        else:
            raise _bad(tr("unknown query parameter: {name}", name=key[:64]))
    if len(cross) > MAX_CROSS_FILTERS:
        raise _bad(tr("too many cross-filters (max {max})", max=MAX_CROSS_FILTERS))
    params: dict[str, object] = {}
    for name in report.params:
        p = report.param(name)
        raw = given.get(name, p.default)
        if raw is None or raw == "":
            continue  # a filter that needs it fails with "missing value for parameter"
        try:
            params[name] = coerce_param(p.type, raw)
        except ParamValueError as e:
            raise _bad(tr("parameter {name}: {error}", name=name, error=e)) from e
    return params, cross


def _visual_rows(
    report_id: str, visual_id: str, request: Request, identity: Identity, reports: ReportStore,
    models: ModelStore, registry: SourceRegistry, settings: Settings,
) -> VisualData:
    """One visual for one reader: access check, typed parameters, cross-filters, RLS, cache.
    `mode: snapshot`: the reader's data is computed once and kept (per identity) until the report is
    republished or `refresh_hours` pass."""
    report = reports.get(report_id)
    if not can_read(report, identity):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=tr("you do not have access to this report"))
    visual = next((v for v in report.visuals if v.id == visual_id), None)
    if visual is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=tr("unknown visual: {id}", id=visual_id))
    model = models.get(report.semantic_model)
    params, cross = parse_query(request, report, model)

    src = registry.get(model.source)
    computed = registry.computed(src.id, model.table)
    key = cache_key(report=report, model=model, visual_id=visual_id, identity=identity, params=params,
                    cross=cross, computed=computed)
    snapshot = report.mode is Mode.snapshot
    if snapshot:
        store = get_snapshots(settings.snapshots_path)
        max_age = report.refresh_hours * 3600 if report.refresh_hours else None
        kept = store.get(key, max_age)
        if kept is not None:
            return VisualData.model_validate_json(kept[0]).model_copy(update={"as_of": kept[1]})
    else:
        hit = _cache(settings).get(key)
        if hit is not None:
            return hit
    extra = tuple(Filter(dimension=d, op=FilterOp.eq, value=v) for d, v in cross)
    filtered = visual.model_copy(update={"filters": visual.filters + extra})
    data, _sql = run_visual(filtered, model, src, params=params, identity=identity,
                            timeout_s=settings.query_timeout_s,  # never author_preview here
                            computed=computed)
    if snapshot:
        content = cache_key(report=report, model=model, visual_id="", identity=_NOBODY, params={}, cross=[],
                            computed=computed)
        as_of = store.put(key, report.id, content, data.model_dump_json())
        return data.model_copy(update={"as_of": as_of})
    _cache(settings).put(key, data)
    return data


# The CSV route goes first: "x.csv" is not a valid visual id, but the JSON route would match it and 422.
@api.get("/{report_id}/visuals/{visual_id}.csv")
def visual_csv(
    report_id: Ident, visual_id: Ident, request: Request, identity: IdentityDep, reports: ReportsDep,
    models: StoreDep, registry: RegistryDep, settings: SettingsDep,
) -> Response:
    """The same rows the reader sees (RLS, parameters, cross-filters), as a CSV download."""
    data = _visual_rows(report_id, visual_id, request, identity, reports, models, registry, settings)
    return csv_response(f"{report_id}-{visual_id}.csv", [c.name for c in data.columns], data.rows)


@api.get("/{report_id}/visuals/{visual_id}")
def visual_data(
    report_id: Ident, visual_id: Ident, request: Request, response: Response, identity: IdentityDep,
    reports: ReportsDep, models: StoreDep, registry: RegistryDep, settings: SettingsDep,
) -> VisualData:
    # per-reader data: no shared (proxy) cache may keep it
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Cookie"
    return _visual_rows(report_id, visual_id, request, identity, reports, models, registry, settings)
