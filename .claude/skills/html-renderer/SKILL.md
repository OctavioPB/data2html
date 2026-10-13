---
name: html-renderer
description: Use when working on HTML report rendering (backend/src/data2html/render/), Jinja2 templates, viewer.js, ECharts, the chart-type selector or the /r/<id> viewer.
---

# HTML renderer

## Viewer HTML contract
- The HTML carries no data on load: it carries the layout, the visuals (spec) and the `allowed_marks`
  of each one. Data is requested per visual from `/api/r/<report>/visuals/<visual>` with the session.
- One selector per visual with only the allowed marks. Changing the mark redraws with the same
  data; there is no new query.
- `table` is drawn with the DOM (`textContent`), the rest with ECharts (canvas). Code: `render/html.py`,
  `render/templates/`, `render/static/viewer.js` (plain JS, no build step) and `api/viewer.py`.
- No `innerHTML` and no inline styles in markup (the CSP forbids them): tooltips are DOM built with
  `textContent`, styles go through CSSOM (`el.style.x = …`).
- Mapping: `bar` → `type: 'bar'`; `line` → `type: 'line'`; `pie` → `type: 'pie'` with
  `{name: dim, value: measure}`; `kpi` → number formatted according to `Measure.format`.
- Data arrives aggregated: do not aggregate again on the client.
- Temporal dimensions with a `time_grain` are labelled by period ("ene 2025", "T1 2025"; UTC); the raw value
  stays for cross-filters. Snapshot reports show "Data as of …" (`as_of`) on each card.
- Each card offers CSV (`/api/r/<id>/visuals/<v>.csv`, same query string as the JSON) and PNG
  (`chart.getDataURL`, charts only; tables and KPIs download as CSV).

## Theme
Colors, font and currency from `config/theme.yaml` (`render/theme.py`): one palette for light and one for
dark, both validated with the dataviz skill. Respect `prefers-color-scheme`.

## Language
The viewer's chrome (selector, empty states, errors) follows the reader's language, like the studio: both
languages travel in the page (`render/strings.py`, `tr()` msgids) and API calls send `Accept-Language`.
Report content (titles, descriptions, data) is shown as authored.

## Inherited from pbix2html
Its `render.py` (Jinja2 + ECharts, absolute .pbix layout) is the reference. Here the layout is a
12-column grid (`Layout.x/y/w/h`). Convert absolute positions in the importer, not in the renderer.
