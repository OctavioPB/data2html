/**
 * Studio localization (English / Spanish).
 *
 * - Dictionaries are typed: `es` must have exactly the keys of `en` (a missing key does not compile).
 * - The chosen language is remembered per browser (localStorage); the first time it follows the browser.
 * - Every API request carries `Accept-Language` (api/client.ts), so server messages match the UI.
 * - Numbers and dates are formatted with the language's locale (es-MX / en-US).
 */
import { useCallback } from 'react'
import { create } from 'zustand'

import { en, type MessageKey } from './en'
import { es } from './es'

export type Lang = 'en' | 'es'
export type { MessageKey }
export type Params = Record<string, string | number>

export const LANGS: { id: Lang; label: string }[] = [
  { id: 'es', label: 'Español' },
  { id: 'en', label: 'English' },
]

const STORAGE_KEY = 'd2h.lang'
const DICTS: Record<Lang, Record<MessageKey, string>> = { en, es }
const LOCALES: Record<Lang, string> = { en: 'en-US', es: 'es-MX' }

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'en' || saved === 'es') return saved
  } catch {
    /* storage unavailable: fall back to the browser language */
  }
  const nav = (navigator.languages?.[0] ?? navigator.language ?? '').toLowerCase()
  return nav.startsWith('es') ? 'es' : 'en'
}

interface LangState {
  lang: Lang
  setLang: (lang: Lang) => void
}

export const useLangStore = create<LangState>((set) => ({
  lang: initialLang(),
  setLang: (lang) => {
    try {
      localStorage.setItem(STORAGE_KEY, lang)
    } catch {
      /* not persisted: the choice lasts for this session */
    }
    document.documentElement.lang = lang
    set({ lang })
  },
}))
document.documentElement.lang = useLangStore.getState().lang

export function getLang(): Lang {
  return useLangStore.getState().lang
}

export function translate(lang: Lang, key: MessageKey, params?: Params): string {
  const text = DICTS[lang][key] ?? en[key]
  return params ? text.replace(/\{(\w+)\}/g, (m, name: string) => (name in params ? String(params[name]) : m)) : text
}

/** Outside React components (event handlers, helpers). Inside components prefer `useT`. */
export function t(key: MessageKey, params?: Params): string {
  return translate(getLang(), key, params)
}

/** Translator bound to the current language; the component re-renders when it changes. */
export function useT(): (key: MessageKey, params?: Params) => string {
  const lang = useLangStore((s) => s.lang)
  return useCallback((key: MessageKey, params?: Params) => translate(lang, key, params), [lang])
}

export function useLang(): Lang {
  return useLangStore((s) => s.lang)
}

export function locale(lang: Lang = getLang()): string {
  return LOCALES[lang]
}
