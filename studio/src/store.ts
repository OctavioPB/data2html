import { create } from 'zustand'

import type { Schemas } from './api/client'

export interface TableRef {
  source: string
  table: string
}

export type Tab = 'data' | 'profile' | 'schema'
export type View = 'table' | 'sql' | 'models' | 'reports'
export type VisualDraft = Schemas['VisualDraft']

/** Studio UI state. Server data lives in TanStack Query, not here. */
interface StudioState {
  view: View
  /** Model open in the "Models" view; '' = new. */
  model: string | null
  /** Report open in the "Reports" view; '' = new. */
  report: string | null
  /** Initial visual of the builder (e.g. when publishing from the SQL editor). */
  builderPreset: VisualDraft | null
  selected: TableRef | null
  tab: Tab
  uploading: boolean
  select: (ref: TableRef | null) => void
  setTab: (tab: Tab) => void
  openSql: () => void
  openModels: (model?: string | null, preset?: VisualDraft | null) => void
  openReports: (report?: string | null) => void
  setUploading: (open: boolean) => void
}

// URL slugs are language-neutral (English); the Spanish ones from earlier links are still accepted
const TAB_SLUG: Record<Tab, string> = { data: 'data', profile: 'profile', schema: 'schema' }
const SLUG_TAB: Record<string, Tab> = {
  data: 'data', profile: 'profile', schema: 'schema',
  datos: 'data', perfil: 'profile', esquema: 'schema',
}

const REPORTS_HASH = new RegExp('^#/(?:reports|reportes)(?:/([a-z][a-z0-9_]*))?$')

/** Report id in `#/reports/<id>`; null for the list (and any other view). */
function reportFromHash(): string | null {
  return REPORTS_HASH.exec(window.location.hash)?.[1] ?? null
}

/** `#/source/table[/tab]`, `#/sql`, `#/models[/name]` or `#/reports[/id]`: the view survives reloads and
 * can be linked. */
function fromHash(): { view: View; selected: TableRef | null; tab: Tab; model: string | null } {
  const h = window.location.hash
  if (h === '#/sql') return { view: 'sql', selected: null, tab: 'data', model: null }
  const mm = /^#\/(?:models|modelos)(?:\/([a-z][a-z0-9_]*))?$/.exec(h)
  if (mm) return { view: 'models', selected: null, tab: 'data', model: mm[1] ?? null }
  if (REPORTS_HASH.test(h)) return { view: 'reports', selected: null, tab: 'data', model: null }
  const m = /^#\/([^/]+)\/([^/]+)(?:\/([a-z]+))?$/.exec(window.location.hash)
  if (!m) return { view: 'table', selected: null, tab: 'data', model: null }
  return {
    view: 'table',
    selected: { source: decodeURIComponent(m[1]), table: decodeURIComponent(m[2]) },
    tab: SLUG_TAB[m[3] ?? ''] ?? 'data',
    model: null,
  }
}

function toHash(ref: TableRef | null, tab: Tab) {
  const suffix = tab === 'data' ? '' : `/${TAB_SLUG[tab]}`
  const hash = ref ? `#/${encodeURIComponent(ref.source)}/${encodeURIComponent(ref.table)}${suffix}` : ''
  window.history.replaceState(null, '', hash || window.location.pathname)
}

export const useStudio = create<StudioState>((set, get) => ({
  ...fromHash(),
  report: reportFromHash(),
  builderPreset: null,
  uploading: false,
  select: (selected) => {
    toHash(selected, get().tab)
    set({ selected, view: 'table' })
  },
  openSql: () => {
    window.history.replaceState(null, '', '#/sql')
    set({ view: 'sql' })
  },
  openModels: (model = null, preset = null) => {
    window.history.replaceState(null, '', model ? `#/models/${model}` : '#/models')
    set({ view: 'models', model, builderPreset: preset })
  },
  openReports: (report = null) => {
    window.history.replaceState(null, '', report ? `#/reports/${report}` : '#/reports')
    set({ view: 'reports', report })
  },
  setTab: (tab) => {
    toHash(get().selected, tab)
    set({ tab })
  },
  setUploading: (uploading) => set({ uploading }),
}))

// Pasted links and the browser's back/forward: the URL wins
window.addEventListener('hashchange', () => useStudio.setState({ ...fromHash(), report: reportFromHash(), builderPreset: null }))
