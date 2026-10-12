import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react'

import { api, type Schemas } from '../api/client'

export const PAGE_SIZE = 200

export type ExploreQuery = Required<Pick<Schemas['ExploreRequest'], 'sort' | 'filters' | 'search'>>
export type Cell = Schemas['ExplorePage']['rows'][number][number]
type Column = Schemas['ExploreColumn']

interface Snapshot {
  pages: ReadonlyMap<number, Cell[][]>
  columns: Column[]
  total: number | null
  error: string | null
}

/** Páginas de una consulta concreta. Una instancia por (tabla, consulta): cambiar algo = otra instancia. */
class PageStore {
  private snap: Snapshot = { pages: new Map(), columns: [], total: null, error: null }
  private inflight = new Set<number>()
  private ctrl = new AbortController()
  private listeners = new Set<() => void>()
  private source: string
  private table: string
  private query: ExploreQuery

  constructor(source: string, table: string, query: ExploreQuery) {
    this.source = source
    this.table = table
    this.query = query
  }

  subscribe = (cb: () => void) => {
    this.listeners.add(cb)
    return () => {
      this.listeners.delete(cb)
    }
  }

  getSnapshot = () => this.snap

  private set(patch: Partial<Snapshot>) {
    this.snap = { ...this.snap, ...patch }
    this.listeners.forEach((cb) => cb())
  }

  abort() {
    this.ctrl.abort()
    this.inflight.clear()
  }

  fetchPage(page: number) {
    if (this.snap.pages.has(page) || this.inflight.has(page)) return
    if (this.ctrl.signal.aborted) this.ctrl = new AbortController() // StrictMode monta el efecto dos veces
    const signal = this.ctrl.signal
    this.inflight.add(page)
    const body = { ...this.query, offset: page * PAGE_SIZE, limit: PAGE_SIZE, with_total: page === 0 }
    api
      .POST('/api/explore/{source}/{table}', {
        params: { path: { source: this.source, table: this.table } },
        body,
        signal,
      })
      .then(({ data, error, response }) => {
        if (signal.aborted) return
        this.inflight.delete(page)
        if (!response.ok || !data) {
          const detail = (error as { detail?: unknown } | undefined)?.detail
          this.set({ error: typeof detail === 'string' ? detail : `HTTP ${response.status}` })
          return
        }
        const pages = new Map(this.snap.pages).set(page, data.rows)
        this.set(page === 0 ? { pages, columns: data.columns, total: data.total ?? 0, error: null } : { pages })
      })
      .catch((e: unknown) => {
        if (signal.aborted) return
        this.inflight.delete(page)
        this.set({ error: e instanceof Error ? e.message : String(e) })
      })
  }
}

/**
 * Filas de una tabla bajo demanda: el grid pide el rango visible y aquí se traen las páginas de
 * PAGE_SIZE que falten. Cambiar `query` (o `refreshKey`) descarta todo y cancela lo pendiente.
 * `query` debe ser estable (memoizada) para no recrear el store en cada render.
 */
export function useExplorePages(source: string, table: string, query: ExploreQuery, refreshKey = '') {
  const store = useMemo(
    () => new PageStore(source, table, query),
    // refreshKey no se usa dentro: solo fuerza un store nuevo
    // oxlint-disable-next-line react-hooks/exhaustive-deps
    [source, table, query, refreshKey],
  )
  const snap = useSyncExternalStore(store.subscribe, store.getSnapshot)

  useEffect(() => {
    store.fetchPage(0)
    return () => store.abort()
  }, [store])

  const ensureRange = useCallback(
    (start: number, end: number) => {
      for (let p = Math.floor(start / PAGE_SIZE); p <= Math.floor(end / PAGE_SIZE); p++) store.fetchPage(p)
    },
    [store],
  )

  const { pages } = snap
  const getRow = useCallback(
    (row: number): Cell[] | undefined => pages.get(Math.floor(row / PAGE_SIZE))?.[row % PAGE_SIZE],
    [pages],
  )

  return {
    columns: snap.columns,
    total: snap.total,
    error: snap.error,
    loading: snap.total === null && snap.error === null,
    ensureRange,
    getRow,
  }
}
