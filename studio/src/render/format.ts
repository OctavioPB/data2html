import type { Schemas } from '../api/client'

// Moneda por defecto MXN; pasará a config/theme.yaml cuando el visor (Fase 6) lea el tema.
const CURRENCY = 'MXN'
const LOCALE = 'es-MX'

/** Formateador según `Measure.format`. `compact` para ejes (6 mil M); completo para tooltips y tablas. */
export function formatter(format: Schemas['MeasureFormat'] | undefined, compact = false): (v: number) => string {
  const base: Intl.NumberFormatOptions = compact ? { notation: 'compact', maximumFractionDigits: 1 } : {}
  if (format === 'currency') {
    const nf = new Intl.NumberFormat(LOCALE, { style: 'currency', currency: CURRENCY, maximumFractionDigits: compact ? 1 : 2, ...base })
    return (v) => nf.format(v)
  }
  if (format === 'percent') {
    const nf = new Intl.NumberFormat(LOCALE, { style: 'percent', maximumFractionDigits: 1, ...base })
    return (v) => nf.format(v)
  }
  const nf = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2, ...base })
  return (v) => nf.format(v)
}
