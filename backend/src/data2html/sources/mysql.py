"""MySQL source (DirectQuery) through DuckDB's `mysql` extension (see `attached.py`; ADR 0011).

The MySQL database is the only visible schema (`<database>.<table>`); `information_schema` is hidden.
MySQL's default collations ignore case and accents, and DuckDB pushes filters down to MySQL without
re-checking them. So this source sets `loose_collation`: sqlgen re-checks the RLS predicate exactly in
DuckDB (a reader in group "sur" must not see the rows of "Sur").
"""

from __future__ import annotations

from data2html.sources.attached import AttachedSource
from data2html.sources.engine import sql_literal
from data2html.sources.registry import MySQLConfig


class MySQLSource(AttachedSource):
    kind = "mysql"
    extension = "mysql"
    loose_collation = True
    _cfg: MySQLConfig

    def _secret_options(self, password: str) -> str:
        c = self._cfg
        return (f"HOST {sql_literal(c.host)}, PORT {c.port}, DATABASE {sql_literal(c.database)}, "
                f"USER {sql_literal(c.user)}, PASSWORD {sql_literal(password)}, "
                f"SSL_MODE {sql_literal(c.ssl_mode)}")

    def _attach_target(self) -> str:
        return ""  # everything comes from the secret

    @property
    def schemas(self) -> list[str]:
        return [self._cfg.database]
