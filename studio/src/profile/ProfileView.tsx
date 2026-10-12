import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useProfile, useRefreshProfile } from '../api/queries'
import { useT } from '../i18n'
import { formatDateTime } from '../i18n/format'
import { CorrelationMatrix } from './charts'
import { ColumnCard } from './ColumnCard'
import { fmtCompact, fmtNumber } from './format'

interface Props {
  source: string
  table: Schemas['TableOut']
}

export function ProfileView({ source, table }: Props) {
  const t = useT()
  const computedKey = table.computed.map((c) => `${c.name}=${c.expr}`).join('|')
  const { data, isPending, isError, error, cancel, refetch } = useProfile(source, table.name, computedKey)
  const refresh = useRefreshProfile(source, table.name, computedKey)
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson')

  if (isPending) {
    return (
      <div className="profile-head">
        <p className="muted">{t('profile.running')}</p>
        <button className="btn small" onClick={cancel}>
          {t('common.cancel')}
        </button>
      </div>
    )
  }
  if (isError) {
    return (
      <div className="profile-head">
        <p className="error">{error.message}</p>
        <button className="btn small" onClick={() => void refetch()}>
          {t('common.retry')}
        </button>
      </div>
    )
  }

  const flagged = data.columns.filter((c) => c.warnings.length > 0)
  const rows = fmtNumber(data.rows)

  return (
    <div className="profile">
      <div className="profile-head">
        {data.sampled ? (
          <p className="sample-banner" role="note">
            <strong>{t('profile.sampleTitle')}</strong> {t('profile.sampleBody', { n: rows })}
          </p>
        ) : (
          <p className="muted small">
            {data.sample_size ? t('profile.allRowsFitSample', { n: rows }) : t('profile.allRows', { n: rows })}
          </p>
        )}
        <span className="muted small">
          {(data.elapsed_ms / 1000).toFixed(1)} s · {formatDateTime(data.profiled_at)}
        </span>
        <button className="btn small" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? t('profile.recomputing') : t('profile.recompute')}
        </button>
      </div>

      {flagged.length > 0 && (
        <section className="profile-warnings">
          <h3>{t('profile.warnings')}</h3>
          <ul>
            {flagged.flatMap((c) =>
              c.warnings.map((w) => (
                <li key={`${c.name}-${w.code}`}>
                  <span aria-hidden>⚠</span>{' '}
                  <a href={`#profile-${c.name}`} onClick={(e) => jump(e, c.name)} className="mono">
                    {c.name}
                  </a>
                  : {w.message}
                </li>
              )),
            )}
          </ul>
        </section>
      )}

      <div className="col-grid">
        {data.columns.map((c) => (
          <ColumnCard key={c.name} col={c} />
        ))}
      </div>

      {data.correlations && (
        <section className="profile-corr">
          <header>
            <h3>{t('profile.correlations')}</h3>
            <div className="seg" role="radiogroup" aria-label={t('profile.method')}>
              {(['pearson', 'spearman'] as const).map((m) => (
                <button key={m} role="radio" aria-checked={method === m} onClick={() => setMethod(m)}>
                  {m === 'pearson' ? 'Pearson' : 'Spearman'}
                </button>
              ))}
            </div>
            <span className="muted small">
              n = {fmtCompact(data.correlations.n)}
              {data.correlations.n < data.rows ? ` ${t('profile.sampleSuffix')}` : ''} ·{' '}
              {method === 'pearson' ? t('profile.linear') : t('profile.monotonic')}
            </span>
          </header>
          <CorrelationMatrix columns={data.correlations.columns} values={data.correlations[method]} />
        </section>
      )}
    </div>
  )
}

/** The URL hash is the open table: jumping to a column must not touch it. */
function jump(e: React.MouseEvent, name: string) {
  e.preventDefault()
  document.getElementById(`profile-${name}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
