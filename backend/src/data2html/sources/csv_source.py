"""Fuente CSV (modo Import): subida → revisión de tipos por el autor → Parquet en `data/csv/`.

Flujo: `stage()` guarda el archivo subido, `preview()` sugiere tipos y avisa de trampas
(ceros a la izquierda, coma decimal, fechas ambiguas, encabezados repetidos, codificación),
`confirm()` convierte con los tipos que el autor revisó y guarda `<tabla>.schema.json` al lado.
"""

from __future__ import annotations

import codecs
import csv
import io
import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

import duckdb
import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, model_validator

from data2html.settings import Settings
from data2html.sources.base import ColumnInfo, Identity, TableInfo
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.engine import new_duckdb, sql_ident, sql_literal
from data2html.sources.errors import Conflict, NotFound, QueryInterrupted, SourceError, TooLarge
from data2html.sqlgen.validate import ensure_single_select

TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SAMPLE_ROWS = 10_000
PREVIEW_ROWS = 20


# ------------------------------------------------------------------ contrato de la API


class CsvType(StrEnum):
    VARCHAR = "VARCHAR"
    BIGINT = "BIGINT"
    DOUBLE = "DOUBLE"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"


class DateFormat(StrEnum):
    iso = "%Y-%m-%d"
    dmy_slash = "%d/%m/%Y"
    mdy_slash = "%m/%d/%Y"
    dmy_dash = "%d-%m-%Y"
    mdy_dash = "%m-%d-%Y"


class ColumnChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: CsvType
    date_format: DateFormat | None = None
    decimal_comma: bool = False

    @model_validator(mode="after")
    def _options_match_type(self) -> ColumnChoice:
        if self.date_format and self.type not in (CsvType.DATE, CsvType.TIMESTAMP):
            raise ValueError(f"{self.name}: date_format solo aplica a DATE/TIMESTAMP")
        if self.decimal_comma and self.type is not CsvType.DOUBLE:
            raise ValueError(f"{self.name}: decimal_comma solo aplica a DOUBLE")
        return self


class ColumnGuess(ColumnChoice):
    warnings: list[str] = Field(default_factory=list)


class CsvPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    filename: str
    suggested_table: str
    encoding: str
    delimiter: str
    columns: list[ColumnGuess]
    warnings: list[str]
    rows: list[list[str | None]]


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str = Field(pattern=_UPLOAD_ID_RE.pattern)
    table: str = Field(pattern=TABLE_RE.pattern)
    columns: list[ColumnChoice]


# ------------------------------------------------------------------ inferencia (pura, testeable)

_INT = re.compile(r"^[+-]?\d+$")
_DEC_DOT = re.compile(r"^[+-]?(\d+\.\d*|\.\d+)$")
_DEC_COMMA = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+),\d+$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$")
_DMY = re.compile(r"^(\d{1,2})([/-])(\d{1,2})\2(\d{4})$")
_BOOL = {"true", "false"}


def _has_leading_zero(v: str) -> bool:
    digits = v.lstrip("+-")
    return len(digits) > 1 and digits.startswith("0")


def guess_column(name: str, values: list[str | None]) -> ColumnGuess:
    vals = [v.strip() for v in values if v is not None and v.strip()]
    if not vals:
        return ColumnGuess(name=name, type=CsvType.VARCHAR, warnings=["columna vacía en la muestra"])

    if all(v.lower() in _BOOL for v in vals):
        return ColumnGuess(name=name, type=CsvType.BOOLEAN)

    if all(_INT.match(v) for v in vals):
        zeros = next((v for v in vals if _has_leading_zero(v)), None)
        if zeros is not None:
            return ColumnGuess(name=name, type=CsvType.VARCHAR, warnings=[
                f"ceros a la izquierda ('{zeros}'): se deja como texto para no perderlos",
            ])
        if any(len(v.lstrip("+-")) > 18 for v in vals):
            return ColumnGuess(name=name, type=CsvType.VARCHAR, warnings=["entero demasiado largo: texto"])
        return ColumnGuess(name=name, type=CsvType.BIGINT)

    if all(_INT.match(v) or _DEC_DOT.match(v) for v in vals):
        return ColumnGuess(name=name, type=CsvType.DOUBLE)

    if all(_INT.match(v) or _DEC_COMMA.match(v) for v in vals):
        sample = next(v for v in vals if "," in v)
        return ColumnGuess(name=name, type=CsvType.DOUBLE, decimal_comma=True, warnings=[
            f"coma decimal detectada ('{sample}'); el punto se toma como separador de miles",
        ])

    if all(_ISO_DATE.match(v) for v in vals):
        return ColumnGuess(name=name, type=CsvType.DATE, date_format=DateFormat.iso)

    if all(_ISO_TS.match(v) or _ISO_DATE.match(v) for v in vals):
        return ColumnGuess(name=name, type=CsvType.TIMESTAMP)

    matches = [_DMY.match(v) for v in vals]
    if all(matches):
        firsts = [int(m.group(1)) for m in matches if m]
        seconds = [int(m.group(3)) for m in matches if m]
        sep = matches[0].group(2) if matches[0] else "/"
        day_first = {"/": DateFormat.dmy_slash, "-": DateFormat.dmy_dash}[sep]
        month_first = {"/": DateFormat.mdy_slash, "-": DateFormat.mdy_dash}[sep]
        if any(f > 12 for f in firsts) and any(s > 12 for s in seconds):
            return ColumnGuess(name=name, type=CsvType.VARCHAR, warnings=["fechas con orden inconsistente"])
        if any(f > 12 for f in firsts):
            return ColumnGuess(name=name, type=CsvType.DATE, date_format=day_first)
        if any(s > 12 for s in seconds):
            return ColumnGuess(name=name, type=CsvType.DATE, date_format=month_first)
        return ColumnGuess(name=name, type=CsvType.DATE, date_format=day_first, warnings=[
            f"fecha ambigua ('{vals[0]}'): se asume día/mes; cámbialo si es mes/día",
        ])

    return ColumnGuess(name=name, type=CsvType.VARCHAR)


