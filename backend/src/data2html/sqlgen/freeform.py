"""The editor's free-form SQL: validate, resolve catalog tables and paginate.

The user writes DuckDB-dialect SQL against ONE source, using catalog names (`sales`,
`public.fact_sales`). Here it is validated (`ensure_single_select`, ADR 0007) and every table is
rewritten to its real relation (`postgres_dev.public.fact_sales`). A table that is not in that
source's catalog is an error: a query can touch neither another attached database nor internal objects.
"""

from __future__ import annotations

from sqlglot import exp

from data2html.i18n import tr
from data2html.sqlgen.validate import UnsafeSQL, ensure_single_select

MAX_PAGE = 1000


def _key(parts: list[str]) -> str:
    return ".".join(p.lower() for p in parts)


def _cte_names(q: exp.Expr) -> set[str]:
    return {cte.alias_or_name.lower() for cte in q.find_all(exp.CTE)}


def prepare_user_sql(sql: str, tables: dict[str, tuple[str, ...]]) -> exp.Query:
    """`tables`: catalog name → real relation (`DataSource.relation`). Returns the ready-to-run tree."""
    q = ensure_single_select(sql)
    lookup: dict[str, tuple[str, ...]] = {}
    for name, rel in tables.items():
        lookup[_key(name.split("."))] = rel
        lookup[_key(list(rel))] = rel  # the fully qualified name is accepted too
    ctes = _cte_names(q)

    for t in list(q.find_all(exp.Table)):
        if not isinstance(t.this, exp.Identifier):
            continue  # table function (range, …): ensure_single_select already filtered it
        parts = [p for p in (t.catalog, t.db, t.name) if p]
        if len(parts) == 1 and parts[0].lower() in ctes:
            continue
        found = lookup.get(_key(parts))
        if found is None:
            raise UnsafeSQL(tr("unknown table in this source: {name}", name=".".join(parts)))
        *qual, ident = (exp.to_identifier(p, quoted=True) for p in found)
        catalog, db = ([None, None] + qual)[-2:]
        t.set("this", ident)
        t.set("db", db)
        t.set("catalog", catalog)
    return q


def page_sql(q: exp.Query, offset: int, limit: int) -> str:
    if not 0 < limit <= MAX_PAGE or offset < 0:
        raise UnsafeSQL(tr("invalid pagination"))
    return exp.select("*").from_(q.subquery("_q")).limit(limit).offset(offset).sql("duckdb")


def count_sql(q: exp.Query) -> str:
    return exp.select(exp.Count(this=exp.Star()).as_("n")).from_(q.subquery("_q")).sql("duckdb")
