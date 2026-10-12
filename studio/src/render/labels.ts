import type { Schemas } from '../api/client'
import type { MessageKey } from '../i18n'

export const MARK_LABEL: Record<Schemas['Mark'], MessageKey> = {
  bar: 'mark.bar',
  line: 'mark.line',
  pie: 'mark.pie',
  kpi: 'mark.kpi',
  table: 'mark.table',
}

export const GRAIN_LABEL: Record<Schemas['TimeGrain'], MessageKey> = {
  day: 'grain.day',
  week: 'grain.week',
  month: 'grain.month',
  quarter: 'grain.quarter',
  year: 'grain.year',
}
