Agrega un tipo de gráfico (mark) nuevo: $ARGUMENTS (p. ej. "scatter" o "heatmap").

Sigue las skills `report-spec` y `html-renderer`:
1. Define qué encoding exige (dimensiones, medidas, color) y propón la regla en `spec/compat.py`.
   Espera aprobación: cambia el contrato.
2. Agrega el valor a `Mark`, la regla a `allowed_marks` y tests de compatibilidad (acepta y rechaza).
3. Implementa el render en el renderer HTML y en el studio con el mismo mapeo.
4. Regenera el JSON Schema y agrega un visual de ejemplo en `examples/reports/`.
