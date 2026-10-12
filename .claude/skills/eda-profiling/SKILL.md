---
name: eda-profiling
description: Use when implementing or improving EDA profiling (backend/src/data2html/profiling/): per-column statistics, histograms, correlations, outliers and data-quality warnings.
---

# EDA profiling

## Per column
- Base: the same metrics as `SUMMARIZE` (min, max, distinct, nulls, quantiles), but as a SELECT of
  aggregates (`profiling/profiler.py`): `SUMMARIZE` is not a SELECT and SQL validation (ADR 0007)
  rejects it. Exact distinct counts (`count(DISTINCT)`), not approximate.
- Numeric: histogram with Freedman-Diaconis bins (max 50, never more than the distinct values;
  short-range integers: one bar per value), outliers by IQR (1.5×).
- Categorical: top 20 + "others". Temporal: range and count per period.

## Warnings (each with a configurable threshold)
| Warning | Default rule |
|---|---|
| Possible ID | distinct ≥ 95% of non-null rows |
| High cardinality | categorical with > 1000 distinct |
| Nulls | > 20% |
| Constant | 1 distinct value |
| Numeric as text | ≥ 95% of values parse as numbers |

Warning texts are server messages: wrap them in `tr()` and add the Spanish entry to `locales/es.py`.

## Remote sources
Never profile a full Teradata table. Sample it (`SAMPLE 100000`) and mark the result with
`sampled: true` and the size. The UI must show it.

## Correlations
Pearson and Spearman between numeric columns, only if there are ≤ 50 numeric columns; report the `n` used.
Do not imply causality in UI texts.
