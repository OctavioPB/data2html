---
name: report-spec
description: Usar al crear, modificar o validar reportes, visuales o modelos semánticos de data2html, o al tocar backend/src/data2html/spec/. Cubre el contrato, la compatibilidad de tipos de gráfico y cómo evolucionar el esquema sin romper productores.
---

# El contrato report-spec

Código: `backend/src/data2html/spec/` (`models.py`, `compat.py`, `export.py`).
Ejemplos canónicos: `examples/semantic/*.yaml`, `examples/reports/*.yaml`.

## Reglas
1. Un visual referencia medidas y dimensiones **por nombre**. Si te ves escribiendo SQL dentro
   de un visual, la medida falta en el modelo: agrégala ahí, con `owner` y `description`.
2. `validate_report(report, model)` devuelve errores en español, uno por problema. Úsalo antes
   de guardar cualquier reporte; no publiques con errores.
3. El tipo de gráfico permitido sale solo de `compat.allowed_marks`. No dupliques esas reglas en
   el frontend ni en el renderer: consúmelas (`GET /api/compat` o el JSON incrustado).
4. `table` siempre es válido. `kpi` solo sin dimensión. `line` solo con dimensión temporal u
   ordinal. `pie` solo con dimensión nominal y sin color.

## Cambiar el contrato (checklist)
- [ ] Diseño mostrado al usuario y aprobado (CLAUDE.md: "Cómo trabajar conmigo").
- [ ] Campo nuevo con default si es opcional; nunca renombres un campo sin migración de YAML.
- [ ] Ejemplos de `examples/` actualizados y validando.
- [ ] Test que cubra el caso nuevo y uno que cubra su rechazo.
- [ ] `python -m data2html.spec.export` y commit del schema regenerado.
- [ ] Si afecta a la IA: el schema es su definición de herramienta; revisa la descripción de campos.
