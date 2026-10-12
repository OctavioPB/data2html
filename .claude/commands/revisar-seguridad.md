Revisa seguridad de los cambios actuales (o de $ARGUMENTS si se indican rutas).

Usa la skill `security-rls`. Para cada invariante, responde Cumple / No cumple / No aplica con
la línea de código que lo demuestra:
1. Identidad solo desde auth/.  2. Caché con identidad en la clave.  3. Sin datos de otra
identidad en respuestas o HTML.  4. PROXYUSER validado.  5. Filtro RLS presente si el modelo lo
declara.  6. Sin secretos en código, YAML ni logs.  7. SQL libre limitado a un único SELECT.
8. Escapado de JSON y celdas en HTML.  9. IA con identidad y nivel de exposición.

Termina con una lista de hallazgos ordenada por severidad. No corrijas nada sin preguntarme.
