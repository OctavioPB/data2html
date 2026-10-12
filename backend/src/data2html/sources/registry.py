"""Source registry: CSV (always) + connections declared in `config/sources.yaml`.

The YAML only holds the NAMES of environment variables for secrets. A `password:` field (or any
unknown field) is a validation error, not something to ignore.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from data2html.i18n import tr
from data2html.settings import Settings
from data2html.sources.base import DataSource
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.csv_source import CsvSource
from data2html.sources.errors import NotFound

SourceId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")]
_HOSTNAME = r"^[A-Za-z0-9.\-]{1,253}$"
_DB_NAME = r"^[A-Za-z0-9_\-]{1,63}$"
_ENV_NAME = r"^[A-Z_][A-Z0-9_]{0,63}$"


class PostgresConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["postgres"]
    host: Annotated[str, Field(pattern=_HOSTNAME)]
    port: Annotated[int, Field(ge=1, le=65535)] = 5432
    database: Annotated[str, Field(pattern=_DB_NAME)]
    user: Annotated[str, Field(pattern=_DB_NAME)]
    password_env: Annotated[str, Field(pattern=_ENV_NAME)]
    mode: Literal["directquery"] = "directquery"
    schemas: Annotated[list[Annotated[str, Field(pattern=_DB_NAME)]], Field(min_length=1)] = ["public"]
    connect_timeout_s: Annotated[int, Field(ge=1, le=60)] = 5


class SourcesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: dict[SourceId, PostgresConfig] = Field(default_factory=dict)


def load_sources_file(path: Path | None) -> SourcesFile:
    if path is None or not path.exists():
        return SourcesFile()
    data = SourcesFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    if "csv" in data.sources:
        raise ValueError(tr("'csv' is a reserved id for the uploaded-files source"))
    return data


class SourceRegistry:
    def __init__(self, csv: CsvSource, others: list[DataSource]) -> None:
        self.csv = csv
        self._by_id: dict[str, DataSource] = {csv.id: csv} | {s.id: s for s in others}

    @classmethod
    def load(cls, settings: Settings, meta: CatalogMeta) -> SourceRegistry:
        from data2html.sources.postgres import PostgresSource  # avoids an import cycle

        cfg = load_sources_file(settings.sources_file)
        others: list[DataSource] = [PostgresSource(sid, c, settings, meta) for sid, c in cfg.sources.items()]
        return cls(CsvSource(settings, meta), others)

    def get(self, source_id: str) -> DataSource:
        try:
            return self._by_id[source_id]
        except KeyError:
            raise NotFound(tr("unknown source: {name}", name=repr(source_id))) from None

    def all(self) -> list[DataSource]:
        return list(self._by_id.values())
