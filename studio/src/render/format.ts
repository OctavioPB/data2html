import type { Schemas } from '../api/client'
import { numberFormat } from '../i18n/format'

// Currency of `format: currency` measures: config/theme.yaml (GET /api/theme), the same as the viewer.
// MXN until the theme arrives (it is fetched before any data).
let currency = 'MXN'

export function setCurrency(code: string) {
  currency = code
}

/** Formatter for `Measure.format`, in the current language's locale. `compact` for axes (6B / 6 mil M);
 * full for tooltips and tables. */
export function formatter(format: Schemas['MeasureFormat'] | undefined, compact = false): (v: number) => string {
  const base: Intl.NumberFormatOptions = compact ? { notation: 'compact', maximumFractionDigits: 1 } : {}
  if (format === 'currency') {
    const nf = numberFormat({ style: 'currency', currency, maximumFractionDigits: compact ? 1 : 2, ...base })
    return (v) => nf.format(v)
  }
  if (format === 'percent') {
    const nf = numberFormat({ style: 'percent', maximumFractionDigits: 1, ...base })
    return (v) => nf.format(v)
  }
  const nf = numberFormat({ maximumFractionDigits: 2, ...base })
  return (v) => nf.format(v)
}
