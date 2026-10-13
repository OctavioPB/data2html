"""Reports in the studio (single author). Saving publishes: the viewer serves `content/reports/`."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from data2html.api.deps import RegistryDep, SettingsDep
from data2html.api.semantic import StoreDep, model_errors
from data2html.i18n import tr
from data2html.reports.store import ReportStore
from data2html.semantic.store import ModelNotFound, ModelStore
from data2html.settings import Settings
from data2html.sources.registry import SourceRegistry
from data2html.spec import Report, validate_report
from data2html.spec.models import Ident

router = APIRouter(prefix="/api/reports", tags=["reports"])


@lru_cache
def _reports(settings: Settings) -> ReportStore:
    return ReportStore(settings.reports_dir)


def get_reports(settings: SettingsDep) -> ReportStore:
    return _reports(settings)


ReportsDep = Annotated[ReportStore, Depends(get_reports)]


class ReportEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report: Report
    errors: list[str]


class ReportList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reports: list[ReportEntry]
    broken: dict[str, str]  # YAML files that do not validate → error


def report_errors(
    report: Report, models: ModelStore, registry: SourceRegistry, *, full: bool, timeout_s: int
) -> list[str]:
    """Report against its model, and the model against its source."""
    try:
        model = models.get(report.semantic_model)
    except ModelNotFound:
        return [tr("unknown semantic model: {name}", name=report.semantic_model)]
    return validate_report(report, model) + model_errors(model, registry, full=full, timeout_s=timeout_s)


@router.get("")
def list_reports(
    reports: ReportsDep, models: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> ReportList:
    items, broken = reports.list()
    t = settings.query_timeout_s
    return ReportList(
        reports=[ReportEntry(report=r, errors=report_errors(r, models, registry, full=False, timeout_s=t))
                 for r in items],
        broken=broken,
    )


@router.get("/{report_id}")
def get_report(
    report_id: Ident, reports: ReportsDep, models: StoreDep, registry: RegistryDep, settings: SettingsDep
) -> ReportEntry:
    report = reports.get(report_id)
    errors = report_errors(report, models, registry, full=False, timeout_s=settings.query_timeout_s)
    return ReportEntry(report=report, errors=errors)


@router.put("/{report_id}")
def put_report(
    report_id: Ident, report: Report, reports: ReportsDep, models: StoreDep, registry: RegistryDep,
    settings: SettingsDep,
) -> ReportEntry:
    """Validate and publish. A report that does not validate is never written."""
    if report.id != report_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=tr("the report id does not match"))
    errors = report_errors(report, models, registry, full=True, timeout_s=settings.query_timeout_s)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(errors))
    reports.put(report)
    return ReportEntry(report=report, errors=[])


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: Ident, reports: ReportsDep) -> None:
    reports.delete(report_id)
