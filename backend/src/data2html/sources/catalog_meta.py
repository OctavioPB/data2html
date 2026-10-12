"""Metadatos editables del catálogo (descripciones y columnas calculadas), aparte de los datos."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from data2html.sqlgen.explore import ComputedColumn


class TableMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(default="", max_length=2000)
    columns: dict[str, str] = Field(default_factory=dict)
    computed: list[ComputedColumn] = Field(default_factory=list)


class _MetaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: dict[str, dict[str, TableMeta]] = Field(default_factory=dict)


class CatalogMeta:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _load(self) -> _MetaFile:
        if not self._path.exists():
            return _MetaFile()
        return _MetaFile.model_validate_json(self._path.read_text(encoding="utf-8"))

    def _modify(self, source: str, table: str, change: Callable[[TableMeta], None]) -> TableMeta:
        with self._lock:
            data = self._load()
            meta = data.sources.setdefault(source, {}).setdefault(table, TableMeta())
            change(meta)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path)
            return meta

    def get(self, source: str, table: str) -> TableMeta:
        return self._load().sources.get(source, {}).get(table, TableMeta())

    def update(
        self,
        source: str,
        table: str,
        *,
        description: str | None = None,
        columns: dict[str, str] | None = None,
    ) -> TableMeta:
        def change(meta: TableMeta) -> None:
            if description is not None:
                meta.description = description
            for col, desc in (columns or {}).items():
                if desc:
                    meta.columns[col] = desc
                else:
                    meta.columns.pop(col, None)

        return self._modify(source, table, change)

    def put_computed(self, source: str, table: str, col: ComputedColumn) -> TableMeta:
        """Agrega o reemplaza (por nombre) una columna calculada ya validada."""

        def change(meta: TableMeta) -> None:
            meta.computed = [c for c in meta.computed if c.name != col.name] + [col]

        return self._modify(source, table, change)

    def drop_computed(self, source: str, table: str, name: str) -> TableMeta:
        def change(meta: TableMeta) -> None:
            meta.computed = [c for c in meta.computed if c.name != name]
            meta.columns.pop(name, None)

        return self._modify(source, table, change)
