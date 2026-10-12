# ADR 0004 — Measures live in the semantic model

**Status:** accepted · 2026-10-11

## Context
Without Power BI, its semantic model disappears. pbix2html flattened everything to "one SQL per
visual", which was fine for migrating (there was a reference to validate against) but not for new reports.

## Decision
A visual references `measure: <name>`. The SQL expression, format, owner and description are
defined once, in `SemanticModel`.

## Consequences
- A measure gives the same number in every report.
- The pbix importer must consolidate the migrated SQL into measures and flag near-duplicate
  definitions: that finding is a deliverable, not an importer error.
