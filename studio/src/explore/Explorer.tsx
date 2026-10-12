import { useEffect, useMemo, useState } from 'react'

import type { Schemas } from '../api/client'
import { ComputedColumns } from './ComputedColumns'
import { ExploreGrid } from './ExploreGrid'
import { FilterBar } from './FilterBar'
import { useExplorePages, type ExploreQuery } from './useExplorePages'

const EMPTY: ExploreQuery = { sort: [], filters: [], search: '' }
const nf = new Intl.NumberFormat('es-MX')

interface Props {
  source: string
  table: Schemas['TableOut']
}

export function Explorer({ source, table }: Props) {
  const [rawQuery, setQuery] = useState<ExploreQuery>(EMPTY)
  const [searchDraft, setSearchDraft] = useState('')

  // búsqueda con espera: no lanzar una consulta por tecla
  useEffect(() => {
    const t = setTimeout(() => setQuery((q) => (q.search === searchDraft ? q : { ...q, search: searchDraft })), 300)
    return () => clearTimeout(t)
  }, [searchDraft])

  // Si se borró una columna calculada usada en filtros u orden, ignorarla en la consulta
  const query = useMemo(() => {
    const names = new Set([...table.columns.map((c) => c.name), ...table.computed.map((c) => c.name)])
    return {
      ...rawQuery,
      filters: rawQuery.filters.filter((f) => names.has(f.column)),
      sort: rawQuery.sort.filter((s) => names.has(s.column)),
    }
  }, [rawQuery, table.columns, table.computed])

  // Al cambiar las columnas calculadas, recargar (puede haber columnas nuevas o borradas)
  const refreshKey = table.computed.map((c) => `${c.name}=${c.expr}`).join('|')
  const data = useExplorePages(source, table.name, query, refreshKey)

  const filtered = query.filters.length > 0 || query.search !== ''

  return (
    <div className="explorer">
      <div className="explorer-toolbar">
        <input
          type="search"
          className="search"
          placeholder="Buscar en columnas de texto…"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          aria-label="Buscar"
        />
        <FilterBar
          columns={data.columns}
          filters={query.filters}
          onChange={(filters) => setQuery({ ...query, filters })}
        />
        <span className="muted small count">
          {data.loading
            ? 'Cargando…'
            : data.total !== null &&
              `${nf.format(data.total)} filas${filtered ? ` de ${nf.format(table.row_count ?? 0)}` : ''}`}
        </span>
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
