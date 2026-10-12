# ADR 0006 — Only permissively licensed dependencies

**Status:** accepted · 2026-10-11

## Decision
MIT, Apache-2.0, BSD or equivalent. Chosen: ECharts (Apache), Glide Data Grid (MIT),
CodeMirror 6 (MIT), react-grid-layout (MIT). Rejected: HyperFormula (GPLv3/commercial),
AG Grid Enterprise (commercial).

## Consequences
Keeps open the option of distributing or selling the app. There are no Excel-style cell
formulas: computed columns are SQL expressions.
