"""Perfilado EDA de una tabla (incluidas sus columnas calculadas).

Tres pasadas, cada una una sola consulta: estadísticas de todas las columnas → detalle (histogramas,
outliers, top-N, periodos) en un UNION ALL → correlaciones sobre una muestra.

- Fuentes locales (CSV/Parquet): se perfila la tabla completa con `DataSource.execute`.
- Fuentes remotas: se trae UNA muestra (`sample_rows`) y se perfila en un DuckDB privado, sin volver a
  la fuente. El resultado lleva `sampled=True` y la UI lo muestra.

El SQL solo interpola identificadores citados por SQLGlot y números calculados en el servidor; todo pasa
por `ensure_single_select` antes de ejecutarse.
"""

from __future__ import annotations

import datetime as dt
import decimal
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

import duckdb
import pyarrow as pa
from sqlglot import exp

from data2html import cancel
from data2html.profiling.models import (
    Bin,
    ColumnKind,
    ColumnProfile,
    Correlations,
    Outliers,
    PeriodCount,
    ProfileOptions,
    ProfileWarning,
    TableProfile,
    ValueCount,
    WarningCode,
)
from data2html.settings import Settings
from data2html.sources.base import DataSource
from data2html.sources.catalog_meta import CatalogMeta
from data2html.sources.engine import new_duckdb
from data2html.sources.errors import QueryInterrupted
from data2html.sqlgen.explore import base_select
from data2html.sqlgen.validate import ensure_single_select

LOCAL_KINDS = {"csv"}  # se perfilan completas; el resto, con muestra

_INT = re.compile(r"^(U?TINYINT|U?SMALLINT|U?INTEGER|U?BIGINT|U?HUGEINT|INT\d*)$", re.I)
_FLOAT = re.compile(r"^(FLOAT|DOUBLE|REAL|DECIMAL)", re.I)
_TEMPORAL = re.compile(r"^(DATE|TIMESTAMP)", re.I)


def classify(type_: str) -> ColumnKind:
    t = type_.strip().upper()
    if _INT.match(t) or _FLOAT.match(t):
        return ColumnKind.numeric
    if _TEMPORAL.match(t):
        return ColumnKind.temporal
    if t == "BOOLEAN":
        return ColumnKind.boolean
    if t.startswith("VARCHAR") or t in {"UUID", "ENUM"} or t.startswith("ENUM"):
        return ColumnKind.text
    return ColumnKind.other


def _q(sql: str) -> exp.Query:
    """SQL armado aquí → árbol validado. Solo identificadores citados y números del servidor."""
    return ensure_single_select(sql)


def _id(name: str) -> str:
    return exp.to_identifier(name, quoted=True).sql("duckdb")


def _num(v: float) -> str:
    return repr(float(v))


def _f(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, decimal.Decimal | int | float):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    return None


# ------------------------------------------------------------------ ejecución


class _Runner(Protocol):
    def run(self, q: exp.Query) -> pa.Table: ...

    def close(self) -> None: ...


@dataclass
class _SourceRunner:
    """Consultas sobre la tabla en la fuente: `WITH _t AS (<base>) …`."""

    src: DataSource
    base: exp.Select
    timeout_s: int
    query_id: str | None = None

    def run(self, q: exp.Query) -> pa.Table:
        cancel.raise_if_cancelled(self.query_id)
        sql = q.with_("_t", as_=self.base.copy()).sql("duckdb")
        return self.src.execute(sql, {}, identity=None, timeout_s=self.timeout_s, query_id=self.query_id)

    def close(self) -> None:
        pass


@dataclass
class _ArrowRunner:
    """Consultas sobre una muestra ya traída, en un DuckDB privado sin acceso a archivos."""

    table: pa.Table
    settings: Settings
    query_id: str | None = None
    conn: duckdb.DuckDBPyConnection = field(init=False)
    _unhook: Callable[[], None] = field(init=False)

    def __post_init__(self) -> None:
        self.conn = new_duckdb(allowed_dirs=[], memory_limit=self.settings.duckdb_memory_limit,
                               threads=self.settings.duckdb_threads,
                               setup=self._register)
        qid = self.query_id
        self._unhook = cancel.on_cancel(qid, self.conn.interrupt) if qid else (lambda: None)

    def _register(self, conn: duckdb.DuckDBPyConnection) -> None:
        conn.register("_t", self.table)

    def run(self, q: exp.Query) -> pa.Table:
        cancel.raise_if_cancelled(self.query_id)
        try:
            return self.conn.execute(q.sql("duckdb")).to_arrow_table()
        except duckdb.InterruptException as e:
            raise QueryInterrupted("consulta cancelada") from e

    def close(self) -> None:
        self._unhook()
        self.conn.close()


# ------------------------------------------------------------------ pasada 1: estadísticas


