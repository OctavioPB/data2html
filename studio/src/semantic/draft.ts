import type { Schemas } from '../api/client'

type Model = Schemas['SemanticModel']
type FieldType = Schemas['FieldType']

export const IDENT = /^[a-z][a-z0-9_]{0,62}$/

export interface DimRow {
  key: number
  name: string
  column: string
  type: FieldType
  description: string
}

export interface MeasureRow {
  key: number
  name: string
  sql: string
  format: Schemas['MeasureFormat']
  owner: string
  description: string
}

export interface ModelDraft {
  name: string
  source: string
  table: string
  dimensions: DimRow[]
  measures: MeasureRow[]
  rls: Schemas['RlsRule'] | null
}

let seq = 0
export const nextKey = () => ++seq

export function toDraft(m: Model): ModelDraft {
  return {
    name: m.name,
    source: m.source,
    table: m.table,
    dimensions: Object.entries(m.dimensions).map(([name, d]) => ({
      key: nextKey(), name, column: d.column, type: d.type, description: d.description ?? '',
    })),
    measures: Object.entries(m.measures).map(([name, x]) => ({
      key: nextKey(), name, sql: x.sql, format: x.format ?? 'number', owner: x.owner, description: x.description,
    })),
    rls: m.rls ?? null,
  }
}

export function fromDraft(d: ModelDraft): Model {
  return {
    name: d.name,
    source: d.source,
    table: d.table,
    dimensions: Object.fromEntries(
      d.dimensions.map((x) => [x.name, { column: x.column, type: x.type, description: x.description }]),
    ),
    measures: Object.fromEntries(
      d.measures.map((x) => [x.name, { sql: x.sql, format: x.format, owner: x.owner, description: x.description }]),
    ),
    rls: d.rls,
  }
}

export function slug(text: string, fallback = 'campo'): string {
  const s = text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return (/^[a-z]/.test(s) ? s : `${fallback}_${s}`).slice(0, 63)
}

/** Tipo de dimensión sugerido a partir del tipo DuckDB de la columna. */
export function guessType(dbType: string): FieldType {
  if (/^(DATE|TIMESTAMP)/i.test(dbType)) return 'temporal'
  return 'nominal'
}

/** Problemas locales (antes de preguntar al servidor). */
export function localErrors(d: ModelDraft): string[] {
  const errs: string[] = []
  if (!IDENT.test(d.name)) errs.push('nombre del modelo: minúsculas, dígitos y _; empieza con letra')
  if (!d.table) errs.push('elige una tabla')
  const names = [...d.dimensions.map((x) => x.name), ...d.measures.map((x) => x.name)]
  names.filter((n) => !IDENT.test(n)).forEach((n) => errs.push(`nombre inválido: '${n || '(vacío)'}'`))
  const dup = names.filter((n, i) => names.indexOf(n) !== i)
  if (dup.length) errs.push(`nombres repetidos: ${[...new Set(dup)].join(', ')}`)
  d.measures.forEach((m) => {
    if (!m.owner.trim() || !m.description.trim()) errs.push(`medida '${m.name}': falta dueño o descripción`)
  })
  return errs
}

/** YAML de un visual para pegar en un reporte (id/título/layout de ejemplo hasta la Fase 6). */
export function visualYaml(v: Schemas['VisualDraft'], title: string): string {
  const q = (s: string) => (/^[\w-]+$/.test(s) ? s : JSON.stringify(s))
  const lines = [`- id: ${slug(title, 'visual')}`, `  title: ${JSON.stringify(title)}`, `  mark: ${v.mark}`, `  measure: ${v.measure}`]
  if (v.dimension) lines.push(`  dimension: ${v.dimension}`)
  if (v.time_grain) lines.push(`  time_grain: ${v.time_grain}`)
  if (v.color) lines.push(`  color: ${v.color}`)
  if (v.filters?.length) {
    lines.push('  filters:')
    for (const f of v.filters) {
      const val = Array.isArray(f.value) ? `[${f.value.map((x) => q(String(x))).join(', ')}]` : q(String(f.value))
      lines.push(`    - { dimension: ${f.dimension}, op: ${f.op}, value: ${val} }`)
    }
  }
  lines.push('  layout: { x: 0, y: 0, w: 6, h: 4 }')
  return lines.join('\n') + '\n'
}
