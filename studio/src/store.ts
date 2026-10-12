import { create } from 'zustand'

import type { Schemas } from './api/client'

export interface TableRef {
  source: string
  table: string
}

export type Tab = 'data' | 'profile' | 'schema'
export type View = 'table' | 'sql' | 'models'
export type VisualDraft = Schemas['VisualDraft']

/** Estado de UI del studio. Los datos del servidor viven en TanStack Query, no aquí. */
interface StudioState {
  view: View
  /** Modelo abierto en la vista "Modelos"; '' = nuevo. */
  model: string | null
  /** Visual inicial del constructor (p. ej. al publicar desde el editor SQL). */
  builderPreset: VisualDraft | null
  selected: TableRef | null
  tab: Tab
  uploading: boolean
  select: (ref: TableRef | null) => void
  setTab: (tab: Tab) => void
  openSql: () => void
  openModels: (model?: string | null, preset?: VisualDraft | null) => void
  setUploading: (open: boolean) => void
}

// En la URL la pestaña va en español: #/fuente/tabla/perfil
const TAB_SLUG: Record<Tab, string> = { data: 'datos', profile: 'perfil', schema: 'esquema' }
const SLUG_TAB = Object.fromEntries(Object.entries(TAB_SLUG).map(([t, s]) => [s, t])) as Record<string, Tab>

/** `#/fuente/tabla[/pestaña]`, `#/sql` o `#/modelos[/nombre]`: la vista sobrevive a recargas y se enlaza. */
function fromHash(): { view: View; selected: TableRef | null; tab: Tab; model: string | null } {
  const h = window.location.hash
  if (h === '#/sql') return { view: 'sql', selected: null, tab: 'data', model: null }
  const mm = /^#\/modelos(?:\/([a-z][a-z0-9_]*))?$/.exec(h)
  if (mm) return { view: 'models', selected: null, tab: 'data', model: mm[1] ?? null }
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
    window.history.replaceState(null, '', model ? `#/modelos/${model}` : '#/modelos')
    set({ view: 'models', model, builderPreset: preset })
  },
  setTab: (tab) => {
    toHash(get().selected, tab)
    set({ tab })
  },
  setUploading: (uploading) => set({ uploading }),
}))

// Enlaces pegados y atrás/adelante del navegador: la URL manda
window.addEventListener('hashchange', () => useStudio.setState({ ...fromHash(), builderPreset: null }))
