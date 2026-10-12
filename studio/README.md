# studio

Frontend del autor. Se crea en la Fase 0 de `PLAN.md`:

```bash
npm create vite@latest . -- --template react-ts
npm i @tanstack/react-query zustand echarts
npm i -D openapi-typescript
```

Script `gen:api`: `openapi-typescript http://localhost:8000/openapi.json -o src/generated/api.ts`.
El JSON Schema del contrato se genera en `src/generated/spec.schema.json` desde el backend
(`python -m data2html.spec.export`). No edites nada en `src/generated/` a mano.
