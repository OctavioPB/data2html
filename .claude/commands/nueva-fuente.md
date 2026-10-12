Agrega una fuente de datos nueva: $ARGUMENTS (p. ej. "mysql" o "snowflake").

Sigue la skill `data-sources`:
1. Muéstrame el diseño: clase, dialecto SQLGlot, modo (Import/DirectQuery), cómo aplica RLS,
   variables de entorno que necesita. Espera aprobación.
2. Implementa en `backend/src/data2html/sources/<nombre>.py` cumpliendo `DataSource`.
3. Registra el tipo en `config/sources.example.yaml` (sin secretos) y en `.env.example`.
4. Tests: conformidad con el protocolo, catálogo, execute, snapshot de SQL del dialecto.
5. Ejecuta `/revisar-seguridad` sobre los archivos tocados.
