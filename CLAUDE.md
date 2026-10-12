# data2html — De los datos al reporte HTML, sin Power BI

App web propia para **EDA, consulta SQL y visualización** (Excel + Power BI + SQL en una sola
herramienta) que publica **reportes HTML servidos en vivo** con seguridad por fila.

- **Backend:** FastAPI sobre Uvicorn, Python 3.12, DuckDB, SQLGlot, Pydantic v2.
- **Frontend (studio):** React + Vite + TypeScript.
- **Fuentes:** CSV (subida), Postgres, MySQL, Teradata, DynamoDB (vía export a S3).
- **Origen:** sucede a `pbix2html`. Su motor (query/render/serve) se trae aquí por fases
  (ver `backend/src/data2html/importers/pbix/README.md`); su extractor queda como importador.
  pbix2html sigue operando hasta el corte: no lo modifiques desde este repo.

Lee `PLAN.md` para saber en qué fase estamos. Lee `docs/ARCHITECTURE.md` antes de tocar más
de un módulo. Las decisiones cerradas están en `docs/decisions/` — no las reabras sin un ADR nuevo.

## Modelo mental (no lo rompas)

```
Studio (autor único) ──► report-spec (YAML/JSON validado) ──► engine ──► HTML en vivo (lectores)
Importador pbix ───────┘         ▲
                         modelo semántico (medidas definidas UNA vez)
```

1. **El `report-spec` es el contrato.** Lo producen el studio, el importador pbix y (más tarde) la IA.
   Lo consume el engine. Vive en `backend/src/data2html/spec/`. Si cambias el contrato, cambia
   también el JSON Schema exportado, los ejemplos en `examples/` y los tests.
2. **Las medidas se definen en el modelo semántico, nunca en el visual.** Un visual referencia
   `measure: venta_neta` por nombre. Prohibido SQL de medida embebido en un visual.
3. **El navegador nunca recibe datos crudos.** Solo resultados agregados o páginas (`LIMIT`).
4. **SQL se genera en dialecto DuckDB y se transpila con SQLGlot** al dialecto de la fuente.
   Nunca concatenes strings de SQL con valores de usuario: usa parámetros.
5. **Un autor, muchos lectores.** El studio es monousuario. El visor (`/r/...`) es multiusuario con RLS.

## Reglas duras (seguridad)

- **Nunca** un HTML con datos de más de un rol/usuario. Cada respuesta del visor se calcula con
  la identidad del lector.
- RLS de Teradata: sesión de confianza con `PROXYUSER` vía `SET QUERY_BAND`. La identidad viene
  del proveedor de auth (OIDC o login local), **nunca** de un parámetro de la petición.
- Conexiones a fuentes: usuarios de base de datos con solo `SELECT`. Además, todo SQL libre se
  parsea con SQLGlot y se rechaza si no es un único `SELECT`.
- Credenciales: solo en variables de entorno / vault. Jamás en YAML del repo, logs ni respuestas.
- DuckDB del servidor: `enable_external_access=false` salvo en la ingesta, límites de memoria y
  threads, timeout por consulta.
- Datos en HTML: escapar `<`, `>`, `&` en el JSON incrustado; celdas con `textContent`.
- Si la IA está activa, sus herramientas corren con la identidad y el RLS del usuario que pregunta.

## Convenciones

- Python: `ruff` + `mypy --strict` en `spec/`, `semantic/`, `sqlgen/`. Tests con `pytest`.
- Modelos Pydantic con `extra="forbid"`: un campo desconocido es un error, no se ignora.
- Toda fuente implementa `DataSource` (`backend/src/data2html/sources/base.py`) y devuelve Arrow.
- Frontend: tipos generados desde OpenAPI (`npm run gen:api`); no escribas tipos de la API a mano.
- Licencias: solo permisivas (MIT/Apache/BSD). Prohibido GPL o comerciales sin un ADR.
- Nombres de modelos de IA y credenciales: siempre en configuración, nunca en código.

## Cómo trabajar conmigo

- Una fase a la vez; marca casillas en `PLAN.md` al terminar y agrega la fecha.
- Antes de implementar algo que toque el contrato, la seguridad o una fuente nueva, muéstrame
  el diseño (archivos a tocar + interfaz) y espera mi visto bueno.
- Antes de ejecutar cualquier cosa contra Teradata real, pídeme confirmación.
- Usa las skills de `.claude/skills/` para su dominio. Comandos: `/fase`, `/nueva-fuente`,
  `/nuevo-visual`, `/revisar-seguridad`.

## Comandos

```bash
docker compose up -d postgres          # fuente de desarrollo
cd backend && pip install -e ".[dev]" && pytest -q
uvicorn data2html.api.main:app --reload
cd studio && npm install && npm run dev
```
