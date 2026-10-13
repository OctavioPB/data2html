import type { EChartsType } from 'echarts/core'
import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useT } from '../i18n'
import { downloadChartPng, downloadVisualCsv } from './download'

/** CSV (server, aggregated rows as previewed) and PNG (the drawn chart) for a builder/editor visual. */
export function VisualDownloads({ request, chart, name }: {
  request: Schemas['VisualRequest'] | null
  chart: EChartsType | null
  name: string
}) {
  const t = useT()
  const [error, setError] = useState<string | null>(null)
  const panel = getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || '#fff'
  return (
    <span className="downloads">
      <button
        type="button"
        className="btn small"
        disabled={!request}
        title={t('download.csvHint')}
        onClick={() => {
          setError(null)
          if (request) downloadVisualCsv(request).catch((e: Error) => setError(e.message))
        }}
      >
        CSV
      </button>
      <button
        type="button"
        className="btn small"
        disabled={!chart}
        title={chart ? t('download.pngHint') : t('download.pngNone')}
        onClick={() => {
          if (chart) downloadChartPng(chart, `${name}.png`, panel).catch(() => setError(t('download.pngFailed')))
        }}
      >
        PNG
      </button>
      {error && <span className="error small">{error}</span>}
    </span>
  )
}
