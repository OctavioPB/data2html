/**
 * Gráficos mínimos del perfil, en SVG. Una sola serie por gráfico (un tono, sin leyenda), barras finas con
 * extremo redondeado de 4px anclado a la base, 2px de separación y tooltip por marca (<title>).
 * Correlaciones: divergente azul (+) / rojo (−) con punto medio gris.
 */
import type { Schemas } from '../api/client'
import { fmtCorr, nf, pct } from './format'


/** Barra vertical con las esquinas superiores redondeadas (base recta). */
function barPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

/** Barra horizontal con el extremo derecho redondeado. */
function hbarPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, h / 2, w)
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`
}

interface VBar {
  label: string
  count: number
}

/** Columnas verticales: histogramas y conteo por periodo. */
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
            {/* área de hover más grande que la marca */}
            <rect x={x} y={0} width={bw + gap} height={height} fill="transparent" />
            {h > 0 && <path d={barPath(x, height - h, bw, h)} className="viz-mark" />}
            <title>{`${b.label}: ${nf.format(b.count)}`}</title>
          </g>
        )
      })}
    </svg>
  )
}

/**
 * Lista de barras horizontales: valores más frecuentes. El largo es la proporción sobre el total (no
 * sobre el mayor del top): un valor con 0.003% se ve casi vacío, como debe. Etiquetas en tinta de texto.
 */
export function BarList({ items, total }: { items: Schemas['ValueCount'][]; total: number }) {
  return (
    <ul className="barlist">
      {items.map((v) => (
        <li key={v.value} title={`${v.value}: ${nf.format(v.count)} (${pct(v.count, total)})`}>
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

/** Matriz de correlación: color divergente con mezcla en OKLab hacia el gris neutro. */
export function CorrelationMatrix({ columns, values }: { columns: string[]; values: (number | null)[][] }) {
  const k = columns.length
  const showNumbers = k <= 12
  return (
    <div className="corr-scroll">
      <table className="corr" role="grid" aria-label="Matriz de correlación">
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
                    title={`${row} × ${col}: ${v === null ? 'sin dato' : fmtCorr(v)}`}
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
