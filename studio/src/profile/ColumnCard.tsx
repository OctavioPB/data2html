import type { Schemas } from '../api/client'
import { BarList, Columns } from './charts'
import { fmt, fmtCompact, fmtStat, pct } from './format'

type Col = Schemas['ColumnProfile']

const KIND_LABEL: Record<Col['kind'], string> = {
  numeric: 'numérica',
  temporal: 'fecha',
  text: 'texto',
  boolean: 'booleana',
  other: 'otra',
}
const PERIOD_LABEL = { year: 'año', month: 'mes', day: 'día', hour: 'hora' } as const

export function ColumnCard({ col }: { col: Col }) {
  return (
    <article className="col-card" id={`perfil-${col.name}`}>
      <header>
        <h3 className="mono">
          {col.computed && <span className="muted">ƒ </span>}
          {col.name}
        </h3>
        <span className="muted small">
          {KIND_LABEL[col.kind]} · <span className="mono">{col.type}</span>
        </span>
      </header>

      <dl className="stats">
        <div>
          <dt>No nulos</dt>
          <dd>{fmtCompact(col.non_null)}</dd>
        </div>
        <div>
          <dt>Nulos</dt>
          <dd>{pct(col.nulls, col.nulls + col.non_null)}</dd>
        </div>
        <div>
          <dt>Distintos</dt>
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
                ariaLabel={`Filas por ${PERIOD_LABEL[col.period_unit ?? 'day']} en ${col.name}`}
              />
              <p className="muted small">Filas por {PERIOD_LABEL[col.period_unit ?? 'day']}</p>
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
  const shown = top.slice(0, 8)
  const others = col.non_null - shown.reduce((s, v) => s + v.count, 0)
  const notes = [
    others > 0 ? `Otros: ${pct(others, col.non_null)}` : null,
    col.min_length !== null && col.min_length !== undefined ? `longitud ${col.min_length}–${col.max_length}` : null,
  ].filter(Boolean)
  return (
    <>
      <BarList items={shown} total={col.non_null} />
      {notes.length > 0 && <p className="muted small">{notes.join(' · ')}</p>}
    </>
  )
}

function NumericDetail({ col }: { col: Col }) {
  const o = col.outliers
  const outliers = o ? o.below + o.above : 0
  return (
    <>
      <dl className="stats five">
        <div>
          <dt>Mín</dt>
          <dd title={fmt(col.min as number | null)}>{fmtStat(col.min as number | null)}</dd>
        </div>
        <div>
          <dt>Q1</dt>
          <dd title={fmt(col.q1)}>{fmtStat(col.q1)}</dd>
        </div>
        <div>
          <dt>Mediana</dt>
          <dd title={fmt(col.median)}>{fmtStat(col.median)}</dd>
        </div>
        <div>
          <dt>Q3</dt>
          <dd title={fmt(col.q3)}>{fmtStat(col.q3)}</dd>
        </div>
        <div>
          <dt>Máx</dt>
          <dd title={fmt(col.max as number | null)}>{fmtStat(col.max as number | null)}</dd>
        </div>
      </dl>
      {col.histogram && (
        <Columns
          bars={col.histogram.map((b) => ({ label: `${fmt(b.start)} – ${fmt(b.end)}`, count: b.count }))}
          ariaLabel={`Histograma de ${col.name}`}
        />
      )}
      <p className="muted small">
        Media {fmt(col.mean)} · desv. {fmt(col.std)}
        {o && (
          <>
            {' '}
            · {outliers === 0 ? 'sin atípicos' : `${fmtCompact(outliers)} atípicos (${pct(outliers, col.non_null)})`}
            <span title={`Fuera de [${fmt(o.low_fence)}, ${fmt(o.high_fence)}] (1.5 × IQR)`}> ⓘ</span>
          </>
        )}
      </p>
    </>
  )
}
