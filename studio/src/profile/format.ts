import { numberFormat } from '../i18n/format'

const plain = () => numberFormat({ maximumFractionDigits: 2 })
const compact = () => numberFormat({ notation: 'compact', maximumFractionDigits: 1 })

export const fmtNumber = (v: number) => plain().format(v)

export const fmt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : plain().format(v))

/** For narrow cells: compact from 100 thousand up (1,249,999.75 → 1.2M). */
export const fmtStat = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : Math.abs(v) >= 100_000 ? compact().format(v) : plain().format(v)

/** Coefficient with 2 decimals, never "-0.00". */
export const fmtCorr = (v: number) => {
  const s = v.toFixed(2)
  return s === '-0.00' ? '0.00' : s
}
export const fmtCompact = (v: number) => compact().format(v)

export function pct(part: number, total: number): string {
  if (!total) return '0%'
  const p = (part / total) * 100
  if (p > 0 && p < 0.1) return '<0.1%'
  return `${p < 1 && p > 0 ? p.toFixed(1) : Math.round(p)}%`
}
