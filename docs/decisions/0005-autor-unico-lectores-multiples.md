# ADR 0005 — Un autor, muchos lectores

**Estado:** aceptada · 2026-10-11

## Decisión
El studio es monousuario (autor). El visor `/r/<id>` es multiusuario, sirve reportes en vivo
y calcula cada respuesta con la identidad del lector. Auth con proveedores `local` y `oidc`.

## Consecuencias
- Sin colaboración en tiempo real ni permisos finos de autoría (se reabre con un ADR si cambia).
- Para Teradata, `PROXYUSER` solo se deriva de identidades `oidc` o de un mapeo explícito.
- Nunca se genera un HTML que contenga datos de más de una identidad.
