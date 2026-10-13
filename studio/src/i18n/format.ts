import { locale } from './index'

const cache = new Map<string, Intl.NumberFormat>()

/** `Intl.NumberFormat` for the current language, cached per (locale, options). */
export function numberFormat(options: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const key = `${locale()}|${JSON.stringify(options)}`
  let nf = cache.get(key)
  if (!nf) {
    nf = new Intl.NumberFormat(locale(), options)
    cache.set(key, nf)
  }
  return nf
}

export const formatNumber = (v: number, options?: Intl.NumberFormatOptions) => numberFormat(options).format(v)

export const formatDateTime = (iso: string) => new Date(iso).toLocaleString(locale())

/** A period start (`2025-04-01`) labelled by its grain: "abr 2025", "T2 2025" / "Q2 2025", "2025"…
 * Dates are read and shown in UTC, so a day never shifts with the browser's time zone. */
export function formatPeriod(iso: string, grain: 'day' | 'week' | 'month' | 'quarter' | 'year'): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const date = new Date(Date.UTC(y, mo - 1, d))
  const loc = locale()
  if (grain === 'year') return String(y)
  if (grain === 'quarter') return `${loc.startsWith('es') ? 'T' : 'Q'}${Math.floor((mo - 1) / 3) + 1} ${y}`
  if (grain === 'month') return date.toLocaleDateString(loc, { month: 'short', year: 'numeric', timeZone: 'UTC' })
  return date.toLocaleDateString(loc, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}
