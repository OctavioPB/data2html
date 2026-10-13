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


class MySQLConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["mysql"]
    host: Annotated[str, Field(pattern=_HOSTNAME)]
    port: Annotated[int, Field(ge=1, le=65535)] = 3306
    database: Annotated[str, Field(pattern=_DB_NAME)]  # the only visible schema
    user: Annotated[str, Field(pattern=_DB_NAME)]
    password_env: Annotated[str, Field(pattern=_ENV_NAME)]
    mode: Literal["directquery"] = "directquery"
    ssl_mode: Literal["disabled", "preferred", "required", "verify_ca", "verify_identity"] = "preferred"


AttachedConfig = PostgresConfig | MySQLConfig

# ------------------------------------------------------------------ DynamoDB (Import from S3 exports)

_COLUMN = r"^[a-z_][a-z0-9_]{0,62}$"
_DDB_PATH = r"^[A-Za-z0-9_\-]{1,255}(\.[A-Za-z0-9_\-]{1,255}){0,9}$"  # attribute, or map.attribute…
_TABLE_ARN = r"^arn:aws[a-z\-]*:dynamodb:[a-z0-9\-]+:\d{12}:table/[A-Za-z0-9_.\-]{3,255}$"
_BUCKET = r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$"
_PREFIX = r"^[A-Za-z0-9!_.*'()/\-]{0,512}$"
_REGION = r"^[a-z]{2}(-[a-z]+)+-\d$"
_DDB_TYPE = r"^(VARCHAR|BIGINT|DOUBLE|BOOLEAN|DATE|TIMESTAMP|JSON|DECIMAL\(\d{1,2},\d{1,2}\))$"


class DynamoColumn(BaseModel):
    """One Parquet column from one item attribute. Lists, sets and maps become JSON text (`type: JSON`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: Annotated[str, Field(pattern=_DDB_PATH)]
    type: Annotated[str, Field(pattern=_DDB_TYPE)] = "VARCHAR"
    unit: Literal["iso", "epoch_s", "epoch_ms"] = "iso"  # how DATE/TIMESTAMP values are stored


class DynamoTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    table_arn: Annotated[str, Field(pattern=_TABLE_ARN)]
    s3_bucket: Annotated[str, Field(pattern=_BUCKET)]
    s3_prefix: Annotated[str, Field(pattern=_PREFIX)] = ""
    columns: Annotated[dict[Annotated[str, Field(pattern=_COLUMN)], DynamoColumn], Field(min_length=1)]
    max_wait_min: Annotated[int, Field(ge=1, le=24 * 60)] = 180  # exports of big tables take a while


class DynamoDBConfig(BaseModel):
    """Import mode: a native DynamoDB export to S3, flattened to Parquet (never a live Scan; ADR 0012).
    AWS credentials come from the standard chain (role, environment, profile), never from this file."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["dynamodb_export"]
    region: Annotated[str, Field(pattern=_REGION)]
    mode: Literal["import"] = "import"
    tables: Annotated[dict[Annotated[str, Field(pattern=_COLUMN)], DynamoTable], Field(min_length=1)]


SourceConfig = Annotated[PostgresConfig | MySQLConfig | DynamoDBConfig, Field(discriminator="type")]


class SourcesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: dict[SourceId, SourceConfig] = Field(default_factory=dict)


def load_sources_file(path: Path | None) -> SourcesFile:
    if path is None or not path.exists():
        return SourcesFile()
    data = SourcesFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    if "csv" in data.sources:
        raise ValueError(tr("'csv' is a reserved id for the uploaded-files source"))
    return data


class SourceRegistry:
    def __init__(self, csv: CsvSource, others: list[DataSource], meta: CatalogMeta | None = None) -> None:
        self.csv = csv
        self._by_id: dict[str, DataSource] = {csv.id: csv} | {s.id: s for s in others}
        self._meta = meta

    def computed(self, source_id: str, table: str) -> dict[str, str]:
        """The explorer's computed columns of a table: name -> SQL expression (validated when saved)."""
        if self._meta is None:
            return {}
        return {c.name: c.expr for c in self._meta.get(source_id, table).computed}

    @classmethod
    def load(cls, settings: Settings, meta: CatalogMeta) -> SourceRegistry:
        from data2html.sources.dynamodb import DynamoDBSource  # avoids an import cycle
        from data2html.sources.mysql import MySQLSource
        from data2html.sources.postgres import PostgresSource

        cfg = load_sources_file(settings.sources_file)
        others: list[DataSource] = []
        for sid, c in cfg.sources.items():
            if isinstance(c, PostgresConfig):
                others.append(PostgresSource(sid, c, settings, meta))
            elif isinstance(c, MySQLConfig):
                others.append(MySQLSource(sid, c, settings, meta))
            else:
                others.append(DynamoDBSource(sid, c, settings, meta))
        return cls(CsvSource(settings, meta), others, meta)

    def get(self, source_id: str) -> DataSource:
        try:
            return self._by_id[source_id]
        except KeyError:
            raise NotFound(tr("unknown source: {name}", name=repr(source_id))) from None

    def all(self) -> list[DataSource]:
        return list(self._by_id.values())
