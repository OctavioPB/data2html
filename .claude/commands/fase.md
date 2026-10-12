Trabaja en la fase actual del PLAN. Argumento opcional: número de fase ($ARGUMENTS).

1. Lee `PLAN.md` y ubica la fase (la indicada o la primera con casillas sin marcar).
2. Lista los puntos pendientes y, para el siguiente, propón: archivos a crear/tocar, interfaz
   pública y tests. Si toca contrato, seguridad o una fuente nueva, **espera mi visto bueno**.
3. Implementa un punto a la vez con su test. Corre `ruff check`, `mypy` y `pytest -q` en `backend/`
   (y `npm run build` en `studio/` si tocaste frontend).
4. Marca la casilla con la fecha (AAAA-MM-DD). Si la fase quedó completa, describe cómo ejecutar
   su **Demo** y actualiza la línea "Estado" de `PLAN.md`.
5. Si surgió una decisión de arquitectura, propón un ADR en `docs/decisions/`.
