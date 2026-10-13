"""CSV source (Import mode): upload → type review by the author → Parquet in `data/csv/`.

Flow: `stage()` stores the uploaded file, `preview()` suggests types and warns about traps
(leading zeros, decimal comma, ambiguous dates, repeated headers, encoding), and `confirm()`
converts with the types the author reviewed and writes `<table>.schema.json` next to the Parquet.
"""

from __future__ import annotations

import codecs
import csv
import io
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

import duckdb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from data2html.i18n import tr
from data2html.settings import Settings
from data2html.sources.base import TableInfo
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.engine import sql_ident, sql_literal
from data2html.sources.errors import Conflict, NotFound, SourceError, TooLarge
from data2html.sources.parquet import TABLE_RE, ParquetSource

_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SAMPLE_ROWS = 10_000
PREVIEW_ROWS = 20


# ------------------------------------------------------------------ API contract


UPLOAD_TTL_S = 24 * 3600  # an upload is reviewed and confirmed within minutes; a day is generous


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
            raise ValueError(tr("{column}: date_format only applies to DATE/TIMESTAMP", column=self.name))
        if self.decimal_comma and self.type is not CsvType.DOUBLE:
            raise ValueError(tr("{column}: decimal_comma only applies to DOUBLE", column=self.name))
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


