import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

async function unwrap<T>(req: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await req
  if (!response.ok) throw new Error(errorMessage(error, response.status))
  return data as T
}

function errorMessage(error: unknown, status: number): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
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
