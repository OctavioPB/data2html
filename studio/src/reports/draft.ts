import type { Schemas } from '../api/client'
import { slug } from '../semantic/draft'

export type Report = Schemas['Report']
export type Visual = Schemas['Visual']
export type Param = Schemas['Param']
export type ParamType = Schemas['ParamType']

export const PARAM_TYPES: ParamType[] = ['date', 'int', 'float', 'str', 'bool']
const COLS = 12

/** A declared parameter with the `name: type` shorthand expanded (same as `Report.param()` in Python). */
export function paramOf(p: NonNullable<Report['params']>[string]): Param {
  return typeof p === 'string' ? { type: p, default: null, label: '' } : p
}

/** What the author's preview sends: each parameter's default, with its declared type. */
export function previewParams(report: Report): Pick<Schemas['VisualRequest'], 'params' | 'param_types'> {
  const params: Schemas['VisualRequest']['params'] = {}
  const types: Record<string, ParamType> = {}
  for (const [name, raw] of Object.entries(report.params ?? {})) {
    const p = paramOf(raw)
    types[name] = p.type
    if (p.default !== null && p.default !== undefined && p.default !== '') params[name] = p.default
  }
  return { params, param_types: types }
}

export function toVisualDraft(v: Visual): Schemas['VisualDraft'] {
  return { mark: v.mark, measure: v.measure, dimension: v.dimension, time_grain: v.time_grain, color: v.color, filters: v.filters }
}

function uniqueId(base: string, taken: Set<string>): string {
  let id = base
  for (let i = 2; taken.has(id); i++) id = `${base.slice(0, 60)}_${i}`
  return id
}

/** Append a builder visual below the existing ones (half width, 4 rows). */
export function addVisual(report: Report, draft: Schemas['VisualDraft'], title: string): Report {
  const taken = new Set(report.visuals.map((v) => v.id))
  const bottom = Math.max(0, ...report.visuals.map((v) => v.layout.y + v.layout.h))
  const visual: Visual = {
    ...draft,
    id: uniqueId(slug(title, 'visual'), taken),
    title,
    filters: draft.filters ?? [],
    layout: { x: 0, y: bottom, w: COLS / 2, h: 4 },
  }
  return { ...report, visuals: [...report.visuals, visual] }
}

export function newReport(id: string, title: string, model: string): Report {
  return { id, title, semantic_model: model, mode: 'live', params: {}, access: [], visuals: [] }
}

export const ID_PATTERN = /^[a-z][a-z0-9_]{0,62}$/

/** Renaming a parameter renames it in every visual filter that uses it (otherwise the report breaks). */
export function renameParam(visuals: Visual[], from: string, to: string): Visual[] {
  return visuals.map((v) =>
    (v.filters ?? []).some((f) => f.param === from)
      ? { ...v, filters: (v.filters ?? []).map((f) => (f.param === from ? { ...f, param: to } : f)) }
      : v,
  )
}
