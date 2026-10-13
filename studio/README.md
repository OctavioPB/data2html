# studio

The author's frontend: Vite + React + TypeScript, TanStack Query (server state) and
Zustand (UI state).

```bash
npm install
npm run dev        # http://localhost:5173 ; /api and /health are proxied to the backend on :8000
npm run build
npm run lint       # oxlint
```

## Generated code (`src/generated/`, not edited by hand)

| File | Source |
|---|---|
| `spec.schema.json` | `python -m data2html.spec.export` (from `backend/`) |
| `openapi.json` | `python -m data2html.api.openapi` (from `backend/`) |
| `api.ts` | `npm run gen:api` (from `openapi.json`; `gen:api:live` takes it from the running server) |

The backend tests fail if `spec.schema.json` or `openapi.json` fall out of date, and CI fails
if `api.ts` does not match `openapi.json`. When changing the API: dump the OpenAPI and run `gen:api`.

## Languages (`src/i18n/`)

- `en.ts` is the source of truth (`MessageKey`); `es.ts` is typed as `Record<MessageKey, string>`, so a
  missing or extra Spanish key is a build error. Placeholders use `{name}`.
- Components use `useT()` (re-renders on language change); non-React code uses `t()`.
- The initial language follows the browser (`es*` → Spanish, otherwise English) and the choice is stored
  in `localStorage` (`d2h.lang`). Numbers and dates are formatted with `src/i18n/format.ts`.
- Every API request sends `Accept-Language`; switching language invalidates the query cache so server
  messages (warnings, errors) come back in the new language.

## Reports (Phase 6)

*Reports* lists the published reports (`content/reports/`); the editor arranges visuals on a 12-column grid
(react-grid-layout) and edits parameters and access groups. «Add to report…» in the visual builder appends
the current visual. Saving validates on the server and publishes; «Open viewer» opens `/r/<id>` (proxied to
the backend in development, like `/dev/login`).

## Pinned versions

- TypeScript `~5.9`: `openapi-typescript` 7 does not support TS 6 yet.
- react-grid-layout `~2.2.4` (2.3.0 was only a week old when added).
- React `18.3`: Glide Data Grid 6.0.3 (stable) declares React ≤ 18; its React 19 support only exists in
  6.0.4-alpha. Move to React 19 when a stable 6.x that declares it ships.

## Lazy loading

The SQL editor (CodeMirror + ECharts, ~1 MB) is a separate chunk: it is only downloaded when `#/sql` opens.

## 5M-row demo (Phase 2)

```bash
cd backend && python -m data2html.devtools demo     # data/csv/demo_ventas.parquet
```

Open `http://localhost:5173/#/csv/demo_ventas`. The grid requests 200-row pages as you scroll.
