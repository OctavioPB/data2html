# studio

Frontend del autor: Vite + React + TypeScript, TanStack Query (estado del servidor) y
Zustand (estado de UI).

```bash
npm install
npm run dev        # http://localhost:5173 ; /api y /health se redirigen al backend en :8000
npm run build
npm run lint       # oxlint
```

## Código generado (`src/generated/`, no se edita a mano)

| Archivo | Origen |
|---|---|
| `spec.schema.json` | `python -m data2html.spec.export` (desde `backend/`) |
| `openapi.json` | `python -m data2html.api.openapi` (desde `backend/`) |
| `api.ts` | `npm run gen:api` (desde `openapi.json`; `gen:api:live` lo toma del servidor corriendo) |

Los tests del backend fallan si `spec.schema.json` u `openapi.json` quedan desfasados, y CI falla
si `api.ts` no corresponde a `openapi.json`. Al cambiar la API: vuelca el OpenAPI y corre `gen:api`.

## Versiones fijadas

- TypeScript `~5.9`: `openapi-typescript` 7 aún no admite TS 6.
- React `18.3`: Glide Data Grid 6.0.3 (estable) declara React ≤ 18; su soporte de React 19 solo existe en
  la 6.0.4-alpha. Subir a React 19 cuando salga una 6.x estable que lo declare.

## Carga diferida

El editor SQL (CodeMirror + ECharts, ~1 MB) es un chunk aparte: solo se descarga al abrir `#/sql`.

## Demo de 5M filas (Fase 2)

```bash
cd backend && python -m data2html.devtools demo     # data/csv/demo_ventas.parquet
```

Abre `http://localhost:5173/#/csv/demo_ventas`. El grid pide páginas de 200 filas conforme se desplaza.
