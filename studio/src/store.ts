import { create } from 'zustand'

export interface TableRef {
  source: string
  table: string
}

export type Tab = 'data' | 'schema'

/** Estado de UI del studio. Los datos del servidor viven en TanStack Query, no aquí. */
interface StudioState {
  selected: TableRef | null
  tab: Tab
  uploading: boolean
  select: (ref: TableRef | null) => void
  setTab: (tab: Tab) => void
  setUploading: (open: boolean) => void
}

/** `#/fuente/tabla`: la tabla abierta sobrevive a recargas y se puede enlazar. */
function fromHash(): TableRef | null {
  const m = /^#\/([^/]+)\/([^/]+)$/.exec(window.location.hash)
  return m ? { source: decodeURIComponent(m[1]), table: decodeURIComponent(m[2]) } : null
}

function toHash(ref: TableRef | null) {
  const hash = ref ? `#/${encodeURIComponent(ref.source)}/${encodeURIComponent(ref.table)}` : ''
  window.history.replaceState(null, '', hash || window.location.pathname)
}

export const useStudio = create<StudioState>((set) => ({
  selected: fromHash(),
  tab: 'data',
  uploading: false,
  select: (selected) => {
    toHash(selected)
    set({ selected })
  },
  setTab: (tab) => set({ tab }),
  setUploading: (uploading) => set({ uploading }),
}))
