"""Personal access tokens (ADR 0014): what the local MCP server sends as `Authorization: Bearer`.

A token is `d2h_` + 256 random bits, shown once; the database (`data/sessions.sqlite`, table `tokens`)
only stores its SHA-256 next to the identity it was created for. Expiry is mandatory. Tokens are
accepted only by the read-only agent API (`/api/agent/*`), never by the studio or the viewer.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from data2html.sources.base import Identity

PREFIX = "d2h_"
DEFAULT_DAYS = 30
MAX_DAYS = 90
MAX_PER_USER = 20
NAME_MAX = 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
  id TEXT PRIMARY KEY,
  secret_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  provider TEXT NOT NULL,
  user_id TEXT NOT NULL,
  identity TEXT NOT NULL,
  created REAL NOT NULL,
  expires REAL NOT NULL,
  last_used REAL
);
CREATE INDEX IF NOT EXISTS tokens_owner ON tokens (provider, user_id);
"""


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class TokenInfo:
    """What a listing shows: never the secret."""

    id: str
    name: str
    created: float
    expires: float
    last_used: float | None


class TooManyTokens(ValueError):
    pass


class TokenStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def create(
        self, identity: Identity, name: str, days: int, *, now: float | None = None
    ) -> tuple[str, str]:
        """New token for `identity`: returns (id, secret). The secret is not kept."""
        if not 1 <= days <= MAX_DAYS:
            raise ValueError(f"days must be between 1 and {MAX_DAYS}")
        t = now if now is not None else time.time()
        token_id = secrets.token_hex(4)
        secret = PREFIX + secrets.token_urlsafe(32)
        with self._lock:
            self._db.execute("DELETE FROM tokens WHERE expires < ?", (t,))
            (count,) = self._db.execute("SELECT count(*) FROM tokens WHERE provider = ? AND user_id = ?",
                                        (identity.provider, identity.user_id)).fetchone()
            if count >= MAX_PER_USER:
                raise TooManyTokens
            self._db.execute(
                "INSERT INTO tokens VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (token_id, _h(secret), name.strip()[:NAME_MAX] or token_id, identity.provider,
                 identity.user_id, json.dumps(dataclasses.asdict(identity)), t, t + days * 86400),
            )
        return token_id, secret

    def get(self, secret: str, *, now: float | None = None) -> Identity | None:
        """The identity the token was created for (as stored), or None if unknown or expired."""
        if not secret.startswith(PREFIX) or len(secret) > 200:
            return None
        t = now if now is not None else time.time()
        with self._lock:
            row = self._db.execute("SELECT id, identity, expires FROM tokens WHERE secret_hash = ?",
                                   (_h(secret),)).fetchone()
            if row is None or row[2] < t:
                return None
            self._db.execute("UPDATE tokens SET last_used = ? WHERE id = ?", (t, row[0]))
        data = json.loads(row[1])
        data["groups"] = tuple(data.get("groups") or ())
        return Identity(**data)

    def list(self, provider: str, user_id: str) -> list[TokenInfo]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, name, created, expires, last_used FROM tokens WHERE provider = ? AND user_id = ? "
                "AND expires >= ? ORDER BY created DESC", (provider, user_id, time.time()),
            ).fetchall()
        return [TokenInfo(*r) for r in rows]

    def revoke(self, token_id: str, *, provider: str | None = None, user_id: str | None = None) -> bool:
        """Delete a token. With `provider`/`user_id`, only if it belongs to them (the /tokens page);
        without them, any token (the administrator's CLI)."""
        sql, args = "DELETE FROM tokens WHERE id = ?", [token_id]
        if provider is not None or user_id is not None:
            sql += " AND provider = ? AND user_id = ?"
            args += [provider or "", user_id or ""]
        with self._lock:
            return self._db.execute(sql, args).rowcount > 0


@lru_cache
def get_tokens(path: Path) -> TokenStore:
    return TokenStore(path)
