import type { Schemas } from '../api/client'
import { numberFormat } from '../i18n/format'

// Default currency MXN; it will move to config/theme.yaml when the viewer (Phase 6) reads the theme.
const CURRENCY = 'MXN'

/** Formatter for `Measure.format`, in the current language's locale. `compact` for axes (6B / 6 mil M);
 * full for tooltips and tables. */
export function formatter(format: Schemas['MeasureFormat'] | undefined, compact = false): (v: number) => string {
  const base: Intl.NumberFormatOptions = compact ? { notation: 'compact', maximumFractionDigits: 1 } : {}
  if (format === 'currency') {
    const nf = numberFormat({ style: 'currency', currency: CURRENCY, maximumFractionDigits: compact ? 1 : 2, ...base })
    return (v) => nf.format(v)
  }
  if (format === 'percent') {
    const nf = numberFormat({ style: 'percent', maximumFractionDigits: 1, ...base })
    return (v) => nf.format(v)
  }
  const nf = numberFormat({ maximumFractionDigits: 2, ...base })
  return (v) => nf.format(v)
}
