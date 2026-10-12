"""EDA profiling result. Aggregates only: the browser never receives raw rows."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnKind(StrEnum):
    numeric = "numeric"
    temporal = "temporal"
    text = "text"
    boolean = "boolean"
    other = "other"


class WarningCode(StrEnum):
    possible_id = "possible_id"
    high_cardinality = "high_cardinality"
    nulls = "nulls"
    constant = "constant"
    empty = "empty"
    numeric_as_text = "numeric_as_text"


class ProfileWarning(_M):
    code: WarningCode
    message: str


class ProfileOptions(_M):
    """Warning thresholds. The defaults come from the eda-profiling skill."""

    sample_rows: Annotated[int, Field(ge=1000, le=1_000_000)] = 100_000
    top_n: Annotated[int, Field(ge=1, le=100)] = 20
    max_bins: Annotated[int, Field(ge=2, le=200)] = 50
    max_corr_columns: Annotated[int, Field(ge=2, le=100)] = 50
    possible_id_ratio: Annotated[float, Field(gt=0, le=1)] = 0.95
    possible_id_min_rows: Annotated[int, Field(ge=1)] = 20
    high_cardinality: Annotated[int, Field(ge=1)] = 1000
    nulls_ratio: Annotated[float, Field(ge=0, le=1)] = 0.20
    numeric_text_ratio: Annotated[float, Field(gt=0, le=1)] = 0.95
    iqr_factor: Annotated[float, Field(gt=0)] = 1.5


class Bin(_M):
    start: float
    end: float
    count: int


class Outliers(_M):
    low_fence: float
    high_fence: float
    below: int
    above: int


class ValueCount(_M):
    value: str
    count: int


class PeriodCount(_M):
    period: str
    count: int


class ColumnProfile(_M):
    name: str
    type: str
    kind: ColumnKind
    computed: bool
    non_null: int
    nulls: int
    null_ratio: float
    distinct: int
    distinct_ratio: float  # over non-null values
    # numeric
    min: float | str | None = None  # str for temporal columns
    max: float | str | None = None
    mean: float | None = None
    std: float | None = None
    q1: float | None = None
    median: float | None = None
    q3: float | None = None
    histogram: list[Bin] | None = None
    outliers: Outliers | None = None
    # text / boolean
    min_length: int | None = None
    max_length: int | None = None
    top: list[ValueCount] | None = None
    other_count: int | None = None
    # temporal
    period_unit: Literal["year", "month", "day", "hour"] | None = None
    periods: list[PeriodCount] | None = None
    warnings: list[ProfileWarning]  # no default: always present in the response


class Correlations(_M):
    columns: list[str]
    n: int  # rows of the sample used
    pearson: list[list[float | None]]
    spearman: list[list[float | None]]


class TableProfile(_M):
    source: str
    table: str
    rows: int  # profiled rows
    sampled: bool
    sample_size: int | None  # requested sample size, if any
    columns: list[ColumnProfile]
    correlations: Correlations | None
    elapsed_ms: int
    profiled_at: str
