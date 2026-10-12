import type { Schemas } from '../api/client'
import { useT, type MessageKey } from '../i18n'
import { BarList, Columns } from './charts'
import { fmt, fmtCompact, fmtStat, pct } from './format'

type Col = Schemas['ColumnProfile']

const KIND_LABEL: Record<Col['kind'], MessageKey> = {
  numeric: 'kind.numeric',
  temporal: 'kind.temporal',
  text: 'kind.text',
  boolean: 'kind.boolean',
  other: 'kind.other',
}
const PERIOD_LABEL: Record<NonNullable<Col['period_unit']>, MessageKey> = {
  year: 'period.year',
  month: 'period.month',
  day: 'period.day',
  hour: 'period.hour',
}

export function ColumnCard({ col }: { col: Col }) {
  const t = useT()
  const period = t(PERIOD_LABEL[col.period_unit ?? 'day'])
  return (
    <article className="col-card" id={`profile-${col.name}`}>
      <header>
        <h3 className="mono">
          {col.computed && <span className="muted">ƒ </span>}
          {col.name}
        </h3>
        <span className="muted small">
          {t(KIND_LABEL[col.kind])} · <span className="mono">{col.type}</span>
        </span>
      </header>

      <dl className="stats">
        <div>
          <dt>{t('stat.nonNull')}</dt>
          <dd>{fmtCompact(col.non_null)}</dd>
        </div>
        <div>
          <dt>{t('stat.nulls')}</dt>
          <dd>{pct(col.nulls, col.nulls + col.non_null)}</dd>
        </div>
        <div>
          <dt>{t('stat.distinct')}</dt>
          <dd>{fmtCompact(col.distinct)}</dd>
        </div>
      </dl>

      {col.kind === 'numeric' && <NumericDetail col={col} />}
      {(col.kind === 'text' || col.kind === 'boolean') && col.top && <TopValues col={col} top={col.top} />}
      {col.kind === 'temporal' && (
        <>
          <p className="small">
            {col.min} → {col.max}
          </p>
          {col.periods && col.periods.length > 0 && (
            <>
              <Columns
                bars={col.periods.map((p) => ({ label: p.period, count: p.count }))}
                ariaLabel={t('profile.rowsPerPeriodOf', { period, name: col.name })}
              />
              <p className="muted small">{t('profile.rowsPerPeriod', { period })}</p>
            </>
          )}
        </>
      )}

      {col.warnings.length > 0 && (
        <ul className="col-warnings">
          {col.warnings.map((w) => (
            <li key={w.code}>
              <span aria-hidden>⚠</span> {w.message}
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}

function TopValues({ col, top }: { col: Col; top: Schemas['ValueCount'][] }) {
  const t = useT()
  const shown = top.slice(0, 8)
  const others = col.non_null - shown.reduce((s, v) => s + v.count, 0)
  const notes = [
    others > 0 ? t('profile.others', { pct: pct(others, col.non_null) }) : null,
    col.min_length !== null && col.min_length !== undefined
      ? t('profile.length', { min: col.min_length, max: col.max_length ?? '' })
      : null,
  ].filter(Boolean)
  return (
    <>
      <BarList items={shown} total={col.non_null} />
      {notes.length > 0 && <p className="muted small">{notes.join(' · ')}</p>}
    </>
  )
}

function NumericDetail({ col }: { col: Col }) {
  const t = useT()
  const o = col.outliers
  const outliers = o ? o.below + o.above : 0
  return (
    <>
      <dl className="stats five">
        <div>
          <dt>{t('stat.min')}</dt>
          <dd title={fmt(col.min as number | null)}>{fmtStat(col.min as number | null)}</dd>
        </div>
        <div>
          <dt>Q1</dt>
          <dd title={fmt(col.q1)}>{fmtStat(col.q1)}</dd>
        </div>
        <div>
          <dt>{t('stat.median')}</dt>
          <dd title={fmt(col.median)}>{fmtStat(col.median)}</dd>
        </div>
        <div>
          <dt>Q3</dt>
          <dd title={fmt(col.q3)}>{fmtStat(col.q3)}</dd>
        </div>
        <div>
          <dt>{t('stat.max')}</dt>
          <dd title={fmt(col.max as number | null)}>{fmtStat(col.max as number | null)}</dd>
        </div>
      </dl>
      {col.histogram && (
        <Columns
          bars={col.histogram.map((b) => ({ label: `${fmt(b.start)} – ${fmt(b.end)}`, count: b.count }))}
          ariaLabel={t('profile.histogramOf', { name: col.name })}
        />
      )}
      <p className="muted small">
        {t('profile.meanStd', { mean: fmt(col.mean), std: fmt(col.std) })}
        {o && (
          <>
            {' '}
            ·{' '}
            {outliers === 0
              ? t('profile.noOutliers')
              : t('profile.outliers', { n: fmtCompact(outliers), pct: pct(outliers, col.non_null) })}
            <span title={t('profile.outlierFences', { low: fmt(o.low_fence), high: fmt(o.high_fence) })}> ⓘ</span>
          </>
        )}
      </p>
    </>
  )
}
