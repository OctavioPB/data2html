# ADR 0008 — Versioned content in `content/` and RLS in the author's preview

**Status:** accepted · 2026-10-12

## Context
Phase 5 introduces semantic models edited from the studio; Phase 6 will do the same with reports.
We need to decide where they live and how RLS behaves when the one querying is the author.

## Decision
1. **Models and reports are versioned content**: `content/semantic/<name>.yaml` (and in Phase 6
   `content/reports/<id>.yaml`), in the repo, configurable with `D2H_CONTENT_DIR`. Data (`data/`:
   Parquet, SQL history, catalog metadata) stays out of git.
2. **The studio writes validated YAML**: `PUT /api/semantic/{name}` only saves if the model passes the
   contract **and** the check against the real catalog (each measure runs with `WHERE false`).
3. **RLS is never skipped by default**: `build_visual_query` requires the reader's identity if the model
   declares `rls`. The only exception is an explicit `author_preview=True`, used only by the studio
   (single user). The viewer (Phase 6) always passes the identity and never that flag.

## Consequences
- A measure change lands in git history, with its diff and author.
- Saving from the studio updates the YAML in place (round-trip with `ruamel.yaml`, 2026-10-12): hand-written
  comments, key order and flow style survive; visuals are matched by `id`; defaults are not written.
- Aggregating in Postgres with `postgres_query()` is postponed to Phase 7: it takes SQL as text, without
  parameters, and would force embedding values. It will be designed together with native Teradata execution.
