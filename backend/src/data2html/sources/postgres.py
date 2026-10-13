"""Postgres source (DirectQuery) through DuckDB's `postgres` extension (see `attached.py`)."""

from __future__ import annotations

from data2html.sources.attached import AttachedSource
from data2html.sources.engine import sql_literal
from data2html.sources.registry import PostgresConfig


class PostgresSource(AttachedSource):
    kind = "postgres"
    extension = "postgres"
    _cfg: PostgresConfig

    def _secret_options(self, password: str) -> str:
        c = self._cfg
        return (f"HOST {sql_literal(c.host)}, PORT {c.port}, DATABASE {sql_literal(c.database)}, "
                f"USER {sql_literal(c.user)}, PASSWORD {sql_literal(password)}")

    def _attach_target(self) -> str:
        return f"connect_timeout={self._cfg.connect_timeout_s}"

    @property
    def schemas(self) -> list[str]:
        return list(self._cfg.schemas)
