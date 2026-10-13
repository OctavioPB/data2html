# ADR 0009 — Live viewer: development identities, signed session, per-identity cache

**Status:** accepted · 2026-10-12

## Context
Phase 6 serves published reports to many readers at `/r/<id>`, each one with their own RLS. Real
authentication (local login, OIDC) is planned for Phase 7, but the viewer and its mandatory security test
(two identities, same report, different rows) need an identity now. The report contract also lacked
typed parameters (the viewer could not draw controls or defaults) and a way to restrict who opens a report.

## Decision
1. **One source of identity**: `data2html.auth.current_identity`. Phase 6 implements it with
   *development identities* (`config/dev_identities.yaml`), enabled only with `D2H_DEV_IDENTITIES=1` and
   only for clients in `Settings.dev_hosts` (localhost). The reader picks one at `/dev/login`; Phase 7 adds
   real providers behind the same dependency without touching the viewer.
2. **Signed session cookie** (`d2h_session`, HMAC-SHA256, `HttpOnly`, `SameSite=Strict`, 8 h): it only
   carries the user id and expiry. Groups and email are resolved on every request from the provider, so a
   cookie can never grant groups. Key from `D2H_SESSION_SECRET` (≥ 32 chars) or a random per-process key.
3. **Contract** (approved): `Report.params` accepts `name: type` or `{type, default, label}` with
   `ParamType = int|float|str|date|bool`, and `Report.access` lists the groups allowed to open the report
   (empty = any authenticated reader). `validate_report` checks that a parameter's type fits the dimension
   it filters.
4. **Saving publishes**: the studio writes `content/reports/<id>.yaml` only after validating the report
   and its model against the source (ADR 0008). There is no draft state.
5. **Data endpoint** `GET /api/r/<id>/visuals/<visual>`: only `p.<param>=` (declared, typed) and
   `cf=<dimension>:<value>` query keys; anything else is a 422. Cross-filters are equality filters on
   nominal/ordinal dimensions of the model, ANDed with RLS (they can narrow, never widen). At most 10.
6. **Cache**: in-memory LRU with TTL (`D2H_VIEWER_CACHE_TTL_S`, default 60 s). The key hashes the full
   report and model content, the visual, the **whole identity**, parameters and cross-filters.
7. **HTML**: no data in the page; embedded JSON escapes `<`, `>`, `&`, U+2028/2029; strict CSP
   (`default-src 'none'`, scripts from self and the ECharts CDN with SRI); cells via `textContent`.

## Consequences
- Development identities are a deliberate, local-only shortcut: production must not set
  `D2H_DEV_IDENTITIES=1`. Phase 7 replaces them and protects the studio's routes (author role).
- The cache is per process and its TTL is global; per-source TTLs and a shared cache come with Phase 7's
  deployment work. Content changes invalidate naturally (the content is part of the key).
- Renaming a parameter in the studio does not rename it in the visuals' filters; the server rejects the
  report until they match.
