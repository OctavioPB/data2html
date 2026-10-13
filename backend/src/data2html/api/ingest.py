"""Import sources in the studio (author): DynamoDB export status and "export now" (ADR 0012).

The scheduled path is the CLI (`python -m data2html.ingest`); this lets the author refresh one table on
demand. One export per table at a time (also across processes: the ingest takes a lock file)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from data2html.api.deps import RegistryDep, SettingsDep
from data2html.i18n import tr
from data2html.ingest import dynamodb as ingest_ddb
from data2html.scrub import scrub
from data2html.settings import Settings
from data2html.sources.dynamodb import DynamoDBSource
from data2html.sources.registry import SourceRegistry

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["ingest"])

_jobs: dict[tuple[str, str], str | None] = {}  # (source, table) → None while running, else the last error
_lock = threading.Lock()


class LastExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finished_at: str
    export_time: str
    rows: int
    warnings: dict[str, int]


class TableStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    running: bool
    last: LastExport | None
    error: str | None  # of the last run started from the studio, if it failed


class IngestStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    tables: list[TableStatus]


def _source(registry: SourceRegistry, source: str) -> DynamoDBSource:
    src = registry.get(source)
    if not isinstance(src, DynamoDBSource):
        detail = tr("{source} is not an import source", source=source)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=detail)
    return src


def make_ingest(source: DynamoDBSource, settings: Settings) -> Any:
    """Indirection so tests can supply stubbed AWS clients."""
    return ingest_ddb.DynamoIngest(source.id, source.cfg, settings)


def _status(src: DynamoDBSource) -> IngestStatus:
    tables = []
    for t in src.cfg.tables:
        last = src.last_export(t)
        with _lock:
            running = (src.id, t) in _jobs and _jobs[(src.id, t)] is None
            error = _jobs.get((src.id, t)) or None
        tables.append(TableStatus(
            table=t, running=running, error=error,
            last=LastExport(**{k: last[k] for k in ("finished_at", "export_time", "rows", "warnings")})
            if last else None,
        ))
    return IngestStatus(source=src.id, tables=tables)


@router.get("/{source}")
def ingest_status(source: str, registry: RegistryDep) -> IngestStatus:
    return _status(_source(registry, source))


@router.post("/{source}/{table}", status_code=status.HTTP_202_ACCEPTED)
def start_ingest(source: str, table: str, registry: RegistryDep, settings: SettingsDep) -> IngestStatus:
    src = _source(registry, source)
    if table not in src.cfg.tables:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=tr("unknown table: {name}", name=repr(table)))
    key = (src.id, table)
    with _lock:
        if key in _jobs and _jobs[key] is None:
            detail = tr("an export of this table is already running")
            raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)
        _jobs[key] = None
    try:
        job = make_ingest(src, settings)
    except Exception as e:  # e.g. boto3 not installed
        with _lock:
            _jobs[key] = scrub(str(e))
        detail = tr("exports are not available: {error}", error=e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from None

    def work() -> None:
        error: str | None = ""
        try:
            job.run(table)
        except Exception as e:  # reported in the status; details in the server log
            log.warning("dynamodb export %s.%s failed: %s", src.id, table, e)
            error = scrub(str(e))
        with _lock:
            _jobs[key] = error or ""

    threading.Thread(target=work, name=f"ingest-{src.id}-{table}", daemon=True).start()
    return _status(src)
