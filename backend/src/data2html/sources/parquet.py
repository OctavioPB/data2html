"""Sources whose tables are Parquet files in one directory (CSV uploads, DynamoDB exports).

Queries run in a DuckDB that can only read that directory (no network, no other files), with one view
per table so the SQL names tables plainly (`FROM ventas`).
"""

from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path

import duckdb
import pyarrow as pa

from data2html.i18n import tr
from data2html.settings import Settings
from data2html.sources.base import ColumnInfo, Identity, TableInfo
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.engine import new_duckdb, sql_ident, sql_literal
from data2html.sources.errors import Deadline, NotFound, SourceError
from data2html.sqlgen.validate import ensure_single_select

TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ParquetSource:
    kind: str
    dialect = "duckdb"

    def __init__(self, source_id: str, directory: Path, settings: Settings, meta: CatalogMeta) -> None:
        self.id = source_id
        self._dir = directory
        self._s = settings
        self._meta = meta
        self._running: dict[str, duckdb.DuckDBPyConnection] = {}
        self._lock = threading.Lock()
        directory.mkdir(parents=True, exist_ok=True)

    def _conn(self, *dirs: Path) -> duckdb.DuckDBPyConnection:
        return new_duckdb(
            allowed_dirs=dirs, memory_limit=self._s.duckdb_memory_limit, threads=self._s.duckdb_threads
        )

    def _parquet(self, table: str) -> Path:
        if not TABLE_RE.match(table):
            raise SourceError(tr("invalid table name: {name}", name=repr(table)))
        return self._dir / f"{table}.parquet"

    def tables(self) -> list[str]:
        return sorted(p.stem for p in self._dir.glob("*.parquet") if TABLE_RE.match(p.stem))

    # -- DataSource --------------------------------------------------------------

    def table_info(self, table: str) -> TableInfo:
        parquet = self._parquet(table)
        if not parquet.exists():
            raise NotFound(tr("unknown table: {name}", name=repr(table)))
        meta = self._meta.get(self.id, table)
        conn = self._conn(self._dir)
        try:
            cols = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(parquet)]).fetchall()
            (count,) = conn.execute("SELECT count(*) FROM read_parquet(?)", [str(parquet)]).fetchone() or (0,)
        finally:
            conn.close()
        return TableInfo(
            name=table,
            columns=tuple(ColumnInfo(n, t, meta.columns.get(n, "")) for n, t, *_ in cols),
            row_count=int(count),
            description=meta.description,
        )

    def catalog(self) -> list[TableInfo]:
        return [self.table_info(t) for t in self.tables()]

    def relation(self, name: str) -> tuple[str, ...]:
        self._parquet(name)  # validates the name
        return (name,)  # execute() creates one view per table

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
        conn = self._conn(self._dir)
        for t in self.tables():  # CREATE VIEW takes no parameters; t already passed TABLE_RE
            path = sql_literal(str(self._parquet(t)))
            conn.execute(f"CREATE VIEW {sql_ident(t)} AS SELECT * FROM read_parquet({path})")  # noqa: S608
        with self._lock:
            self._running[qid] = conn
        deadline = Deadline(timeout_s, conn.interrupt)
        try:
            with deadline:
                return conn.execute(sql, params or None).to_arrow_table()
        except duckdb.InterruptException as e:
            raise deadline.interrupted() from e
        finally:
            with self._lock:
                self._running.pop(qid, None)
            conn.close()

    def cancel(self, query_id: str) -> None:
        with self._lock:
            conn = self._running.get(query_id)
        if conn is not None:
            conn.interrupt()
