# ADR 0010 — Authentication: local and OIDC sign-in, server-side sessions, author role, CSRF

**Status:** accepted · 2026-10-12

## Context
Phase 6 served the viewer with development identities (ADR 0009) and left the studio's API open to anyone
who could reach the server, including free SQL. Phase 7 needs real readers (corporate SSO: Microsoft
Entra ID), a protected studio, and identities that can carry the Teradata PROXYUSER.

## Decision
1. **Providers** behind the single `auth.current_identity` dependency:
   - `local`: `config/users.yaml` (ignored by git), scrypt hashes (stdlib), created with
     `python -m data2html.auth add-user`. Throttled: 5 failures per user and per client address in 15 min.
   - `oidc`: authorization code + PKCE (S256), implemented with httpx and **joserfc** (BSD-3) for the
     `id_token`: RS256 only, JWKS signature, `iss`, `aud`, `exp`/`nbf` (60 s leeway) and `nonce`. Authlib was
     considered; its httpx integration is deprecated and the flow is small enough to own.
   - `dev`: development identities, only with `D2H_DEV_IDENTITIES=1` and from localhost (ADR 0009).
2. **Entra ID claims**: App Roles in the `roles` claim feed both `Identity.groups` (report `access`, RLS) and
   the author role (`data2html.author`). The `groups` claim is avoided: opaque ids, and it is dropped from
   the token above 200 groups. `user_id` comes from `oid`. The Teradata user (`Identity.db_user`) comes from a
   configurable claim + transform (default: UPN local part, upper-cased) and must match
   `^[A-Za-z_][A-Za-z0-9_$#]{0,127}$`; otherwise it is `None` and the identity gets no Teradata data.
3. **Server-side sessions** in SQLite (`data/sessions.sqlite`, shared by workers). The cookie carries a
   random id (signed with `D2H_SESSION_SECRET`), `HttpOnly`, `SameSite=Strict`, `Secure` on https; the
   database stores only its SHA-256. Sign-out deletes the row (real revocation). `local` and `dev` identities
   are re-read from their files on every request; `oidc` ones are the snapshot taken at sign-in.
4. **The studio requires the author role** on every route (`require_author`); `/health` and the viewer
   (any authenticated reader, plus report `access`) are the only other entry points.
5. **CSRF**: besides `SameSite=Strict`, every state-changing request with an `Origin` header must come from
   the request's own origin (or `D2H_PUBLIC_URL` / `trusted_origins`). Pages use
   `Referrer-Policy: same-origin` (with `no-referrer`, browsers send `Origin: null` and our own forms would
   be refused). The dev proxy keeps the `Host` header (`changeOrigin: false`).
6. **OIDC callback**: the provider's redirect is a cross-site navigation, so a `SameSite=Strict` cookie set
   there would not be sent on a chained redirect; the callback answers a small page that continues to the
   target from our own origin.

## Consequences
- Development requires signing in: `D2H_DEV_IDENTITIES=1` and pick `autor`, or create a local user.
- Real Entra ID has not been exercised yet: the flow is tested against a mock provider (discovery, JWKS,
  token endpoint, rotated keys, wrong `aud`/`iss`/`nonce`, expired and foreign-signed tokens).
- OIDC groups and roles change only at the next sign-in (sessions last `session_hours`, default 8).
- The throttle is per process; with several workers the effective limit is per worker.