def suggest_table_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_") or "tabla"
    if slug[0].isdigit():
        slug = "t_" + slug
    return slug[:63]


def cast_expr(choice: ColumnChoice) -> str:
    col = sql_ident(choice.name)
    if choice.type is CsvType.VARCHAR:
        return f"NULLIF({col}, '') AS {col}"
    v = f"NULLIF(trim({col}), '')"
    if choice.decimal_comma:
        v = f"replace(replace({v}, '.', ''), ',', '.')"
    if choice.date_format:  # de una lista cerrada (DateFormat): seguro como literal
        v = f"strptime({v}, {sql_literal(choice.date_format.value)})"
    return f"CAST({v} AS {choice.type.value}) AS {col}"


def _detect_encoding(path: Path) -> str:
    decoder = codecs.getincrementaldecoder("utf-8")()
    with path.open("rb") as f:
        try:
            while chunk := f.read(1 << 20):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "latin-1"
    return "utf-8"


# ------------------------------------------------------------------ la fuente


class CsvSource:
    """Tablas Parquet nacidas de CSV. Las consultas corren en un DuckDB que solo ve `csv_dir`."""

    id = "csv"
    kind = "csv"
    dialect = "duckdb"

    def __init__(self, settings: Settings, meta: CatalogMeta) -> None:
        self._s = settings
        self._meta = meta
        self._running: dict[str, duckdb.DuckDBPyConnection] = {}
        self._lock = threading.Lock()
        settings.csv_dir.mkdir(parents=True, exist_ok=True)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _conn(self, *dirs: Path) -> duckdb.DuckDBPyConnection:
        return new_duckdb(
            allowed_dirs=dirs, memory_limit=self._s.duckdb_memory_limit, threads=self._s.duckdb_threads
        )

    def _parquet(self, table: str) -> Path:
        if not TABLE_RE.match(table):
            raise SourceError(f"nombre de tabla inválido: {table!r}")
        return self._s.csv_dir / f"{table}.parquet"

    def tables(self) -> list[str]:
        return sorted(p.stem for p in self._s.csv_dir.glob("*.parquet") if TABLE_RE.match(p.stem))

    # -- subida ----------------------------------------------------------------

    def stage(self, src: BinaryIO, filename: str) -> str:
        upload_id = uuid.uuid4().hex
        dest = self._s.uploads_dir / f"{upload_id}.csv"
        limit = self._s.max_upload_mb * 1024 * 1024
        written = 0
        with dest.open("wb") as out:
            while chunk := src.read(1 << 20):
                written += len(chunk)
                if written > limit:
                    out.close()
                    dest.unlink()
                    raise TooLarge(f"el archivo supera {self._s.max_upload_mb} MB")
                out.write(chunk)
        if written == 0:
            dest.unlink()
            raise SourceError("el archivo está vacío")
        (self._s.uploads_dir / f"{upload_id}.json").write_text(
            json.dumps({"filename": Path(filename).name}), encoding="utf-8"
        )
        return upload_id

    def _upload(self, upload_id: str) -> tuple[Path, str]:
        if not _UPLOAD_ID_RE.match(upload_id):
            raise NotFound("subida desconocida")
        path = self._s.uploads_dir / f"{upload_id}.csv"
        meta = self._s.uploads_dir / f"{upload_id}.json"
        if not path.exists() or not meta.exists():
            raise NotFound("subida desconocida o expirada")
        return path, str(json.loads(meta.read_text(encoding="utf-8"))["filename"])

    def _read_raw(
        self, conn: duckdb.DuckDBPyConnection, path: Path, encoding: str
    ) -> tuple[str, bool, str]:
        """Devuelve (delimitador, tiene encabezado, SQL de lectura todo-VARCHAR)."""
        try:
            delim, header = conn.execute(
                "SELECT Delimiter, HasHeader FROM sniff_csv(?, encoding := ?)", [str(path), encoding]
            ).fetchone() or (",", True)
        except duckdb.Error as e:
            raise SourceError(f"no se pudo leer el CSV: {e}") from e
        reader = (
            f"read_csv({sql_literal(str(path))}, all_varchar = true, header = {str(bool(header)).lower()}, "
            f"delim = {sql_literal(delim)}, encoding = {sql_literal(encoding)})"
        )
        return delim, bool(header), reader

    def preview(self, upload_id: str) -> CsvPreview:
        path, filename = self._upload(upload_id)
        encoding = _detect_encoding(path)
        warnings: list[str] = []
        if encoding != "utf-8":
            warnings.append("el archivo no es UTF-8: se leyó como Latin-1 (Excel en español suele serlo)")
        conn = self._conn(self._s.uploads_dir)
        try:
            delim, header, reader = self._read_raw(conn, path, encoding)
            try:
                sample = conn.execute(f"SELECT * FROM {reader} LIMIT {SAMPLE_ROWS}").to_arrow_table()  # noqa: S608 (reader: rutas y opciones del servidor)
            except duckdb.Error as e:
                raise SourceError(f"no se pudo leer el CSV: {e}") from e
        finally:
            conn.close()

        if header:
            with path.open(encoding=encoding, newline="") as f:
                first = next(csv.reader(io.StringIO(f.readline()), delimiter=delim), [])
            dupes = sorted({h for h in first if first.count(h) > 1})
            if dupes:
                warnings.append(f"encabezados repetidos {dupes}: se renombraron con sufijo _1, _2…")

        columns = [guess_column(n, sample.column(n).to_pylist()) for n in sample.column_names]
        head = sample.slice(0, PREVIEW_ROWS).to_pylist()
        rows = [[r[n] for n in sample.column_names] for r in head]
        return CsvPreview(
            upload_id=upload_id, filename=filename, suggested_table=suggest_table_name(filename),
            encoding=encoding, delimiter=delim, columns=columns, warnings=warnings, rows=rows,
        )

    def confirm(self, req: ConfirmRequest) -> TableInfo:
        path, filename = self._upload(req.upload_id)
        target = self._parquet(req.table)
        if target.exists():
            raise Conflict(f"la tabla {req.table!r} ya existe")
        encoding = _detect_encoding(path)
        tmp = target.with_suffix(".parquet.tmp")
        conn = self._conn(self._s.uploads_dir, self._s.csv_dir)
        try:
            delim, _, reader = self._read_raw(conn, path, encoding)
            names = [r[0] for r in conn.execute(f"DESCRIBE SELECT * FROM {reader}").fetchall()]  # noqa: S608
            if [c.name for c in req.columns] != names:
                raise SourceError(f"las columnas no coinciden con el archivo: {names}")
            # COPY no acepta parámetros: columnas citadas, tipos y formatos de listas cerradas, rutas propias
            select = ", ".join(cast_expr(c) for c in req.columns)
            copy = f"COPY (SELECT {select} FROM {reader}) TO {sql_literal(str(tmp))} (FORMAT parquet)"  # noqa: S608
            try:
                conn.execute(copy)
            except duckdb.ConversionException as e:
                raise SourceError(f"no se pudo convertir con los tipos elegidos: {e}") from e
        finally:
            conn.close()
        os.replace(tmp, target)
        target.with_suffix(".schema.json").write_text(json.dumps({
            "table": req.table,
            "source_file": filename,
            "encoding": encoding,
            "delimiter": delim,
            "columns": [c.model_dump(mode="json") for c in req.columns],
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        path.unlink()
        path.with_suffix(".json").unlink()
        return self.table_info(req.table)

    def discard(self, upload_id: str) -> None:
        path, _ = self._upload(upload_id)
        path.unlink()
        path.with_suffix(".json").unlink()

    # -- DataSource --------------------------------------------------------------

    def table_info(self, table: str) -> TableInfo:
        parquet = self._parquet(table)
        if not parquet.exists():
            raise NotFound(f"tabla desconocida: {table!r}")
        meta = self._meta.get(self.id, table)
        conn = self._conn(self._s.csv_dir)
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
        self._parquet(name)  # valida el nombre
        return (name,)  # execute() crea una vista por tabla

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
        conn = self._conn(self._s.csv_dir)
        for t in self.tables():  # CREATE VIEW no acepta parámetros; t ya pasó TABLE_RE
            path = sql_literal(str(self._parquet(t)))
            conn.execute(f"CREATE VIEW {sql_ident(t)} AS SELECT * FROM read_parquet({path})")  # noqa: S608
        timer = threading.Timer(timeout_s, conn.interrupt)
        with self._lock:
            self._running[qid] = conn
        timer.start()
        try:
            return conn.execute(sql, params or None).to_arrow_table()
        except duckdb.InterruptException as e:
            raise QueryInterrupted(f"consulta cancelada o con más de {timeout_s}s") from e
        finally:
            timer.cancel()
            with self._lock:
                self._running.pop(qid, None)
            conn.close()

    def cancel(self, query_id: str) -> None:
        with self._lock:
            conn = self._running.get(query_id)
        if conn is not None:
            conn.interrupt()

