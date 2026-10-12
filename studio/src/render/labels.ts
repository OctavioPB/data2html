import type { Schemas } from '../api/client'

export const MARK_LABEL: Record<Schemas['Mark'], string> = {
  bar: 'Barras',
  line: 'Líneas',
  pie: 'Pastel',
  kpi: 'KPI',
  table: 'Tabla',
}

export const GRAIN_LABEL: Record<Schemas['TimeGrain'], string> = {
  day: 'día',
  week: 'semana',
  month: 'mes',
  quarter: 'trimestre',
  year: 'año',
}
