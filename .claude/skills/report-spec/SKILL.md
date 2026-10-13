---
name: report-spec
description: Use when creating, modifying or validating data2html reports, visuals or semantic models, or when touching backend/src/data2html/spec/. Covers the contract, chart-type compatibility and how to evolve the schema without breaking producers.
---

# The report-spec contract

Code: `backend/src/data2html/spec/` (`models.py`, `compat.py`, `export.py`).
Canonical examples: `examples/semantic/*.yaml`, `examples/reports/*.yaml`.

## Rules
1. A visual references measures and dimensions **by name**. If you find yourself writing SQL inside
   a visual, the measure is missing from the model: add it there, with `owner` and `description`.
2. `validate_report(report, model)` returns errors in the request language (English by default,
   via `tr()`), one per problem. Use it before saving any report; do not publish with errors.
3. The allowed chart type comes only from `compat.allowed_marks`. Do not duplicate those rules in
   the frontend or the renderer: consume them (`GET /api/compat` or the embedded JSON).
4. `table` is always valid. `kpi` only without a dimension. `line` only with a temporal or ordinal
   dimension. `pie` only with a nominal dimension and no color.
5. Report parameters are typed (`name: date` or `{type, default, label}`; `int|float|str|date|bool`) and must
   fit the dimension they filter (temporal → date; quantitative → int/float). `access` lists the groups that
   can open the report (empty = any authenticated reader); RLS still filters rows. Read them with
   `Report.param(name)`, which expands the shorthand.
6. `mode: snapshot` keeps each reader's data (with their RLS) until the report is republished or
   `refresh_hours` pass (`refresh_hours` is only valid with `snapshot`). Snapshots are per identity, never shared.
7. A dimension may name an explorer computed column of its table (its expression is expanded in the SQL);
   the RLS column and measures use physical columns only.

## Changing the contract (checklist)
- [ ] Design shown to the user and approved (CLAUDE.md: "Working with me").
- [ ] New field with a default if optional; never rename a field without a YAML migration.
- [ ] `examples/` updated and validating.
- [ ] A test covering the new case and one covering its rejection.
- [ ] `python -m data2html.spec.export` and commit the regenerated schema.
- [ ] If it affects the AI: the schema is its tool definition; review the field descriptions.
