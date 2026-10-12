# ADR 0003 — SQL canónico en DuckDB, transpilado con SQLGlot

**Estado:** aceptada · 2026-10-11

## Decisión
`sqlgen` emite SQL en dialecto DuckDB; SQLGlot lo traduce a `teradata`, `postgres` o `mysql`.
Las agregaciones de modelos DirectQuery se ejecutan completas en la fuente.

## Consecuencias
- Una sola implementación del generador; cada fuente solo declara su dialecto.
- Toda traducción nueva necesita un test con el SQL esperado por dialecto (snapshot).
- SQLGlot también valida el SQL libre del editor: un único `SELECT`.
