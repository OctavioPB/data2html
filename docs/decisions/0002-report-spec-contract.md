# ADR 0002 — `report-spec` as the single contract

**Status:** accepted · 2026-10-11

## Context
There are three report producers (studio, pbix importer, AI) and one consumer (engine).

## Decision
A Pydantic contract (`spec/`), `extra="forbid"`, exported as JSON Schema. YAML on disk.

## Consequences
- The engine never knows the producer. The AI receives the JSON Schema as a tool definition.
- Changing the contract requires tests, examples and the exported schema in the same change.
