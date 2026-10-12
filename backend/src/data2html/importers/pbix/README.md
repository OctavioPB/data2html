# pbix importer (Phase 7)

Bring over from the `pbix2html` repo:

| pbix2html | destination in data2html |
|---|---|
| `extract.py`, `semantic.py` | `importers/pbix/` (output: `SemanticModel` + `Report`) |
| `query.py` (Teradata, PROXYUSER) | `sources/teradata.py` satisfying `DataSource` |
| `render.py` + template | `render/` (12-column grid instead of absolute layout) |
| `serve.py` | `api/` routes of the `/r/<id>` viewer |
| `validate.py` | parity `tests/` for migrated reports |
| `metrics/<R>.yaml` | importer input; its validated SQL seeds measures |

## Measure consolidation
Each per-visual `sql` is decomposed into (dimension, measure). Measures with the same normalized
expression (SQLGlot AST) are merged; near-identical ones are listed in
`out/<report>.measure_conflicts.md` for the owner to decide. Do not merge them silently.

## Layout conversion
Absolute .pbix positions → `Layout(x, y, w, h)` on a 12-column grid, rounding and preserving
reading order (top-to-bottom, left-to-right).
