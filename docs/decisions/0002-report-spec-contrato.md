# ADR 0002 — `report-spec` como contrato único

**Estado:** aceptada · 2026-10-11

## Contexto
Hay tres productores de reportes (studio, importador pbix, IA) y un consumidor (engine).

## Decisión
Un contrato Pydantic (`spec/`), `extra="forbid"`, exportado como JSON Schema. YAML en disco.

## Consecuencias
- El engine nunca conoce al productor. La IA recibe el JSON Schema como definición de herramienta.
- Cambiar el contrato exige: tests, ejemplos y schema exportado en el mismo cambio.