# ------------------------------------------------------------------ inference (pure, testable)

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
        return ColumnGuess(name=name, type=CsvType.VARCHAR, warnings=[tr("empty column in the sample")])

    if all(v.lower() in _BOOL for v in vals):
        return ColumnGuess(name=name, type=CsvType.BOOLEAN)

    if all(_INT.match(v) for v in vals):
        zeros = next((v for v in vals if _has_leading_zero(v)), None)
        if zeros is not None:
            return ColumnGuess(name=name, type=CsvType.VARCHAR, warnings=[
                tr("leading zeros ('{sample}'): kept as text so they are not lost", sample=zeros),
            ])
        if any(len(v.lstrip("+-")) > 18 for v in vals):
            return ColumnGuess(name=name, type=CsvType.VARCHAR,
                               warnings=[tr("integer too long: kept as text")])
        return ColumnGuess(name=name, type=CsvType.BIGINT)

    if all(_INT.match(v) or _DEC_DOT.match(v) for v in vals):
        return ColumnGuess(name=name, type=CsvType.DOUBLE)

    if all(_INT.match(v) or _DEC_COMMA.match(v) for v in vals):
        sample = next(v for v in vals if "," in v)
        return ColumnGuess(name=name, type=CsvType.DOUBLE, decimal_comma=True, warnings=[
            tr("decimal comma detected ('{sample}'); the dot is taken as the thousands separator",
               sample=sample),
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
            return ColumnGuess(name=name, type=CsvType.VARCHAR,
                               warnings=[tr("dates with inconsistent order")])
        if any(f > 12 for f in firsts):
            return ColumnGuess(name=name, type=CsvType.DATE, date_format=day_first)
        if any(s > 12 for s in seconds):
            return ColumnGuess(name=name, type=CsvType.DATE, date_format=month_first)
        return ColumnGuess(name=name, type=CsvType.DATE, date_format=day_first, warnings=[
            tr("ambiguous date ('{sample}'): day/month assumed; change it if it is month/day",
               sample=vals[0]),
        ])

    return ColumnGuess(name=name, type=CsvType.VARCHAR)


def suggest_table_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_") or "table"
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
    if choice.date_format:  # from a closed list (DateFormat): safe as a literal
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


# ------------------------------------------------------------------ the source


class CsvSource(ParquetSource):
    """Parquet tables born from CSV files. Queries run in a DuckDB that can only see `csv_dir`."""

    kind = "csv"

    def __init__(self, settings: Settings, meta: CatalogMeta) -> None:
        super().__init__("csv", settings.csv_dir, settings, meta)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.clean_uploads()

    def clean_uploads(self, *, now: float | None = None) -> int:
        """Delete uploads that were neither confirmed nor cancelled within UPLOAD_TTL_S (a closed tab,
        a crashed browser). Runs at start-up and on every new upload. Returns how many were removed."""
        cutoff = (now if now is not None else time.time()) - UPLOAD_TTL_S
        removed = 0
        for f in self._s.uploads_dir.glob("*"):
            if f.suffix in (".csv", ".json") and _UPLOAD_ID_RE.match(f.stem) and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += f.suffix == ".csv"
        return removed

    # -- upload ------------------------------------------------------------------

    def stage(self, src: BinaryIO, filename: str) -> str:
        self.clean_uploads()
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
                    raise TooLarge(tr("the file exceeds {mb} MB", mb=self._s.max_upload_mb))
                out.write(chunk)
        if written == 0:
            dest.unlink()
            raise SourceError(tr("the file is empty"))
        (self._s.uploads_dir / f"{upload_id}.json").write_text(
            json.dumps({"filename": Path(filename).name}), encoding="utf-8"
        )
        return upload_id

    def _upload(self, upload_id: str) -> tuple[Path, str]:
        if not _UPLOAD_ID_RE.match(upload_id):
            raise NotFound(tr("unknown upload"))
        path = self._s.uploads_dir / f"{upload_id}.csv"
        meta = self._s.uploads_dir / f"{upload_id}.json"
        if not path.exists() or not meta.exists():
            raise NotFound(tr("unknown or expired upload"))
        return path, str(json.loads(meta.read_text(encoding="utf-8"))["filename"])

    def _read_raw(
        self, conn: duckdb.DuckDBPyConnection, path: Path, encoding: str
    ) -> tuple[str, bool, str]:
        """Return (delimiter, has header, all-VARCHAR read SQL)."""
        try:
            delim, header = conn.execute(
                "SELECT Delimiter, HasHeader FROM sniff_csv(?, encoding := ?)", [str(path), encoding]
            ).fetchone() or (",", True)
        except duckdb.Error as e:
            raise SourceError(tr("could not read the CSV: {error}", error=e)) from e
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
            warnings.append(tr("the file is not UTF-8: it was read as Latin-1 (Excel exports often are)"))
        conn = self._conn(self._s.uploads_dir)
        try:
            delim, header, reader = self._read_raw(conn, path, encoding)
            try:
                sample = conn.execute(f"SELECT * FROM {reader} LIMIT {SAMPLE_ROWS}").to_arrow_table()  # noqa: S608 (reader: server paths and options)
            except duckdb.Error as e:
                raise SourceError(tr("could not read the CSV: {error}", error=e)) from e
        finally:
            conn.close()

        if header:
            with path.open(encoding=encoding, newline="") as f:
                first = next(csv.reader(io.StringIO(f.readline()), delimiter=delim), [])
            dupes = sorted({h for h in first if first.count(h) > 1})
            if dupes:
                warnings.append(tr("repeated headers {names}: renamed with suffixes _1, _2…", names=dupes))

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
            raise Conflict(tr("table {name} already exists", name=repr(req.table)))
        encoding = _detect_encoding(path)
        tmp = target.with_suffix(".parquet.tmp")
        conn = self._conn(self._s.uploads_dir, self._dir)
        try:
            delim, _, reader = self._read_raw(conn, path, encoding)
            names = [r[0] for r in conn.execute(f"DESCRIBE SELECT * FROM {reader}").fetchall()]  # noqa: S608
            if [c.name for c in req.columns] != names:
                raise SourceError(tr("the columns do not match the file: {names}", names=names))
            # COPY takes no parameters: quoted columns, types and formats from closed lists, our own paths
            select = ", ".join(cast_expr(c) for c in req.columns)
            copy = f"COPY (SELECT {select} FROM {reader}) TO {sql_literal(str(tmp))} (FORMAT parquet)"  # noqa: S608
            try:
                conn.execute(copy)
            except duckdb.ConversionException as e:
                raise SourceError(tr("could not convert with the chosen types: {error}", error=e)) from e
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
