"""DynamoDB source (Import, ADR 0012): Parquet files produced by `data2html.ingest.dynamodb` from native
table exports to S3. Queries never touch AWS: they read `data/dynamodb/<source>/<table>.parquet` in a
sandboxed DuckDB, like CSV uploads. A configured table that has not been exported yet is not listed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data2html.settings import Settings
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.parquet import ParquetSource
from data2html.sources.registry import DynamoDBConfig


def export_dir(settings: Settings, source_id: str) -> Path:
    return settings.data_dir / "dynamodb" / source_id


class DynamoDBSource(ParquetSource):
    kind = "dynamodb"

    def __init__(self, source_id: str, cfg: DynamoDBConfig, settings: Settings, meta: CatalogMeta) -> None:
        super().__init__(source_id, export_dir(settings, source_id), settings, meta)
        self.cfg = cfg

    def tables(self) -> list[str]:
        return sorted(t for t in self.cfg.tables if self._parquet(t).exists())

    def last_export(self, table: str) -> dict[str, Any] | None:
        """Metadata written by the last successful ingest (`<table>.export.json`), if any."""
        f = self._dir / f"{table}.export.json"
        if table not in self.cfg.tables or not f.exists():
            return None
        data: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        return data
