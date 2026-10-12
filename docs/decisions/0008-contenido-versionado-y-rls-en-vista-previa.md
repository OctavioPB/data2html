# ADR 0008 — Contenido versionado en `content/` y RLS en la vista previa del autor

**Estado:** propuesta · 2026-10-11

## Contexto
La Fase 5 introduce modelos semánticos editados desde el studio; la Fase 6 hará lo mismo con reportes.
Hay que decidir dónde viven y cómo se comporta el RLS cuando el que consulta es el autor.

## Decisión
1. **Modelos y reportes son contenido versionado**: `content/semantic/<nombre>.yaml` (y en la Fase 6
   `content/reports/<id>.yaml`), en el repo, configurable con `D2H_CONTENT_DIR`. Los datos (`data/`:
   Parquet, historial SQL, metadatos del catálogo) siguen fuera de git.
2. **El studio escribe YAML validado**: `PUT /api/semantic/{nombre}` solo guarda si el modelo pasa el
   contrato **y** el chequeo contra el catálogo real (cada medida se ejecuta con `WHERE false`).
3. **RLS nunca se omite por defecto**: `build_visual_query` exige la identidad del lector si el modelo
   declara `rls`. La única excepción es `author_preview=True`, explícito, que usa solo el studio
   (monousuario). El visor (Fase 6) siempre pasa la identidad y nunca ese indicador.

## Consecuencias
- Un cambio de medida queda en el historial de git, con su diff y su autor.
- Guardar desde el studio reescribe el YAML: se pierden los comentarios hechos a mano (se conserva una
  cabecera fija). Si eso molesta, la alternativa es editar con un parser que preserve comentarios.
- La agregación en Postgres con `postgres_query()` se pospone a la Fase 7: recibe SQL como texto, sin
  parámetros, y obligaría a incrustar valores. Se diseñará junto con la ejecución nativa de Teradata.
