import { LANGS, useLangStore, useT } from '../i18n'

/** ES / EN selector in the top bar. The choice is remembered per browser. */
export function LanguageSwitch() {
  const t = useT()
  const lang = useLangStore((s) => s.lang)
  const setLang = useLangStore((s) => s.setLang)
  return (
    <div className="seg lang-switch" role="radiogroup" aria-label={t('lang.label')}>
      {LANGS.map((l) => (
        <button
          key={l.id}
          type="button"
          role="radio"
          aria-checked={lang === l.id}
          lang={l.id}
          title={l.label}
          onClick={() => setLang(l.id)}
        >
          {l.id.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
