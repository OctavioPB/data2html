Add a new data source: $ARGUMENTS (e.g. "mysql" or "snowflake").

Follow the `data-sources` skill:
1. Show me the design: class, SQLGlot dialect, mode (Import/DirectQuery), how it applies RLS,
   environment variables it needs. Wait for approval.
2. Implement it in `backend/src/data2html/sources/<name>.py`, satisfying `DataSource`.
3. Register the type in `config/sources.example.yaml` (no secrets) and in `.env.example`.
4. Tests: protocol conformance, catalog, execute, SQL snapshot for the dialect.
5. Run `/review-security` over the touched files.
