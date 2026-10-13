/** Import sources (DynamoDB exports): last export per table and "export now" (ADR 0012). */
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { useIngest, useStartIngest } from '../api/queries'
import { useT } from '../i18n'
import { formatDateTime, formatNumber } from '../i18n/format'

export function IngestPanel({ source }: { source: string }) {
  const t = useT()
  const qc = useQueryClient()
  const { data, isError, error } = useIngest(source)
  const start = useStartIngest(source)
  const running = data?.tables.some((x) => x.running) ?? false
  const wasRunning = useRef(false)
  useEffect(() => {
    // an export just finished: its table appears in (or refreshes) the catalog
    if (wasRunning.current && !running) void qc.invalidateQueries({ queryKey: ['catalog'] })
    wasRunning.current = running
  }, [running, qc])

  if (isError) return <p className="error small">{error.message}</p>
  if (!data) return null
  return (
    <div className="ingest" aria-label={t('ingest.title')}>
      {data.tables.map((x) => (
        <div key={x.table} className="ingest-row">
          <span className="muted" title={x.error ?? undefined}>
            <span className="mono">{x.table}</span>{' '}
            {x.running
              ? t('ingest.running')
              : x.error
                ? `⚠ ${t('ingest.failed')}`
                : x.last
                  ? t('ingest.last', { when: formatDateTime(x.last.finished_at), rows: formatNumber(x.last.rows) })
                  : t('ingest.never')}
            {x.last && Object.keys(x.last.warnings).length > 0 && (
              <span title={Object.entries(x.last.warnings).map(([c, n]) => `${c}: ${n}`).join(', ')}> ⚠</span>
            )}
          </span>
          <button
            className="btn small"
            disabled={x.running || start.isPending}
            onClick={() => start.mutate(x.table)}
            title={t('ingest.hint')}
          >
            {t('ingest.now')}
          </button>
        </div>
      ))}
      {start.isError && <p className="error small">{start.error.message}</p>}
    </div>
  )
}
