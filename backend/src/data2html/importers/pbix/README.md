# Importador pbix (Fase 7)

Trae aquí desde el repo `pbix2html`:

| pbix2html | destino en data2html |
|---|---|
| `extract.py`, `semantic.py` | `importers/pbix/` (salida: `SemanticModel` + `Report`) |
| `query.py` (Teradata, PROXYUSER) | `sources/teradata.py` cumpliendo `DataSource` |
| `render.py` + plantilla | `render/` (grilla de 12 columnas en vez de layout absoluto) |
| `serve.py` | `api/` rutas del visor `/r/<id>` |
| `validate.py` | `tests/` de paridad para reportes migrados |
| `metrics/<R>.yaml` | entrada del importador; sus SQL validados siembran medidas |

## Consolidación de medidas
Cada `sql` por visual se descompone en (dimensión, medida). Medidas con la misma expresión
normalizada (AST de SQLGlot) se fusionan; las casi iguales se listan en
`out/<reporte>.medidas_conflicto.md` para que el dueño decida. No las fusiones en silencio.

## Conversión de layout
Posiciones absolutas del .pbix → `Layout(x, y, w, h)` en grilla de 12 columnas, redondeando y
preservando el orden de lectura (arriba-abajo, izquierda-derecha).
