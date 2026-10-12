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
