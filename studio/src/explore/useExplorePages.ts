import { useMemo } from 'react'

import { api, type Schemas } from '../api/client'
import { errorMessage } from '../api/queries'
import { usePagedRows, type FetchPage } from './usePagedRows'

export type ExploreQuery = Required<Pick<Schemas['ExploreRequest'], 'sort' | 'filters' | 'search'>>
export type { Cell } from './usePagedRows'

/**
 * Filas del explorador. `query` debe ser estable (memoizada); cambiarla, o `refreshKey`, reinicia todo.
 */
export function useExplorePages(source: string, table: string, query: ExploreQuery, refreshKey = '') {
  const fetcher = useMemo<FetchPage>(
    () => async (offset, limit, withTotal, signal) => {
      const { data, error, response } = await api.POST('/api/explore/{source}/{table}', {
        params: { path: { source, table } },
        body: { ...query, offset, limit, with_total: withTotal },
        signal,
      })
      if (!response.ok || !data) throw new Error(errorMessage(error, response.status))
      return data
    },
    // refreshKey no se usa dentro: solo fuerza un fetcher (y un store) nuevo
    // oxlint-disable-next-line react-hooks/exhaustive-deps
    [source, table, query, refreshKey],
  )
  return usePagedRows(fetcher)
}
