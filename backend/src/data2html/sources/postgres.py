"""Fuente Postgres (DirectQuery) vía la extensión `postgres` de DuckDB.

Una conexión DuckDB por fuente, de larga vida: `LOAD postgres` → secreto temporal con la contraseña
del entorno → `ATTACH … (READ_ONLY)` → sandbox cerrado. Cada consulta usa su propio `cursor()`.
Los filtros y proyecciones viajan a Postgres; el resto lo resuelve DuckDB.

Defensa en capas: usuario de BD con solo SELECT, ATTACH READ_ONLY, sandbox cerrado (no se puede
adjuntar otra base) y `ensure_single_select`, que rechaza `postgres_scan/query/execute`.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid

import duckdb
import pyarrow as pa

from data2html.settings import Settings
from data2html.sources.base import ColumnInfo, Identity, TableInfo
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.engine import new_duckdb, sql_ident, sql_literal
from data2html.sources.errors import NotFound, QueryInterrupted, SourceUnavailable
from data2html.sources.registry import PostgresConfig
from data2html.sqlgen.validate import ensure_single_select

log = logging.getLogger(__name__)
_RETRY_AFTER_S = 30


class PostgresSource:
    kind = "postgres"
    dialect = "duckdb"  # el SQL corre en DuckDB sobre la base adjunta

    def __init__(self, source_id: str, cfg: PostgresConfig, settings: Settings, meta: CatalogMeta) -> None:
        self.id = source_id
        self._cfg = cfg
        self._s = settings
        self._meta = meta
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.Lock()
        self._running: dict[str, duckdb.DuckDBPyConnection] = {}
        self._failed_at = 0.0
        self._last_error = ""

    def __repr__(self) -> str:  # sin secretos ni cadena de conexión
        return f"PostgresSource(id={self.id!r}, host={self._cfg.host!r}, database={self._cfg.database!r})"

    # -- conexión -------------------------------------------------------------------

    def _setup(self, conn: duckdb.DuckDBPyConnection) -> None:
        password = os.environ.get(self._cfg.password_env)
        if password is None:
            raise SourceUnavailable(f"falta la variable de entorno {self._cfg.password_env}")
        try:
            conn.execute("LOAD postgres")
        except duckdb.Error:
            conn.execute("INSTALL postgres")  # primera vez en esta máquina
            conn.execute("LOAD postgres")
        c = self._cfg
        secret = sql_ident(f"{self.id}_secret")
        # CREATE SECRET no acepta parámetros; los valores vienen de la config validada y del entorno.
        # Un error aquí puede citar la sentencia (con la contraseña): se descarta el mensaje original.
        try:
            conn.execute(
                f"CREATE TEMPORARY SECRET {secret} (TYPE postgres, HOST {sql_literal(c.host)}, "
                f"PORT {c.port}, DATABASE {sql_literal(c.database)}, USER {sql_literal(c.user)}, "
                f"PASSWORD {sql_literal(password)})"
            )
        except duckdb.Error:
            raise SourceUnavailable(f"no se pudo crear el secreto de la fuente {self.id!r}") from None
        conn.execute(
            f"ATTACH {sql_literal(f'connect_timeout={c.connect_timeout_s}')} AS {sql_ident(self.id)} "
            f"(TYPE postgres, SECRET {secret}, READ_ONLY)"
        )

    def _connection(self) -> duckdb.DuckDBPyConnection:
        with self._lock:
            if self._conn is not None:
                return self._conn
            if time.monotonic() - self._failed_at < _RETRY_AFTER_S:
                raise SourceUnavailable(self._last_error)
            try:
                self._conn = new_duckdb(
                    allowed_dirs=[], memory_limit=self._s.duckdb_memory_limit,
                    threads=self._s.duckdb_threads, setup=self._setup,
                )
            except (duckdb.Error, SourceUnavailable) as e:
                # El detalle de DuckDB incluye host/usuario (nunca la contraseña: va en el secreto);
                # se registra en el servidor y al cliente solo llega un mensaje genérico.
                log.warning("fuente %s: no se pudo conectar: %s", self.id, e)
                self._failed_at = time.monotonic()
                self._last_error = (str(e) if isinstance(e, SourceUnavailable)
                                    else f"no se pudo conectar a la fuente {self.id!r}")
                raise SourceUnavailable(self._last_error) from None
            return self._conn

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        conn = self._connection()
        with self._lock:
            return conn.cursor()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- catálogo -------------------------------------------------------------------

    def catalog(self) -> list[TableInfo]:
        cur = self._cursor()
        try:
            rows = cur.execute(
                """SELECT schema_name, table_name, column_name, data_type
                   FROM duckdb_columns()
                   WHERE database_name = ? AND list_contains(?, schema_name)
                   ORDER BY schema_name, table_name, column_index""",
                [self.id, list(self._cfg.schemas)],
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
            row_count=None,  # contar en remoto es caro
            description=meta.description,
        )

    def table_info(self, name: str) -> TableInfo:
        for t in self.catalog():
            if t.name == name:
                return t
        raise NotFound(f"tabla desconocida: {name!r}")

    def relation(self, name: str) -> tuple[str, ...]:
        schema, sep, table = name.partition(".")
        if not sep or schema not in self._cfg.schemas or not table:
            raise NotFound(f"tabla desconocida: {name!r}")
        return (self.id, schema, table)

    # -- consultas ------------------------------------------------------------------

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
        timer = threading.Timer(timeout_s, cur.interrupt)
        with self._lock:
            self._running[qid] = cur
        timer.start()
        try:
            return cur.execute(sql, params or None).to_arrow_table()
        except duckdb.InterruptException as e:
            raise QueryInterrupted(f"consulta cancelada o con más de {timeout_s}s") from e
        except duckdb.IOException as e:
            raise self._lost(e) from None
        finally:
            timer.cancel()
            with self._lock:
                self._running.pop(qid, None)
            cur.close()

    def cancel(self, query_id: str) -> None:
        with self._lock:
            cur = self._running.get(query_id)
        if cur is not None:
            cur.interrupt()

    def _lost(self, e: duckdb.Error) -> SourceUnavailable:
        log.warning("fuente %s: error de conexión: %s", self.id, e)
        self.close()  # la próxima petición reconecta
        return SourceUnavailable(f"se perdió la conexión con la fuente {self.id!r}")
