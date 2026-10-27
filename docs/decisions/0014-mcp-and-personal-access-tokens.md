# 0014 — Local MCP server and personal access tokens

- Status: accepted
- Date: 2026-10-27

## Context

We want Claude (Claude Desktop, Claude Code) to use data2html: list the semantic models and reports,
and ask for aggregated results ("net sales by region in March"). Claude talks to tools through MCP.
The repo rules apply unchanged: identity only from authentication, every result computed with the RLS
of the person asking, the AI runs with that person's identity, measures defined once in the model,
no raw rows leave the server.

Results returned to an MCP client leave the organisation (they reach the model provider). That is a new
data flow, so it needs an explicit, per-source opt-in.

## Decision

1. **Local MCP server over stdio** (`python -m data2html.mcp`, official `mcp` SDK, MIT). Claude Desktop
   starts it. It holds no data-source credentials and opens no database: it is a thin proxy that calls
   the running backend over HTTP. A remote MCP connector (OAuth 2.1 for claude.ai) is out of scope here.
2. **Personal access tokens** identify the person behind the MCP server:
   - Created by a signed-in person at `/tokens` (any provider: local, OIDC, development) or, for local
     users, by an administrator with `python -m data2html.auth token create`.
   - Format `d2h_<random 256 bits>`; only the SHA-256 is stored (`sessions.sqlite`, table `tokens`).
     Shown once. Expiry is required (default 30 days, max 90). Revocable from `/tokens` or the CLI.
   - Resolution mirrors sessions: `local` and `dev` identities are re-read from their files on every
     request (removing a user kills their tokens); `oidc` keeps the identity taken at sign-in until the
     token expires or is revoked; `dev` tokens still need `D2H_DEV_IDENTITIES=1` and a localhost client.
   - **Bearer tokens are accepted only by `/api/agent/*`**, and those routes accept nothing else (no
     cookie). Studio and viewer routes ignore `Authorization`. A leaked token reads, it never edits.
3. **Agent API `/api/agent/*`** (read-only, not in the studio's OpenAPI):
   - `models` and `reports`: what the token's person may read. A reader sees the models used by the
     reports they can read (`access`); the author sees every model. No SQL, table names or RLS rules.
   - `query`: one measure by up to one dimension (+ colour, time grain, equality/range filters),
     built as a visual by `sqlgen`, run with the token's identity — **never** `author_preview`, so the
     author also gets their own RLS. Row cap `max_rows` (default 500).
   - `reports/{id}/visuals/{vid}`: exactly what the person sees at `/r/{id}` (same code path).
   - Author only: `tables` (catalog) and `profile` (EDA).
   - Every call is logged (`data2html.agent`: user, action, target, row count; never values).
4. **Exposure per source** in `config/ai.yaml`: `none` (invisible to the AI), `metadata` (names,
   types and descriptions, no rows), `results` (aggregated results and profiles). **The default is
   `metadata`**: nothing leaves as data until someone opts a source in. A missing file means
   `metadata` everywhere. The `sample` level sketched for Phase 9 (raw sample rows) is left out: it would
   send row-level data, against the "aggregated results only" rule; it needs its own ADR if ever wanted.

## Consequences

- Claude Desktop can answer questions over the semantic models with each person's RLS, with no new
  credentials on the client beyond a revocable, expiring token.
- Results Claude receives are data, not instructions; there are no write tools, so text inside a cell
  cannot make Claude change anything in data2html. Writing (draft reports proposed by Claude) needs a
  draft state first and a later ADR.
- An OIDC token keeps the roles of its sign-in until it expires: removing someone in Entra ID does not
  revoke it. Hence the 90-day cap and revocation; the remote connector (OAuth with short-lived tokens)
  will remove this gap.
- New dependency (optional extra `mcp`): `mcp` (MIT) and its tree (Starlette BSD, pydantic MIT,
  pywin32 PSF on Windows, OpenTelemetry API Apache-2.0). Only the MCP process imports it.