@dataclass
class _Col:
    i: int
    name: str
    type: str
    kind: ColumnKind
    computed: bool

    @property
    def ref(self) -> str:
        return _id(self.name)

    @property
    def is_int(self) -> bool:
        return bool(_INT.match(self.type.strip()))


def _stats_query(cols: list[_Col]) -> exp.Query:
    parts = ["count(*) AS n"]
    for c in cols:
        r, i = c.ref, c.i
        parts += [f"count({r}) AS nn_{i}", f"count(DISTINCT {r}) AS d_{i}"]
        if c.kind is ColumnKind.numeric:
            parts += [
                f"min({r}) AS min_{i}", f"max({r}) AS max_{i}",
                f"avg(CAST({r} AS DOUBLE)) AS mean_{i}", f"stddev_samp(CAST({r} AS DOUBLE)) AS std_{i}",
                f"quantile_cont(CAST({r} AS DOUBLE), [0.25, 0.5, 0.75]) AS q_{i}",
            ]
        elif c.kind is ColumnKind.temporal:
            parts += [f"min({r}) AS min_{i}", f"max({r}) AS max_{i}"]
        elif c.kind is ColumnKind.text:
            parts += [
                f"min(length(CAST({r} AS VARCHAR))) AS minlen_{i}",
                f"max(length(CAST({r} AS VARCHAR))) AS maxlen_{i}",
                # números como texto, salvo códigos con ceros a la izquierda (CP, claves): esos son texto
                f"count(CASE WHEN NOT regexp_matches(CAST({r} AS VARCHAR), '^[+-]?0[0-9]') "
                f"THEN TRY_CAST(replace(CAST({r} AS VARCHAR), ',', '.') AS DOUBLE) END) AS numlike_{i}",
            ]
    return _q("SELECT " + ", ".join(parts) + " FROM _t")  # noqa: S608 (ver _q)


# ------------------------------------------------------------------ pasada 2: detalle


@dataclass
class _Hist:
    start: float
    width: float
    bins: int


def hist_bins(
    mn: float, mx: float, q1: float, q3: float, n: int, distinct: int, is_int: bool, max_bins: int
) -> _Hist:
    """Freedman-Diaconis, con tope `max_bins` y no más bins que valores distintos. Enteros: una barra por
    valor si el rango cabe en `max_bins`; si no, anchos enteros."""
    if mx <= mn:
        return _Hist(mn, 1.0, 1)
    if is_int and mx - mn + 1 <= max_bins:
        return _Hist(mn, 1.0, int(mx - mn) + 1)
    iqr = q3 - q1
    h = 2 * iqr / n ** (1 / 3) if n > 0 and iqr > 0 else 0.0
    bins = math.ceil((mx - mn) / h) if h > 0 else math.ceil(math.sqrt(max(n, 1)))
    bins = max(1, min(max_bins, distinct, bins))
    if is_int:
        span = int(mx - mn) + 1
        width = max(1, math.ceil(span / bins))
        return _Hist(mn, float(width), math.ceil(span / width))
    return _Hist(mn, (mx - mn) / bins, bins)


def _period_unit(mn: object, mx: object) -> Literal["year", "month", "day", "hour"]:
    if isinstance(mn, dt.datetime) and isinstance(mx, dt.datetime):
        days = (mx - mn).total_seconds() / 86400
    elif isinstance(mn, dt.date) and isinstance(mx, dt.date):
        days = float((mx - mn).days)
    else:
        return "day"
    if days > 3 * 366:
        return "year"
    if days > 92:
        return "month"
    if days > 2 or not isinstance(mn, dt.datetime):
        return "day"
    return "hour"


def _branch(i: int, kind: str, key_expr: str, where: str, tail: str = "") -> str:
    return (f"SELECT * FROM (SELECT {i} AS c, '{kind}' AS k, CAST({key_expr} AS VARCHAR) AS key, "  # noqa: S608
            f"count(*) AS n FROM _t WHERE {where} GROUP BY 3 {tail})")


# ------------------------------------------------------------------ avisos


def _warnings(p: ColumnProfile, c: _Col, numlike: int | None, o: ProfileOptions) -> list[ProfileWarning]:
    w: list[ProfileWarning] = []
    if p.non_null == 0:
        return [ProfileWarning(code=WarningCode.empty, message="columna sin valores")]
    if p.null_ratio > o.nulls_ratio:
        w.append(ProfileWarning(code=WarningCode.nulls, message=f"{p.null_ratio:.0%} de nulos"))
    if p.distinct == 1:
        w.append(ProfileWarning(code=WarningCode.constant, message="un solo valor distinto"))
    id_like = c.kind is ColumnKind.text or (c.kind is ColumnKind.numeric and c.is_int)
    if id_like and p.non_null >= o.possible_id_min_rows and p.distinct_ratio >= o.possible_id_ratio:
        msg = f"{p.distinct_ratio:.0%} de valores distintos: posible identificador"
        w.append(ProfileWarning(code=WarningCode.possible_id, message=msg))
    elif c.kind is ColumnKind.text and p.distinct > o.high_cardinality:
        w.append(ProfileWarning(code=WarningCode.high_cardinality,
                                message=f"{p.distinct:,} valores distintos: alta cardinalidad"))
    if c.kind is ColumnKind.text and numlike is not None and numlike >= o.numeric_text_ratio * p.non_null:
        w.append(ProfileWarning(code=WarningCode.numeric_as_text,
                                message=f"{numlike / p.non_null:.0%} parecen números guardados como texto"))
    return w


