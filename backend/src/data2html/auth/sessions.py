"""Server-side sessions in SQLite (`data/sessions.sqlite`), shared by every worker process.

The cookie holds a random session id (signed, see `session.py`); the database only stores its SHA-256,
so a copy of the database cannot be replayed as cookies. Logging out deletes the row: the session is
revoked everywhere at once. Pending OIDC logins (state, nonce, PKCE verifier) live here too, for 10 min,
and the failed sign-ins of the throttle (keys hashed: no user names or addresses at rest).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from functools import lru_cache
from pathlib import Path

from data2html.sources.base import Identity

PENDING_TTL_S = 600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id_hash TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  identity TEXT NOT NULL,
  created REAL NOT NULL,
  expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_failures (
  key TEXT NOT NULL,
  at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS login_failures_key ON login_failures (key, at);
CREATE TABLE IF NOT EXISTS pending_logins (
  state_hash TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  expires REAL NOT NULL
);
"""


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class SessionStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def create(self, identity: Identity, ttl_s: int, *, now: float | None = None) -> str:
        t = now if now is not None else time.time()
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._db.execute("DELETE FROM sessions WHERE expires < ?", (t,))
            self._db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (_h(sid), identity.provider, json.dumps(dataclasses.asdict(identity)), t, t + ttl_s),
            )
        return sid

    def get(self, sid: str, *, now: float | None = None) -> Identity | None:
        with self._lock:
            row = self._db.execute(
                "SELECT identity, expires FROM sessions WHERE id_hash = ?", (_h(sid),)
            ).fetchone()
        if row is None or row[1] < (now if now is not None else time.time()):
            return None
        data = json.loads(row[0])
        data["groups"] = tuple(data.get("groups") or ())
        return Identity(**data)

    def delete(self, sid: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM sessions WHERE id_hash = ?", (_h(sid),))

    def put_pending(self, data: dict[str, str]) -> str:
        """Store a pending OIDC login and return its `state` (random, single use)."""
        state = secrets.token_urlsafe(32)
        t = time.time()
        with self._lock:
            self._db.execute("DELETE FROM pending_logins WHERE expires < ?", (t,))
            self._db.execute("INSERT INTO pending_logins VALUES (?, ?, ?)",
                             (_h(state), json.dumps(data), t + PENDING_TTL_S))
        return state

    def pop_pending(self, state: str) -> dict[str, str] | None:
        with self._lock:
            row = self._db.execute(
                "DELETE FROM pending_logins WHERE state_hash = ? RETURNING data, expires", (_h(state),)
            ).fetchone()
        if row is None or row[1] < time.time():
            return None
        data: dict[str, str] = json.loads(row[0])
        return data

    # -- sign-in throttle (shared by all workers) -------------------------------------

    def failures(self, keys: tuple[str, ...], window_s: float) -> int:
        """Most recent failed sign-ins for any of `keys` within the window."""
        since = time.time() - window_s
        with self._lock:
            rows = [self._db.execute("SELECT count(*) FROM login_failures WHERE key = ? AND at >= ?",
                                     (_h(k), since)).fetchone()[0] for k in keys]
        return max(rows, default=0)

    def record_failure(self, keys: tuple[str, ...], window_s: float) -> None:
        t = time.time()
        with self._lock:
            self._db.execute("DELETE FROM login_failures WHERE at < ?", (t - window_s,))
            self._db.executemany("INSERT INTO login_failures VALUES (?, ?)", [(_h(k), t) for k in keys])

    def clear_failures(self, keys: tuple[str, ...]) -> None:
        with self._lock:
            self._db.executemany("DELETE FROM login_failures WHERE key = ?", [(_h(k),) for k in keys])


@lru_cache
def get_store(path: Path) -> SessionStore:
    return SessionStore(path)
