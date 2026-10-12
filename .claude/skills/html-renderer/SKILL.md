---
name: html-renderer
description: Use when working on HTML report rendering (backend/src/data2html/render/), Jinja2 templates, ECharts, the chart-type selector or the /r/<id> viewer.
---

# HTML renderer

## Viewer HTML contract
- The HTML carries no data on load: it carries the layout, the visuals (spec) and the `allowed_marks`
  of each one. Data is requested per visual from `/api/r/<report>/visuals/<visual>` with the session.
- One selector per visual with only the allowed marks. Changing the mark redraws with the same
  data; there is no new query.
- `table` is drawn with the DOM (`textContent`), the rest with ECharts.
- Mapping: `bar` → `type: 'bar'`; `line` → `type: 'line'`; `pie` → `type: 'pie'` with
  `{name: dim, value: measure}`; `kpi` → number formatted according to `Measure.format`.
- Data arrives aggregated: do not aggregate again on the client.

## Theme
Colors and typography from `config/theme.yaml`. Accessible categorical palette; respect
`prefers-color-scheme`.

## Language
The viewer's chrome (selector, empty states, errors) follows the reader's language, like the studio.
Report content (titles, descriptions, data) is shown as authored.

## Inherited from pbix2html
Its `render.py` (Jinja2 + ECharts, absolute .pbix layout) is the reference. Here the layout is a
12-column grid (`Layout.x/y/w/h`). Convert absolute positions in the importer, not in the renderer.