# ------------------------------------------------------------------ orquestación


def profile_table(
    src: DataSource,
    meta: CatalogMeta,
    table: str,
    settings: Settings,
    opts: ProfileOptions | None = None,
    query_id: str | None = None,
) -> TableProfile:
    """`query_id`: permite cancelarlo con `cancel.request` (POST /api/cancel/{query_id})."""
    o = opts or ProfileOptions()
    t0 = time.perf_counter()
    info = src.table_info(table)
    computed = meta.get(src.id, table).computed
    base, types = base_select(src.relation(table), {c.name: c.type for c in info.columns}, computed)
    computed_names = {c.name for c in computed}
    cols = [_Col(i, n, t, classify(t), n in computed_names) for i, (n, t) in enumerate(types.items())]

    runner: _Runner
    sampled = False
    sample_size: int | None = None
    if src.kind in LOCAL_KINDS:
        runner = _SourceRunner(src, base, settings.query_timeout_s, query_id)
    else:
        sample_size = o.sample_rows
        q = _q(f"SELECT * FROM _t USING SAMPLE reservoir({int(o.sample_rows)} ROWS) REPEATABLE (42)")  # noqa: S608
        sample = _SourceRunner(src, base, settings.query_timeout_s, query_id).run(q)
        sampled = sample.num_rows >= o.sample_rows
        runner = _ArrowRunner(sample, settings, query_id)
    try:
        profiles, rows, corr = _profile(runner, cols, o)
    finally:
        runner.close()

    return TableProfile(
        source=src.id, table=table, rows=rows, sampled=sampled,
        sample_size=sample_size, columns=profiles, correlations=corr,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        profiled_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    )


