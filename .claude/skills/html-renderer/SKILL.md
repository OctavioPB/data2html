---
name: html-renderer
description: Usar al trabajar en el render de reportes HTML (backend/src/data2html/render/), plantillas Jinja2, ECharts, el selector de tipo de gráfico o el visor /r/<id>.
---

# Renderer HTML

## Contrato del HTML del visor
- El HTML no trae datos al cargar: trae el layout, los visuales (spec) y `allowed_marks` de
  cada uno. Los datos se piden por visual a `/api/r/<report>/visuals/<visual>` con la sesión.
- Un selector por visual con solo los marks permitidos. Cambiar el mark re-dibuja con los
  mismos datos; no hay nueva consulta.
- `table` se dibuja con DOM (`textContent`), el resto con ECharts.
- Mapeo: `bar` → `type: 'bar'`; `line` → `type: 'line'`; `pie` → `type: 'pie'` con
  `{name: dim, value: medida}`; `kpi` → número formateado según `Measure.format`.
- Los datos llegan agregados: no agregues de nuevo en el cliente.

## Tema
Colores y tipografía desde `config/theme.yaml`. Paleta categórica accesible; respeta
`prefers-color-scheme`.

## Herencia de pbix2html
Su `render.py` (Jinja2 + ECharts, layout absoluto del .pbix) es la referencia. Aquí el layout
es una grilla de 12 columnas (`Layout.x/y/w/h`). Convierte posiciones absolutas en el importador,
no en el renderer.
