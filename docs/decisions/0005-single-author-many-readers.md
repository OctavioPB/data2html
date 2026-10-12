# ADR 0005 — One author, many readers

**Status:** accepted · 2026-10-11

## Decision
The studio is single-user (author). The viewer `/r/<id>` is multi-user, serves live reports
and computes every response with the reader's identity. Auth with `local` and `oidc` providers.

## Consequences
- No real-time collaboration or fine-grained authoring permissions (reopened with an ADR if that changes).
- For Teradata, `PROXYUSER` is only derived from `oidc` identities or from an explicit mapping.
- An HTML containing data from more than one identity is never generated.
