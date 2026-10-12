import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'

import { api, type Schemas } from './client'

async function unwrap<T>(req: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await req
  if (!response.ok) throw new Error(errorMessage(error, response.status))
  return data as T
}

export function errorMessage(error: unknown, status: number): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  // Pydantic validation errors: only the message, without the technical "Value error, " prefix
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => (d.msg ?? '').replace(/^Value error, /, '')).join('; ')
  }
  return `HTTP ${status}`
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => unwrap(api.GET('/health')),
    refetchInterval: 15_000,
    retry: false,
  })
}

export function useCatalog() {
  return useQuery({
    queryKey: ['catalog'],
    queryFn: () => unwrap(api.GET('/api/catalog')),
  })
}

export function useCsvPreview() {
  return useMutation({
    mutationFn: (file: File) =>
      unwrap(
        api.POST('/api/csv/preview', {
          body: { file: '' },
          bodySerializer: () => {
            const form = new FormData()
            form.append('file', file)
            return form
          },
        }),
      ),
  })
}

export function useCsvConfirm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['ConfirmRequest']) => unwrap(api.POST('/api/csv/confirm', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['catalog'] }),
  })
}

export function useCsvDiscard() {
  return useMutation({
    mutationFn: (uploadId: string) =>
      unwrap(api.DELETE('/api/csv/uploads/{upload_id}', { params: { path: { upload_id: uploadId } } })),
  })
}

export function usePatchDescriptions(source: string, table: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['DescriptionsPatch']) =>
      unwrap(api.PATCH('/api/catalog/{source}/{table}', { params: { path: { source, table } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['catalog'] }),
  })
}

export function usePutComputed(source: string, table: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['ComputedIn']) =>
      unwrap(api.PUT('/api/catalog/{source}/{table}/computed', { params: { path: { source, table } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['catalog'] }),
  })
}

export function useDeleteComputed(source: string, table: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.DELETE('/api/catalog/{source}/{table}/computed/{name}', {
          params: { path: { source, table, name } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['catalog'] }),
  })
}

/** EDA profile. `cancel()` stops the computation on the server (POST /api/cancel/{query_id}). */
export function useProfile(source: string, table: string, computedKey: string) {
  const running = useRef<string | null>(null)
  const query = useQuery({
    queryKey: ['profile', source, table, computedKey],
    queryFn: ({ signal }) => {
      const queryId = newQueryId()
      running.current = queryId
      return unwrap(
        api.GET('/api/profile/{source}/{table}', {
          params: { path: { source, table }, query: { query_id: queryId } },
          signal,
        }),
      )
    },
    staleTime: Infinity, // the backend caches; "Recompute" forces it
    retry: false,
  })
  const cancel = () => {
    if (running.current) void cancelJob(running.current)
  }
  return { ...query, cancel }
}

export function useRefreshProfile(source: string, table: string, computedKey: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.GET('/api/profile/{source}/{table}', {
          params: { path: { source, table }, query: { refresh: true } },
        }),
      ),
    onSuccess: (data) => qc.setQueryData(['profile', source, table, computedKey], data),
  })
}

export function useSqlHistory() {
  return useQuery({
    queryKey: ['sql-history'],
    queryFn: () => unwrap(api.GET('/api/sql/history')),
  })
}

export function useSavedQueries() {
  return useQuery({
    queryKey: ['sql-saved'],
    queryFn: () => unwrap(api.GET('/api/sql/saved')),
  })
}

export function useSaveQuery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, ...body }: { name: string } & Schemas['SaveIn']) =>
      unwrap(api.PUT('/api/sql/saved/{name}', { params: { path: { name } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sql-saved'] }),
  })
}

export function useDeleteSaved() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      unwrap(api.DELETE('/api/sql/saved/{name}', { params: { path: { name } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sql-saved'] }),
  })
}

export function useCompat(dimension: Schemas['FieldType'] | null, hasColor: boolean) {
  return useQuery({
    queryKey: ['compat', dimension, hasColor],
    queryFn: () =>
      unwrap(
        api.GET('/api/compat', {
          params: { query: { dimension: dimension ?? undefined, has_color: hasColor } },
        }),
      ),
    staleTime: Infinity,
  })
}

/** Cancel an editor query or a profiling run (idempotent). */
export function cancelJob(queryId: string) {
  return api.POST('/api/cancel/{query_id}', { params: { path: { query_id: queryId } } })
}

export function newQueryId(): string {
  return crypto.randomUUID().replaceAll('-', '')
}

// ------------------------------------------------------------------ semantic model (Phase 5)

export function useModels() {
  return useQuery({ queryKey: ['models'], queryFn: () => unwrap(api.GET('/api/semantic')) })
}

export function useCheckModel(model: Schemas['SemanticModel'] | null) {
  return useQuery({
    queryKey: ['model-check', model],
    queryFn: () => unwrap(api.POST('/api/semantic/check', { body: model! })),
    enabled: model !== null,
    retry: false,
    staleTime: 30_000,
  })
}

export function useSaveModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (model: Schemas['SemanticModel']) =>
      unwrap(api.PUT('/api/semantic/{name}', { params: { path: { name: model.name } }, body: model })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['models'] })
      void qc.invalidateQueries({ queryKey: ['visual'] })
    },
  })
}

export function useDeleteModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => unwrap(api.DELETE('/api/semantic/{name}', { params: { path: { name } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['models'] }),
  })
}

export function useVisualQuery(req: Schemas['VisualRequest'] | null) {
  return useQuery({
    queryKey: ['visual', req],
    queryFn: ({ signal }) => unwrap(api.POST('/api/visual/query', { body: req!, signal })),
    enabled: req !== null,
    retry: false,
    placeholderData: (prev) => prev, // when the mark/filter changes, keep the previous chart while the new one arrives
  })
}

export function useSuggest() {
  return useMutation({
    mutationFn: (body: Schemas['SuggestIn']) => unwrap(api.POST('/api/semantic/suggest', { body })),
  })
}
