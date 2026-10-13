/**
 * The studio needs a signed-in author (ADR 0010). Signing in happens on the server's pages (`/login`:
 * local password, Microsoft Entra ID or, in development, a picked identity), which come back to `/`.
 */
import type { ReactNode } from 'react'

import { useMe, useTheme } from '../api/queries'
import { useT } from '../i18n'

const SIGN_IN = '/login?next=/'

export function AuthGate({ children }: { children: ReactNode }) {
  const t = useT()
  const me = useMe()
  const theme = useTheme(me.data?.author === true) // the studio's API answers authors only
  if (me.isPending) return <p className="muted gate">{t('common.loading')}</p>
  if (me.isError) return <p className="error gate">{me.error.message}</p>
  if (me.data === null) {
    return (
      <section className="gate">
        <h2>{t('auth.signInTitle')}</h2>
        <p className="muted">{t('auth.signInBody')}</p>
        <a className="btn primary" href={SIGN_IN}>
          {t('auth.signIn')}
        </a>
      </section>
    )
  }
  if (!me.data.author) {
    return (
      <section className="gate">
        <h2>{t('auth.noAuthorTitle')}</h2>
        <p className="muted">{t('auth.noAuthorBody', { user: me.data.user_id })}</p>
        <p className="muted small">{t('auth.noAuthorViewer')}</p>
        <SignOut />
      </section>
    )
  }
  // the theme (currency) before any chart or table is formatted
  if (theme.isPending) return <p className="muted gate">{t('common.loading')}</p>
  return <>{children}</>
}

export function SignOut() {
  const t = useT()
  return (
    <form method="post" action="/logout" className="inline-form">
      <button className="btn small" type="submit">
        {t('auth.signOut')}
      </button>
    </form>
  )
}

/** Signed-in user and sign-out, in the top bar. */
export function UserMenu() {
  const t = useT()
  const me = useMe()
  if (!me.data) return null
  return (
    <span className="user-menu">
      <span className="muted small" title={me.data.email || undefined}>
        {t('auth.signedInAs', { user: me.data.user_id })}
      </span>
      <SignOut />
    </span>
  )
}
