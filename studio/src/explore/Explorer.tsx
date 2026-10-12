import { useEffect, useMemo, useState } from 'react'

import type { Schemas } from '../api/client'
import { useT } from '../i18n'
import { formatNumber } from '../i18n/format'
import { ComputedColumns } from './ComputedColumns'
import { ExploreGrid } from './ExploreGrid'
import { FilterBar } from './FilterBar'
import { useExplorePages, type ExploreQuery } from './useExplorePages'

const EMPTY: ExploreQuery = { sort: [], filters: [], search: '' }

interface Props {
  source: string
  table: Schemas['TableOut']
}

export function Explorer({ source, table }: Props) {
  const t = useT()
  const [rawQuery, setQuery] = useState<ExploreQuery>(EMPTY)
  const [searchDraft, setSearchDraft] = useState('')

  // debounced search: do not fire one query per keystroke
  useEffect(() => {
    const timer = setTimeout(
      () => setQuery((q) => (q.search === searchDraft ? q : { ...q, search: searchDraft })),
      300,
    )
    return () => clearTimeout(timer)
  }, [searchDraft])

  // If a computed column used in filters or sorting was deleted, ignore it in the query
  const query = useMemo(() => {
    const names = new Set([...table.columns.map((c) => c.name), ...table.computed.map((c) => c.name)])
    return {
      ...rawQuery,
      filters: rawQuery.filters.filter((f) => names.has(f.column)),
      sort: rawQuery.sort.filter((s) => names.has(s.column)),
    }
  }, [rawQuery, table.columns, table.computed])

  // When the computed columns change, reload (there may be new or deleted columns)
  const refreshKey = table.computed.map((c) => `${c.name}=${c.expr}`).join('|')
  const data = useExplorePages(source, table.name, query, refreshKey)

  const filtered = query.filters.length > 0 || query.search !== ''
  const count =
    data.total === null
      ? null
      : filtered && table.row_count !== null
        ? t('explore.rowsOf', { n: formatNumber(data.total), total: formatNumber(table.row_count) })
        : t('common.rows', { n: formatNumber(data.total) })

  return (
    <div className="explorer">
      <div className="explorer-toolbar">
        <input
          type="search"
          className="search"
          placeholder={t('explore.searchPlaceholder')}
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          aria-label={t('explore.search')}
        />
        <FilterBar
          columns={data.columns}
          filters={query.filters}
          onChange={(filters) => setQuery({ ...query, filters })}
        />
        <span className="muted small count">{data.loading ? t('common.loading') : count}</span>
      </div>
      <ComputedColumns source={source} table={table.name} computed={table.computed} />
      {data.error && <p className="error">{data.error}</p>}
      <div className="grid-wrap">
        {data.columns.length > 0 && (
          <div className="grid-fill">
            <ExploreGrid
              columns={data.columns}
              rows={data.total ?? 0}
              getRow={data.getRow}
              ensureRange={data.ensureRange}
              sort={query.sort}
              onSort={(sort) => setQuery({ ...query, sort })}
            />
          </div>
        )}
      </div>
    </div>
  )
}
