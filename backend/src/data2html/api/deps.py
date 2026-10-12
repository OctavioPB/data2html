"""Dependencias compartidas por los routers."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status

from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import Conflict, CsvError, CsvSource, NotFound, TooLarge


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def _meta(settings: Settings) -> CatalogMeta:
    return CatalogMeta(settings.catalog_meta_path)


@lru_cache
def _csv(settings: Settings) -> CsvSource:
    return CsvSource(settings, _meta(settings))


def get_meta(settings: Annotated[Settings, Depends(get_settings)]) -> CatalogMeta:
    return _meta(settings)


def get_csv(settings: Annotated[Settings, Depends(get_settings)]) -> CsvSource:
    return _csv(settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]
CsvDep = Annotated[CsvSource, Depends(get_csv)]
MetaDep = Annotated[CatalogMeta, Depends(get_meta)]

_STATUS: list[tuple[type[CsvError], int]] = [
    (NotFound, status.HTTP_404_NOT_FOUND),
    (Conflict, status.HTTP_409_CONFLICT),
    (TooLarge, status.HTTP_413_CONTENT_TOO_LARGE),
    (CsvError, status.HTTP_422_UNPROCESSABLE_CONTENT),
]


def http_error(e: CsvError) -> HTTPException:
    code = next(c for cls, c in _STATUS if isinstance(e, cls))
    return HTTPException(code, detail=str(e))


def check_source(source: str, csv: CsvSource) -> None:
    if source != csv.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"fuente desconocida: {source!r}")
