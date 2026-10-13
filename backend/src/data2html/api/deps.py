"""Dependencies shared by the routers, and translation of errors into HTTP responses."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import duckdb
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse

from data2html.i18n import tr
from data2html.reports.store import ReportNotFound
from data2html.scrub import register as register_dir
from data2html.scrub import scrub
from data2html.semantic.store import ModelNotFound
from data2html.semantic.suggest import NotPromotable
from data2html.settings import Settings
from data2html.sources.base import DataSource
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import CsvSource
from data2html.sources.errors import (
    Conflict,
    NotFound,
    QueryInterrupted,
    SourceError,
    SourceUnavailable,
    TooLarge,
)
from data2html.sources.registry import SourceRegistry
from data2html.sqlgen.explore import InvalidExplore
from data2html.sqlgen.validate import UnsafeSQL
from data2html.sqlgen.visual import VisualQueryError


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def _meta(settings: Settings) -> CatalogMeta:
    return CatalogMeta(settings.catalog_meta_path)


@lru_cache
def _registry(settings: Settings) -> SourceRegistry:
    register_dir(settings.data_dir, "<data>")
    if settings.content_dir is not None:
        register_dir(settings.content_dir, "<content>")
    return SourceRegistry.load(settings, _meta(settings))


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_meta(settings: SettingsDep) -> CatalogMeta:
    return _meta(settings)


def get_registry(settings: SettingsDep) -> SourceRegistry:
    return _registry(settings)


RegistryDep = Annotated[SourceRegistry, Depends(get_registry)]


def get_source(source: str, registry: RegistryDep) -> DataSource:
    """Resolve the `{source}` path parameter."""
    return registry.get(source)


def get_csv(registry: RegistryDep) -> CsvSource:
    return registry.csv


MetaDep = Annotated[CatalogMeta, Depends(get_meta)]
SourceDep = Annotated[DataSource, Depends(get_source)]
CsvDep = Annotated[CsvSource, Depends(get_csv)]


# ------------------------------------------------------------------ errors → HTTP

_SOURCE_STATUS: list[tuple[type[SourceError], int]] = [
    (NotFound, status.HTTP_404_NOT_FOUND),
    (Conflict, status.HTTP_409_CONFLICT),
    (TooLarge, status.HTTP_413_CONTENT_TOO_LARGE),
    (SourceError, status.HTTP_422_UNPROCESSABLE_CONTENT),
]


def _json(code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": scrub(detail)}, status_code=code)  # no server paths to the browser


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ModelNotFound)
    async def _model(_: Request, e: ModelNotFound) -> JSONResponse:
        return _json(status.HTTP_404_NOT_FOUND, tr("unknown semantic model: {name}", name=e))

    @app.exception_handler(ReportNotFound)
    async def _report(_: Request, e: ReportNotFound) -> JSONResponse:
        return _json(status.HTTP_404_NOT_FOUND, tr("unknown report: {id}", id=e))

    @app.exception_handler(VisualQueryError)
    async def _visual(_: Request, e: VisualQueryError) -> JSONResponse:
        return _json(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    @app.exception_handler(NotPromotable)
    async def _promote(_: Request, e: NotPromotable) -> JSONResponse:
        return _json(status.HTTP_422_UNPROCESSABLE_CONTENT, tr("cannot be promoted: {reason}", reason=e))

    @app.exception_handler(SourceError)
    async def _source(_: Request, e: SourceError) -> JSONResponse:
        return _json(next(c for cls, c in _SOURCE_STATUS if isinstance(e, cls)), str(e))

    @app.exception_handler(InvalidExplore)
    async def _explore(_: Request, e: InvalidExplore) -> JSONResponse:
        return _json(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    @app.exception_handler(UnsafeSQL)
    async def _unsafe(_: Request, e: UnsafeSQL) -> JSONResponse:
        return _json(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    @app.exception_handler(SourceUnavailable)
    async def _unavailable(_: Request, e: SourceUnavailable) -> JSONResponse:
        return _json(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    @app.exception_handler(QueryInterrupted)
    async def _interrupted(_: Request, e: QueryInterrupted) -> JSONResponse:
        return _json(status.HTTP_504_GATEWAY_TIMEOUT, str(e))

    @app.exception_handler(duckdb.Error)
    async def _duckdb(_: Request, e: duckdb.Error) -> JSONResponse:
        # Binder/conversion errors caused by the user's query: first line only
        return _json(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e).split("\n")[0])
