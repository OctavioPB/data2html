"""Snapshots for `mode: snapshot` reports (per reader, never shared).

The key is the viewer cache key: report and model content, visual, the reader's WHOLE identity,
parameters, cross-filters and computed columns. So a snapshot only ever answers the identity that produced
it, and republishing the report (new content) starts new snapshots. Stored in SQLite under `data/` (shared
by workers, survives restarts); older snapshots of a report are dropped when its content changes.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  key TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created REAL NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_report ON snapshots (report_id, content_hash);
"""


class SnapshotStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def get(self, key: str, max_age_s: float | None) -> tuple[str, str] | None:
        """(data JSON, ISO time it was taken) if there is a fresh enough snapshot."""
        with self._lock:
            row = self._db.execute("SELECT data, created FROM snapshots WHERE key = ?", (key,)).fetchone()
        if row is None or (max_age_s is not None and time.time() - row[1] > max_age_s):
            return None
        return row[0], _iso(row[1])

    def put(self, key: str, report_id: str, content_hash: str, data: str) -> str:
        t = time.time()
        with self._lock:
            # snapshots of an older version of this report can never be asked for again
            self._db.execute("DELETE FROM snapshots WHERE report_id = ? AND content_hash != ?",
                             (report_id, content_hash))
            self._db.execute("INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?)",
                             (key, report_id, content_hash, t, data))
        return _iso(t)


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds")


@lru_cache
def get_snapshots(path: Path) -> SnapshotStore:
    return SnapshotStore(path)
