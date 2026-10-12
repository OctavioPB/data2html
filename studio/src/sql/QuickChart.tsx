/**
 * Quick view of a SQL editor result. It does NOT produce a report-spec and is not saved: a publishable
 * visual comes from the semantic model ("Publish as measure…" in the editor). Draws the already
 * aggregated page. Marks limited by `compat.allowed_marks` (via /api/compat); shared render/VisualChart.
 */
import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useCompat } from '../api/queries'
import type { Cell, Column } from '../explore/usePagedRows'
import { useT } from '../i18n'
import { formatNumber } from '../i18n/format'
import { MARK_LABEL } from '../render/labels'
import { VisualChart } from '../render/VisualChart'

type FieldType = Schemas['FieldType']
type Mark = Schemas['Mark']
type ChartMark = Exclude<Mark, 'table'>

const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|U\w*INT|FLOAT|DOUBLE|REAL|DECIMAL)/i
const MAX_SERIES = 8

function fieldType(type: string): FieldType {
  if (/^(DATE|TIMESTAMP)/i.test(type)) return 'temporal'
  if (NUMERIC.test(type)) return 'quantitative'
  return 'nominal'
}

interface Props {
  columns: Column[]
  rows: Cell[][]
  total: number | null
}

export function QuickChart({ columns, rows, total }: Props) {
  const t = useT()
  const numeric = columns.filter((c) => NUMERIC.test(c.type))
  const dims = columns.filter((c) => !NUMERIC.test(c.type))
  const [dim, setDim] = useState<string>(dims[0]?.name ?? '')
  const [measures, setMeasures] = useState<string[]>(numeric[0] ? [numeric[0].name] : [])
  const [mark, setMark] = useState<ChartMark | null>(null)

  const dimCol = columns.find((c) => c.name === dim) ?? null
  const dimType = dimCol ? fieldType(dimCol.type) : null
  const compat = useCompat(dimType, measures.length > 1)
  const marks = (compat.data?.marks ?? []).filter((m): m is ChartMark => m !== 'table')
  const active: ChartMark | null = mark && marks.includes(mark) ? mark : (marks[0] ?? null)

  if (numeric.length === 0) {
    return <p className="muted">{t('quick.noNumeric')}</p>
  }

  const toggleMeasure = (name: string) =>
    setMeasures((m) =>
      m.includes(name) ? m.filter((x) => x !== name) : m.length < MAX_SERIES ? [...m, name] : m,
    )

  return (
    <div className="quick-chart">
      <div className="qc-controls">
        <label>
          {t('quick.dimension')}{' '}
          <select value={dim} onChange={(e) => setDim(e.target.value)}>
            <option value="">{t('quick.none')}</option>
            {dims.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </label>
        <fieldset className="qc-measures">
          <legend>{t('quick.measures')}</legend>
          {numeric.map((c) => (
            <label key={c.name} className="inline">
              <input type="checkbox" checked={measures.includes(c.name)} onChange={() => toggleMeasure(c.name)} />
              {c.name}
            </label>
          ))}
        </fieldset>
        <div className="seg" role="radiogroup" aria-label={t('quick.chartType')}>
          {marks.map((m) => (
            <button key={m} role="radio" aria-checked={active === m} onClick={() => setMark(m)}>
              {t(MARK_LABEL[m])}
            </button>
          ))}
        </div>
      </div>
      <p className="muted small">
        {t('quick.notSaved')}
        {total !== null && total > rows.length &&
          ` ${t('quick.firstRows', { n: rows.length, total: formatNumber(total) })}`}
      </p>
      {measures.length === 0 ? (
        <p className="muted">{t('quick.pickMeasure')}</p>
      ) : active ? (
        <VisualChart mark={active} columns={columns} rows={rows} dimension={dim || null} measures={measures} />
      ) : (
        <p className="muted">{t('quick.tableOnly')}</p>
      )}
    </div>
  )
}
