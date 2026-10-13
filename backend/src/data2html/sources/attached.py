"""Sources that DuckDB attaches READ_ONLY through an extension (Postgres, MySQL).

One long-lived DuckDB connection per source: `LOAD <extension>` -> temporary secret with the password
from the environment -> `ATTACH ... (READ_ONLY)` -> sandbox locked. Every query uses its own `cursor()`.
Filters and projections travel to the source; DuckDB resolves the rest.

Defense in depth: SELECT-only database user, READ_ONLY attach, locked sandbox (no other database can
be attached) and `ensure_single_select`, which rejects `postgres_*`/`mysql_*` escape hatches (ADR 0007).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid

import duckdb
import pyarrow as pa

from data2html.i18n import tr
from data2html.settings import Settings
from data2html.sources.base import ColumnInfo, Identity, TableInfo
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.engine import new_duckdb, sql_ident, sql_literal
from data2html.sources.errors import Deadline, NotFound, SourceUnavailable
from data2html.sources.registry import AttachedConfig
from data2html.sqlgen.validate import ensure_single_select

log = logging.getLogger(__name__)
_RETRY_AFTER_S = 30


class _Failure(Exception):
    """Connection failure kept as (message, params) so it is localized each time it is raised: the
    cached error is reused for other requests, possibly in another language."""

    def __init__(self, msgid: str, **params: object) -> None:
        super().__init__(msgid)
        self.msgid = msgid
        self.params = params


class AttachedSource:
    """Base of the sources DuckDB attaches (READ_ONLY). Subclasses declare the extension, the secret,
    the ATTACH target and the visible schemas."""

    kind: str
    extension: str
    dialect = "duckdb"  # the SQL runs in DuckDB over the attached database
    # True when the source compares text ignoring case/accents (e.g. MySQL's default collation) and DuckDB
    # pushes filters down to it: sqlgen then re-checks the RLS predicate exactly in DuckDB.
    loose_collation = False

    def __init__(self, source_id: str, cfg: AttachedConfig, settings: Settings, meta: CatalogMeta) -> None:
        self.id = source_id
        self._cfg = cfg
        self._s = settings
        self._meta = meta
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.Lock()
        self._running: dict[str, duckdb.DuckDBPyConnection] = {}
        self._failed_at = 0.0
        self._last_error = _Failure("could not connect to source {source}", source=repr(source_id))

    def __repr__(self) -> str:  # no secrets, no connection string
        c = self._cfg
        return f"{type(self).__name__}(id={self.id!r}, host={c.host!r}, database={c.database!r})"

    # -- what each source declares ---------------------------------------------------

    def _secret_options(self, password: str) -> str:
        """Body of `CREATE TEMPORARY SECRET … (TYPE <extension>, …)`, from validated config values."""
        raise NotImplementedError

    def _attach_target(self) -> str:
        raise NotImplementedError

    @property
    def schemas(self) -> list[str]:
        raise NotImplementedError

    # -- connection -----------------------------------------------------------------

    def _setup(self, conn: duckdb.DuckDBPyConnection) -> None:
        password = os.environ.get(self._cfg.password_env)
        if password is None:
            raise _Failure("missing environment variable {name}", name=self._cfg.password_env)
        ext = self.extension
        try:
            conn.execute(f"LOAD {ext}")
        except duckdb.Error:
            conn.execute(f"INSTALL {ext}")  # first time on this machine
            conn.execute(f"LOAD {ext}")
        secret = sql_ident(f"{self.id}_secret")
        # CREATE SECRET takes no parameters; the values come from the validated config and the environment.
        # An error here may quote the statement (with the password): the original message is dropped.
        try:
            conn.execute(f"CREATE TEMPORARY SECRET {secret} (TYPE {ext}, {self._secret_options(password)})")
        except duckdb.Error:
            raise _Failure("could not create the secret for source {source}", source=repr(self.id)) from None
        conn.execute(
            f"ATTACH {sql_literal(self._attach_target())} AS {sql_ident(self.id)} "
            f"(TYPE {ext}, SECRET {secret}, READ_ONLY)"
        )

    def _connection(self) -> duckdb.DuckDBPyConnection:
        with self._lock:
            if self._conn is not None:
                return self._conn
            if time.monotonic() - self._failed_at < _RETRY_AFTER_S:
                raise SourceUnavailable(tr(self._last_error.msgid, **self._last_error.params))
            try:
                self._conn = new_duckdb(
                    allowed_dirs=[], memory_limit=self._s.duckdb_memory_limit,
                    threads=self._s.duckdb_threads, setup=self._setup,
                )
            except (duckdb.Error, _Failure) as e:
                # DuckDB's detail includes host/user (never the password: it lives in the secret);
                # it is logged on the server and the client only gets a generic message.
                log.warning("source %s: could not connect: %s", self.id, e)
                self._failed_at = time.monotonic()
                generic = _Failure("could not connect to source {source}", source=repr(self.id))
                self._last_error = e if isinstance(e, _Failure) else generic
                raise SourceUnavailable(tr(self._last_error.msgid, **self._last_error.params)) from None
            return self._conn

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        conn = self._connection()
        with self._lock:
            return conn.cursor()

    def refresh(self) -> None:
        """Forget the cached schema: the next request reconnects and attaches again."""
        self.close()
        self._failed_at = 0.0  # and retry at once, even if the last attempt failed

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- catalog --------------------------------------------------------------------

    def catalog(self) -> list[TableInfo]:
        cur = self._cursor()
        try:
            rows = cur.execute(
                """SELECT schema_name, table_name, column_name, data_type
                   FROM duckdb_columns()
                   WHERE database_name = ? AND list_contains(?, schema_name)
                   ORDER BY schema_name, table_name, column_index""",
                [self.id, self.schemas],
            ).fetchall()
        except duckdb.IOException as e:
            raise self._lost(e) from None
        finally:
            cur.close()
        tables: dict[str, list[tuple[str, str]]] = {}
        for schema, table, col, type_ in rows:
            tables.setdefault(f"{schema}.{table}", []).append((col, type_))
        return [self._info(name, cols) for name, cols in tables.items()]

    def _info(self, name: str, cols: list[tuple[str, str]]) -> TableInfo:
        meta = self._meta.get(self.id, name)
        return TableInfo(
            name=name,
            columns=tuple(ColumnInfo(c, t, meta.columns.get(c, "")) for c, t in cols),
            row_count=None,  # counting remotely is expensive
            description=meta.description,
        )

    def table_info(self, name: str) -> TableInfo:
        for t in self.catalog():
            if t.name == name:
                return t
        raise NotFound(tr("unknown table: {name}", name=repr(name)))

    def relation(self, name: str) -> tuple[str, ...]:
        schema, sep, table = name.partition(".")
        if not sep or schema not in self.schemas or not table:
            raise NotFound(tr("unknown table: {name}", name=repr(name)))
        return (self.id, schema, table)

    # -- queries --------------------------------------------------------------------

    def execute(
        self,
        sql: str,
        params: dict[str, object],
        *,
        identity: Identity | None,
        timeout_s: int,
        query_id: str | None = None,
    ) -> pa.Table:
        ensure_single_select(sql, self.dialect)
        qid = query_id or uuid.uuid4().hex
        cur = self._cursor()
        with self._lock:
            self._running[qid] = cur
        deadline = Deadline(timeout_s, cur.interrupt)
        try:
            with deadline:
                return cur.execute(sql, params or None).to_arrow_table()
        except duckdb.InterruptException as e:
            raise deadline.interrupted() from e
        except duckdb.IOException as e:
            raise self._lost(e) from None
        finally:
            with self._lock:
                self._running.pop(qid, None)
            cur.close()

    def cancel(self, query_id: str) -> None:
        with self._lock:
            cur = self._running.get(query_id)
        if cur is not None:
            cur.interrupt()

    def _lost(self, e: duckdb.Error) -> SourceUnavailable:
        log.warning("source %s: connection error: %s", self.id, e)
        self.close()  # the next request reconnects
        return SourceUnavailable(tr("lost the connection to source {source}", source=repr(self.id)))