def _profile(
    runner: _Runner, cols: list[_Col], o: ProfileOptions
) -> tuple[list[ColumnProfile], int, Correlations | None]:
    if not cols:
        return [], 0, None
    s = runner.run(_stats_query(cols)).to_pylist()[0]
    n = int(s["n"])

    profiles: dict[int, ColumnProfile] = {}
    numlike: dict[int, int | None] = {}
    branches: list[str] = []
    hists: dict[int, _Hist] = {}
    for c in cols:
        i, r = c.i, c.ref
        nn, d = int(s[f"nn_{i}"]), int(s[f"d_{i}"])
        p = ColumnProfile(
            name=c.name, type=c.type, kind=c.kind, computed=c.computed, non_null=nn, nulls=n - nn,
            null_ratio=(n - nn) / n if n else 0.0, distinct=d, distinct_ratio=d / nn if nn else 0.0,
            warnings=[],
        )
        numlike[i] = None
        if c.kind is ColumnKind.numeric and nn:
            q1, med, q3 = (_f(v) for v in s[f"q_{i}"])
            mn, mx = _f(s[f"min_{i}"]), _f(s[f"max_{i}"])
            p.min, p.max, p.mean, p.std = mn, mx, _f(s[f"mean_{i}"]), _f(s[f"std_{i}"])
            p.q1, p.median, p.q3 = q1, med, q3
            if None not in (mn, mx, q1, q3):
                assert mn is not None and mx is not None and q1 is not None and q3 is not None
                h = hist_bins(mn, mx, q1, q3, nn, d, c.is_int, o.max_bins)
                hists[i] = h
                bucket = f"floor((CAST({r} AS DOUBLE) - {_num(h.start)}) / {_num(h.width)})"
                idx = f"least(CAST({bucket} AS BIGINT), {h.bins - 1})"
                branches.append(_branch(i, "hist", idx, f"{r} IS NOT NULL"))
                iqr = q3 - q1
                lo, hi = q1 - o.iqr_factor * iqr, q3 + o.iqr_factor * iqr
                p.outliers = Outliers(low_fence=lo, high_fence=hi, below=0, above=0)
                band = f"CASE WHEN {r} < {_num(lo)} THEN 'below' ELSE 'above' END"
                branches.append(_branch(i, "out", band, f"{r} < {_num(lo)} OR {r} > {_num(hi)}"))
        elif c.kind is ColumnKind.temporal and nn:
            mn_t, mx_t = s[f"min_{i}"], s[f"max_{i}"]
            p.min = mn_t.isoformat() if hasattr(mn_t, "isoformat") else str(mn_t)
            p.max = mx_t.isoformat() if hasattr(mx_t, "isoformat") else str(mx_t)
            p.period_unit = _period_unit(mn_t, mx_t)
            p.periods = []
            trunc = f"date_trunc('{p.period_unit}', {r})"
            if c.type.strip().upper() == "DATE":
                trunc = f"CAST({trunc} AS DATE)"  # date_trunc devuelve TIMESTAMP
            branches.append(_branch(i, "period", trunc, f"{r} IS NOT NULL", "ORDER BY 3 LIMIT 1000"))
        elif c.kind in (ColumnKind.text, ColumnKind.boolean) and nn:
            if c.kind is ColumnKind.text:
                p.min_length, p.max_length = s[f"minlen_{i}"], s[f"maxlen_{i}"]
                numlike[i] = int(s[f"numlike_{i}"])
            p.top = []
            top_tail = f"ORDER BY 4 DESC, 3 LIMIT {int(o.top_n)}"
            branches.append(_branch(i, "top", r, f"{r} IS NOT NULL", top_tail))
        profiles[i] = p

    if branches:
        detail = runner.run(_q(" UNION ALL ".join(branches)))
        hist_counts: dict[int, dict[int, int]] = {}
        for row in detail.to_pylist():
            i, k, key, cnt = int(row["c"]), row["k"], row["key"], int(row["n"])
            p = profiles[i]
            if k == "hist":
                hist_counts.setdefault(i, {})[int(key)] = cnt
            elif k == "out" and p.outliers is not None:
                if key == "below":
                    p.outliers.below = cnt
                else:
                    p.outliers.above = cnt
            elif k == "top" and p.top is not None:
                p.top.append(ValueCount(value=key, count=cnt))
            elif k == "period" and p.periods is not None:
                p.periods.append(PeriodCount(period=key, count=cnt))
        for i, h in hists.items():
            counts = hist_counts.get(i, {})
            profiles[i].histogram = [
                Bin(start=h.start + b * h.width, end=h.start + (b + 1) * h.width, count=counts.get(b, 0))
                for b in range(h.bins)
            ]
        for p in profiles.values():
            if p.top is not None:
                p.top.sort(key=lambda v: (-v.count, v.value))
                p.other_count = p.non_null - sum(v.count for v in p.top)

    for c in cols:
        profiles[c.i].warnings = _warnings(profiles[c.i], c, numlike[c.i], o)

    varying = [c for c in cols if c.kind is ColumnKind.numeric and profiles[c.i].distinct > 1]
    corr = _correlations(runner, varying, o)
    return [profiles[c.i] for c in cols], n, corr


def _correlations(runner: _Runner, cols: list[_Col], o: ProfileOptions) -> Correlations | None:
    """Pearson y Spearman (rangos promedio) sobre una muestra; solo si hay 2..max_corr_columns numéricas."""
    if not 2 <= len(cols) <= o.max_corr_columns:
        return None
    k = len(cols)
    xs = ", ".join(f"CAST({c.ref} AS DOUBLE) AS x{j}" for j, c in enumerate(cols))
    ranks = ", ".join(
        f"x{j}, CASE WHEN x{j} IS NULL THEN NULL ELSE rank() OVER (ORDER BY x{j}) "
        f"+ (count(*) OVER (PARTITION BY x{j}) - 1) / 2.0 END AS r{j}"
        for j in range(k)
    )
    aggs = ["count(*) AS n"]
    for a in range(k):
        for b in range(a + 1, k):
            aggs += [f"corr(x{a}, x{b}) AS p_{a}_{b}", f"corr(r{a}, r{b}) AS s_{a}_{b}"]
    sample = f"SELECT {xs} FROM _t USING SAMPLE reservoir({int(o.sample_rows)} ROWS) REPEATABLE (42)"  # noqa: S608
    sql = f"SELECT {', '.join(aggs)} FROM (SELECT {ranks} FROM ({sample}) AS s) AS r"  # noqa: S608 (ver _q)
    row = runner.run(_q(sql)).to_pylist()[0]
    pearson: list[list[float | None]] = [[1.0 if a == b else None for b in range(k)] for a in range(k)]
    spearman: list[list[float | None]] = [[1.0 if a == b else None for b in range(k)] for a in range(k)]
    for a in range(k):
        for b in range(a + 1, k):
            pearson[a][b] = pearson[b][a] = _f(row[f"p_{a}_{b}"])
            spearman[a][b] = spearman[b][a] = _f(row[f"s_{a}_{b}"])
    return Correlations(columns=[c.name for c in cols], n=int(row["n"]), pearson=pearson, spearman=spearman)
