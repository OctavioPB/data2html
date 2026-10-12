Work on the current PLAN phase. Optional argument: phase number ($ARGUMENTS).

1. Read `PLAN.md` and locate the phase (the given one or the first with unchecked boxes).
2. List the pending items and, for the next one, propose: files to create/touch, public
   interface and tests. If it touches the contract, security or a new source, **wait for my approval**.
3. Implement one item at a time with its test. Run `ruff check`, `mypy` and `pytest -q` in `backend/`
   (and `npm run build` in `studio/` if you touched the frontend).
4. Check the box with the date (YYYY-MM-DD). If the phase is complete, describe how to run
   its **Demo** and update the "Status" line of `PLAN.md`.
5. If an architecture decision came up, propose an ADR in `docs/decisions/`.
