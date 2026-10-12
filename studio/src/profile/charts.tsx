/**
 * Minimal profile charts in SVG. One series per chart (one hue, no legend), thin bars with a 4px rounded
 * end anchored to the baseline, 2px gaps and a tooltip per mark (<title>).
 * Correlations: diverging blue (+) / red (−) with a gray midpoint.
 */
import type { Schemas } from '../api/client'
import { useT } from '../i18n'
import { fmtCorr, fmtNumber, pct } from './format'


/** Vertical bar with rounded top corners (flat base). */
function barPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

/** Horizontal bar with a rounded right end. */
function hbarPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, h / 2, w)
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`
}

interface VBar {
  label: string
  count: number
}

/** Vertical columns: histograms and counts per period. */
export function Columns({ bars, height = 72, ariaLabel }: { bars: VBar[]; height?: number; ariaLabel: string }) {
  const W = 300
  const max = Math.max(1, ...bars.map((b) => b.count))
  const gap = bars.length > 60 ? 1 : 2
  const bw = Math.max(1, (W - gap * (bars.length - 1)) / bars.length)
  return (
    <svg className="viz" viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" role="img" aria-label={ariaLabel}>
      <line x1="0" x2={W} y1={height - 0.5} y2={height - 0.5} className="viz-axis" />
      {bars.map((b, i) => {
        const h = b.count === 0 ? 0 : Math.max(1.5, (b.count / max) * (height - 4))
        const x = i * (bw + gap)
        return (
          <g key={i} className="viz-hit">
            {/* hover area larger than the mark */}
            <rect x={x} y={0} width={bw + gap} height={height} fill="transparent" />
            {h > 0 && <path d={barPath(x, height - h, bw, h)} className="viz-mark" />}
            <title>{`${b.label}: ${fmtNumber(b.count)}`}</title>
          </g>
        )
      })}
    </svg>
  )
}

/**
 * Horizontal bar list: most frequent values. The length is the share of the total (not of the largest
 * top value): a value with 0.003% looks almost empty, as it should. Labels use text ink.
 */
export function BarList({ items, total }: { items: Schemas['ValueCount'][]; total: number }) {
  return (
    <ul className="barlist">
      {items.map((v) => (
        <li key={v.value} title={`${v.value}: ${fmtNumber(v.count)} (${pct(v.count, total)})`}>
          <span className="barlist-label">{v.value}</span>
          <svg className="barlist-bar" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden>
            <path d={hbarPath(0, 1, Math.max(0.8, (v.count / Math.max(1, total)) * 100), 8)} className="viz-mark" />
          </svg>
          <span className="barlist-value">{pct(v.count, total)}</span>
        </li>
      ))}
    </ul>
  )
}

/** Correlation matrix: diverging color mixed in OKLab toward the neutral gray. */
export function CorrelationMatrix({ columns, values }: { columns: string[]; values: (number | null)[][] }) {
  const t = useT()
  const k = columns.length
  const showNumbers = k <= 12
  return (
    <div className="corr-scroll">
      <table className="corr" role="grid" aria-label={t('corr.matrix')}>
        <thead>
          <tr>
            <th />
            {columns.map((c) => (
              <th key={c} scope="col" className="corr-col">
                <span>{c}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {columns.map((row, a) => (
            <tr key={row}>
              <th scope="row" className="corr-row">{row}</th>
              {columns.map((col, b) => {
                const v = values[a][b]
                const strength = v === null ? 0 : Math.round(Math.min(1, Math.abs(v)) * 100)
                const pole = v !== null && v < 0 ? 'var(--div-neg)' : 'var(--div-pos)'
                const bg = v === null ? 'transparent' : `color-mix(in oklab, ${pole} ${strength}%, var(--div-mid))`
                const strong = strength >= 55
                return (
                  <td
                    key={col}
                    style={{ background: bg }}
                    className={strong ? 'corr-cell strong' : 'corr-cell'}
                    title={`${row} × ${col}: ${v === null ? t('corr.noData') : fmtCorr(v)}`}
                  >
                    {showNumbers && v !== null ? fmtCorr(v) : ''}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="corr-legend" aria-hidden>
        <span>−1</span>
        <span className="corr-ramp" />
        <span>+1</span>
      </div>
    </div>
  )
}
