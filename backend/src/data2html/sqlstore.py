"""Historial y consultas guardadas del editor SQL (studio monousuario), en `data/`."""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MAX_HISTORY = 100
SQL_MAX = 100_000
SavedName = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^/\\\x00-\x1f]+$")]


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    at: str
    source: str
    sql: Annotated[str, Field(max_length=SQL_MAX)]
    ok: bool
    rows: int | None = None
    elapsed_ms: int
    error: str | None = None


class SavedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: SavedName
    source: str
    sql: Annotated[str, Field(min_length=1, max_length=SQL_MAX)]
    updated_at: str


class _History(BaseModel):
    entries: list[HistoryEntry] = Field(default_factory=list)


class _Saved(BaseModel):
    queries: dict[str, SavedQuery] = Field(default_factory=dict)


class SqlStore:
    def __init__(self, data_dir: Path) -> None:
        self._history = data_dir / "sql_history.json"
        self._saved = data_dir / "sql_saved.json"
        self._lock = threading.Lock()

    @staticmethod
    def _write(path: Path, model: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(model.model_dump(), indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def history(self) -> list[HistoryEntry]:
        if not self._history.exists():
            return []
        return _History.model_validate_json(self._history.read_text(encoding="utf-8")).entries

    def record(self, source: str, sql: str, *, ok: bool, rows: int | None, elapsed_ms: int,
               error: str | None = None) -> None:
        entry = HistoryEntry(at=_now(), source=source, sql=sql[:SQL_MAX], ok=ok, rows=rows,
                             elapsed_ms=elapsed_ms, error=error)
        with self._lock:
            entries = [entry, *self.history()][:MAX_HISTORY]
            self._write(self._history, _History(entries=entries))

    def saved(self) -> list[SavedQuery]:
        if not self._saved.exists():
            return []
        data = _Saved.model_validate_json(self._saved.read_text(encoding="utf-8"))
        return sorted(data.queries.values(), key=lambda q: q.name.lower())

    def save(self, name: str, source: str, sql: str) -> SavedQuery:
        q = SavedQuery(name=name, source=source, sql=sql, updated_at=_now())
        with self._lock:
            data = _Saved(queries={s.name: s for s in self.saved()})
            data.queries[name] = q
            self._write(self._saved, data)
        return q

    def delete(self, name: str) -> bool:
        with self._lock:
            data = _Saved(queries={s.name: s for s in self.saved()})
            if data.queries.pop(name, None) is None:
                return False
            self._write(self._saved, data)
            return True
