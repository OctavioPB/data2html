# ADR 0004 — Las medidas viven en el modelo semántico

**Estado:** aceptada · 2026-10-11

## Contexto
Sin Power BI desaparece su modelo semántico. pbix2html aplanó a "un SQL por visual", válido
para migrar (había referencia contra la cual validar) pero no para reportes nuevos.

## Decisión
Un visual referencia `measure: <nombre>`. La expresión SQL, el formato, el dueño y la
descripción se definen una sola vez en `SemanticModel`.

## Consecuencias
- Una medida da el mismo número en todos los reportes.
- El importador pbix debe consolidar los SQL migrados en medidas y señalar las definiciones
  casi duplicadas: ese hallazgo es un entregable, no un error del importador.
