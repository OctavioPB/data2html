import type { SQLNamespace } from '@codemirror/lang-sql'

import type { Schemas } from '../api/client'

/** Autocompletion schema: `public.fact_sales` → { public: { fact_sales: [cols] } }. */
export function schemaFor(tables: Schemas['TableOut'][]): SQLNamespace {
  const ns: Record<string, unknown> = {}
  for (const t of tables) {
    const cols = [...t.columns.map((c) => c.name)]
    const parts = t.name.split('.')
    let node = ns
    parts.slice(0, -1).forEach((p) => {
      node = (node[p] ??= {}) as Record<string, unknown>
    })
    node[parts[parts.length - 1]] = cols
  }
  return ns as SQLNamespace
}
