# ADR 0001 — DuckDB como motor analítico embebido

**Estado:** aceptada · 2026-10-11

## Contexto
La app combina explorador tipo Excel, perfilado EDA y visuales sobre CSV y bases remotas.
Hacer agregaciones en Pandas no escala más allá de unos cientos de miles de filas.

## Decisión
DuckDB en proceso para CSV/Parquet y como capa de federación hacia Postgres/MySQL
(extensiones `postgres`/`mysql`, `READ_ONLY`).

## Consecuencias
- (+) SQL columnar rápido sin servidor extra; lee CSV/Parquet/Excel de forma nativa.
- (−) Un solo escritor por archivo: una base por proyecto y conexiones por petición.
- (−) No empuja siempre las agregaciones a Postgres/MySQL; ver ADR 0003.
