import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react'

import type { Schemas } from '../api/client'

export const PAGE_SIZE = 200

export type Cell = Schemas['ExplorePage']['rows'][number][number]
export type Column = Schemas['ExploreColumn']

export interface Page {
  columns: Column[]
  rows: Cell[][]
  total?: number | null
}

/** Fetch one page. `withTotal` only for the first; `signal` aborts when the query changes. */
export type FetchPage = (offset: number, limit: number, withTotal: boolean, signal: AbortSignal) => Promise<Page>

interface Snapshot {
  pages: ReadonlyMap<number, Cell[][]>
  columns: Column[]
  total: number | null
  error: string | null
}

/** Pages of ONE query. A different query = another instance (and the previous one is aborted). */
class PageStore {
  private snap: Snapshot = { pages: new Map(), columns: [], total: null, error: null }
  private inflight = new Set<number>()
  private ctrl = new AbortController()
  private listeners = new Set<() => void>()
  private fetcher: FetchPage

  constructor(fetcher: FetchPage) {
    this.fetcher = fetcher
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
    if (this.ctrl.signal.aborted) this.ctrl = new AbortController() // StrictMode mounts the effect twice
    const signal = this.ctrl.signal
    this.inflight.add(page)
    this.fetcher(page * PAGE_SIZE, PAGE_SIZE, page === 0, signal)
      .then((data) => {
        if (signal.aborted) return
        this.inflight.delete(page)
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
 * Rows on demand: the grid asks for the visible range and the missing PAGE_SIZE pages are fetched here.
 * A new `fetcher` (memoized by the caller) discards everything and cancels what is pending; `null` = no query.
 */
export function usePagedRows(fetcher: FetchPage | null) {
  const store = useMemo(() => (fetcher ? new PageStore(fetcher) : null), [fetcher])
  const empty = useMemo(() => new PageStore(() => Promise.reject(new Error('no query'))), [])
  const active = store ?? empty
  const snap = useSyncExternalStore(active.subscribe, active.getSnapshot)

  useEffect(() => {
    if (!store) return
    store.fetchPage(0)
    return () => store.abort()
  }, [store])

  const ensureRange = useCallback(
    (start: number, end: number) => {
      for (let p = Math.floor(start / PAGE_SIZE); p <= Math.floor(end / PAGE_SIZE); p++) store?.fetchPage(p)
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
    loading: store !== null && snap.total === null && snap.error === null,
    firstPage: pages.get(0) ?? null,
    ensureRange,
    getRow,
  }
}
