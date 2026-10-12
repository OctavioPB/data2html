export const nf = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('es-MX', { notation: 'compact', maximumFractionDigits: 1 })

export const fmt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf.format(v))

/** Para celdas estrechas: compacto a partir de 100 mil (1,249,999.75 → 1.2 M). */
export const fmtStat = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : Math.abs(v) >= 100_000 ? compact.format(v) : nf.format(v)

/** Coeficiente con 2 decimales, sin "-0.00". */
export const fmtCorr = (v: number) => {
  const s = v.toFixed(2)
  return s === '-0.00' ? '0.00' : s
}
export const fmtCompact = (v: number) => compact.format(v)

export function pct(part: number, total: number): string {
  if (!total) return '0%'
  const p = (part / total) * 100
  if (p > 0 && p < 0.1) return '<0.1%'
  return `${p < 1 && p > 0 ? p.toFixed(1) : Math.round(p)}%`
}
