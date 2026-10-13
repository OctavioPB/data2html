"""DynamoDB → Parquet (ADR 0012). Never a `Scan`: a native point-in-time export to S3, then flattening.

1. `ExportTableToPointInTime` (PITR must be enabled on the table), format DYNAMODB_JSON, full export.
2. Wait for COMPLETED (`max_wait_min`) and read the manifests. Every data key must live under the export's
   own prefix. Each data file is downloaded with boto3 and streamed: only the DECLARED attributes are
   extracted (nested maps by `a.b` paths) into one JSON-lines file of plain text values.
3. A sandboxed DuckDB (only the staging and output directories, no network) reads that file, converts each
   column with TRY_CAST (values that do not convert become NULL and are counted as warnings) and replaces
   `data/dynamodb/<source>/<table>.parquet` atomically, next to `<table>.export.json`.

AWS credentials come from boto3's standard chain (instance/task role, environment, profile): never from
config files.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
import os
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import IO, Any

from data2html.settings import Settings
from data2html.sources.dynamodb import export_dir
from data2html.sources.engine import new_duckdb, sql_ident, sql_literal
from data2html.sources.registry import DynamoColumn, DynamoDBConfig, DynamoTable

log = logging.getLogger(__name__)
POLL_S = 30


class IngestError(Exception):
    pass


@dataclass
class ExportResult:
    source: str
    table: str
    export_arn: str = ""
    export_time: str = ""
    rows: int = 0
    warnings: dict[str, int] = field(default_factory=dict)  # column → values that did not convert
    finished_at: str = ""


# ------------------------------------------------------------------ DynamoDB JSON → plain values


def _number(text: str) -> int | float:
    d = Decimal(text)
    return int(d) if d == d.to_integral_value() else float(d)


def ddb_value(v: Any) -> Any:
    """`{"S": "x"}` → "x", `{"M": {...}}` → dict, `{"NS": ["1"]}` → [1]… (binary → base64 text)."""
    if not isinstance(v, dict) or len(v) != 1:
        return None
    ((tag, x),) = v.items()
    if tag == "S":
        return x
    if tag == "N":
        return _number(x)
    if tag == "BOOL":
        return bool(x)
    if tag == "NULL":
        return None
    if tag == "B":
        return x if isinstance(x, str) else base64.b64encode(x).decode()
    if tag == "M":
        return {k: ddb_value(i) for k, i in x.items()}
    if tag == "L":
        return [ddb_value(i) for i in x]
    if tag in ("SS", "BS"):
        return list(x)
    if tag == "NS":
        return [_number(i) for i in x]
    return None


def extract(item: dict[str, Any], path: str) -> Any:
    """Typed attribute at `a.b.c` (nested maps), or None."""
    node: Any = {"M": item}
    for seg in path.split("."):
        if not isinstance(node, dict) or "M" not in node or not isinstance(node["M"], dict):
            return None
        node = node["M"].get(seg)
    return node


def plain_text(attr: Any, col: DynamoColumn) -> str | None:
    """The text DuckDB will convert to the column's type. JSON columns (and any list, set or map) get
    plain JSON; scalars their DynamoDB text (`N` keeps its exact decimal digits)."""
    if attr is None:
        return None
    if col.type == "JSON":
        value = ddb_value(attr)
        return None if value is None else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if not isinstance(attr, dict) or len(attr) != 1:
        return None
    ((tag, x),) = attr.items()
    if tag in ("S", "N"):
        return str(x)
    if tag == "BOOL":
        return "true" if x else "false"
    if tag == "NULL":
        return None
    return json.dumps(ddb_value(attr), ensure_ascii=False, separators=(",", ":"))


def typed_sql(name: str, col: DynamoColumn) -> str:
    """Conversion of the text column `name` to the declared type (types already match `_DDB_TYPE`)."""
    c = sql_ident(name)
    t = col.type
    if t in ("VARCHAR", "JSON"):
        return c
    if t in ("DATE", "TIMESTAMP") and col.unit != "iso":
        # make_timestamp(µs) is UTC and zone-free; to_timestamp() would depend on the server's time zone
        per_unit = 1_000_000 if col.unit == "epoch_s" else 1_000
        micros = f"CAST(TRY_CAST({c} AS DOUBLE) * {per_unit} AS BIGINT)"
        return f"CAST(make_timestamp({micros}) AS {t})"
    return f"TRY_CAST({c} AS {t})"


# ------------------------------------------------------------------ the pipeline


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DynamoIngest:
    def __init__(
        self, source_id: str, cfg: DynamoDBConfig, settings: Settings, *, dynamodb: Any = None,
        s3: Any = None, sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source_id = source_id
        self.cfg = cfg
        self.s = settings
        self._sleep = sleep
        if dynamodb is None or s3 is None:
            import boto3  # optional dependency: pip install -e ".[dynamodb]"

            dynamodb = dynamodb or boto3.client("dynamodb", region_name=cfg.region)
            s3 = s3 or boto3.client("s3", region_name=cfg.region)
        self.ddb = dynamodb
        self.s3 = s3

    def run(self, table: str) -> ExportResult:
        t = self.cfg.tables.get(table)
        if t is None:
            raise IngestError(f"table {table!r} is not configured in source {self.source_id!r}")
        out_dir = export_dir(self.s, self.source_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        lock = out_dir / f"{table}.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.time() - lock.stat().st_mtime < t.max_wait_min * 60 + 600:
                raise IngestError(f"an export of {table!r} is already running") from None
            lock.unlink(missing_ok=True)  # stale: a previous run died
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        staging = self.s.data_dir / "ingest" / self.source_id / f"{table}-{uuid.uuid4().hex[:8]}"
        try:
            desc = self._export(t)
            flat = self._download(t, desc, staging)
            result = self._to_parquet(table, t, flat, staging, out_dir)
            result.export_arn = desc["ExportArn"]
            result.export_time = str(desc.get("ExportTime", ""))
            meta = json.dumps(asdict(result), indent=2)
            (out_dir / f"{table}.export.json").write_text(meta, encoding="utf-8")
            log.info("dynamodb %s.%s: %d rows from %s", self.source_id, table, result.rows, result.export_arn)
            return result
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            lock.unlink(missing_ok=True)

    def _export(self, t: DynamoTable) -> dict[str, Any]:
        desc: dict[str, Any] = self.ddb.export_table_to_point_in_time(
            TableArn=t.table_arn, S3Bucket=t.s3_bucket, S3Prefix=t.s3_prefix, ExportFormat="DYNAMODB_JSON",
            ExportType="FULL_EXPORT", ClientToken=uuid.uuid4().hex,
        )["ExportDescription"]
        deadline = time.monotonic() + t.max_wait_min * 60
        while desc["ExportStatus"] == "IN_PROGRESS":
            if time.monotonic() > deadline:
                raise IngestError(f"export {desc['ExportArn']} did not finish in {t.max_wait_min} min")
            self._sleep(POLL_S)
            desc = self.ddb.describe_export(ExportArn=desc["ExportArn"])["ExportDescription"]
        if desc["ExportStatus"] != "COMPLETED":
            why = f"{desc.get('FailureCode', '')} {desc.get('FailureMessage', '')}"
            raise IngestError(f"export failed: {why}")
        return desc

    def _get(self, bucket: str, key: str) -> bytes:
        body: bytes = self.s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return body

    def _download(self, t: DynamoTable, desc: dict[str, Any], staging: Path) -> Path:
        """Data files → `flat.jsonl`: one object per item with the declared columns as plain text."""
        bucket = t.s3_bucket
        summary_key: str = desc["ExportManifest"]
        export_root = summary_key.rsplit("/", 1)[0] + "/"  # <prefix>/AWSDynamoDB/<export-id>/
        summary = json.loads(self._get(bucket, summary_key))
        lines = self._get(bucket, summary["manifestFilesS3Key"]).decode().splitlines()
        keys = [json.loads(x)["dataFileS3Key"] for x in lines if x.strip()]
        for key in keys:  # checked before downloading anything
            if not key.startswith(export_root) or ".." in key:
                raise IngestError(f"unexpected data file outside the export: {key!r}")
        staging.mkdir(parents=True, exist_ok=True)
        flat = staging / "flat.jsonl"
        with flat.open("w", encoding="utf-8", newline="\n") as out:
            for key in keys:
                with gzip.open(_bytes_io(self._get(bucket, key)), "rt", encoding="utf-8") as f:
                    self._flatten_lines(f, t, out)
        return flat

    @staticmethod
    def _flatten_lines(lines: IO[str], t: DynamoTable, out: IO[str]) -> None:
        for line in lines:
            if not line.strip():
                continue
            item = json.loads(line).get("Item") or {}
            row = {name: plain_text(extract(item, col.path), col) for name, col in t.columns.items()}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _to_parquet(
        self, table: str, t: DynamoTable, flat: Path, staging: Path, out_dir: Path
    ) -> ExportResult:
        def setup(conn: Any) -> None:
            conn.execute(f"SET temp_directory = {sql_literal(str(staging / 'tmp'))}")

        conn = new_duckdb(allowed_dirs=[staging, out_dir], memory_limit=self.s.duckdb_memory_limit,
                          threads=self.s.duckdb_threads, setup=setup)
        tmp = out_dir / f"{table}.parquet.tmp"
        try:
            # read_json/COPY take no parameters: names and types come from the validated config
            text_cols = ", ".join(f"{sql_literal(n)}: 'VARCHAR'" for n in t.columns)
            conn.execute(
                f"CREATE TEMP TABLE raw AS SELECT * FROM read_json({sql_literal(str(flat))}, "  # noqa: S608
                f"format = 'newline_delimited', columns = {{{text_cols}}})"
            )
            typed = ", ".join(f"{typed_sql(n, c)} AS {sql_ident(n)}" for n, c in t.columns.items())
            conn.execute(f"CREATE TEMP TABLE flat AS SELECT {typed} FROM raw")  # noqa: S608
            warnings: dict[str, int] = {}
            for n in t.columns:
                (bad,) = conn.execute(
                    f"SELECT count(*) FROM raw, flat WHERE raw.rowid = flat.rowid "  # noqa: S608
                    f"AND raw.{sql_ident(n)} IS NOT NULL AND flat.{sql_ident(n)} IS NULL"
                ).fetchone() or (0,)
                if bad:
                    warnings[n] = int(bad)
            (rows,) = conn.execute("SELECT count(*) FROM flat").fetchone() or (0,)
            conn.execute(f"COPY flat TO {sql_literal(str(tmp))} (FORMAT parquet)")
        finally:
            conn.close()
        os.replace(tmp, out_dir / f"{table}.parquet")  # readers never see a half-written file
        return ExportResult(source=self.source_id, table=table, rows=int(rows), warnings=warnings,
                            finished_at=_now())


def _bytes_io(data: bytes) -> IO[bytes]:
    import io

    return io.BytesIO(data)
