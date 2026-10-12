/**
 * Render de un visual a partir de filas YA agregadas (no re-agrega). Lo usan la vista rápida del editor
 * SQL y el constructor; la Fase 6 lo reutiliza en el visor.
 *
 * Mapeo (skill html-renderer): bar/line/pie → ECharts; kpi → número formateado; table → <table> DOM
 * (React escapa el texto). Estilo (skill dataviz): una serie por tono en orden fijo de la paleta validada
 * (--series-N), barras con extremo redondeado de 4px y 2px de separación, líneas de 2px, marcadores de
 * 8px con anillo de 2px, rejilla recesiva, leyenda solo con ≥2 series, tooltip siempre.
 */
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useEffect, useMemo, useRef } from 'react'

import type { Schemas } from '../api/client'
import type { Cell, Column } from '../explore/usePagedRows'
import { usePrefersDark } from '../explore/usePrefersDark'
import { formatter } from './format'

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

type Mark = Schemas['Mark']
const MAX_SERIES = 8
const MAX_PIE = 8

export interface VisualChartProps {
  mark: Mark
  columns: Column[]
  rows: Cell[][]
  dimension: string | null
  color?: string | null
  measures: string[]
  format?: Schemas['MeasureFormat']
  height?: number
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function VisualChart(props: VisualChartProps) {
  const { mark, columns, rows, measures } = props
  if (mark === 'table') return <DataTable columns={columns} rows={rows} format={props.format} measures={measures} />
  if (mark === 'kpi') return <Kpi {...props} />
  if (rows.length === 0) return <p className="muted">Sin filas para graficar.</p>
  return <EChart {...props} />
}

function DataTable({ columns, rows, format, measures }: Pick<VisualChartProps, 'columns' | 'rows' | 'format' | 'measures'>) {
  const fmt = formatter(format)
  return (
    <div className="scroll visual-table">
      <table className="grid">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.name} className={measures.includes(c.name) ? 'num' : undefined}>
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => {
                const isMeasure = measures.includes(columns[j].name)
                return (
                  <td key={j} className={isMeasure ? 'num' : undefined}>
                    {v === null ? '∅' : isMeasure && typeof v === 'number' ? fmt(v) : String(v)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Kpi({ columns, rows, measures, format }: VisualChartProps) {
  if (rows.length !== 1) return <p className="muted">Un KPI necesita una sola fila (sin dimensión).</p>
  const fmt = formatter(format)
  return (
    <div className="kpis">
      {measures.map((m) => {
        const v = rows[0][columns.findIndex((c) => c.name === m)]
        return (
          <div key={m} className="kpi">
            <div className="kpi-value">{typeof v === 'number' ? fmt(v) : String(v ?? '—')}</div>
            <div className="kpi-label">{m}</div>
          </div>
        )
      })}
    </div>
  )
}

interface Series {
  name: string
  values: (number | null)[]
}

/** Filas → categorías y series. Con `color`, una serie por valor (pivot, no agregación). */
function toSeries(props: VisualChartProps): { cats: string[]; series: Series[] } | { error: string } {
  const { columns, rows, dimension, color, measures } = props
  const idx = (name: string) => columns.findIndex((c) => c.name === name)
  const di = dimension ? idx(dimension) : -1
  const num = (v: Cell) => (typeof v === 'number' ? v : v === null ? null : Number(v))
  const label = (v: Cell) => (v === null ? '∅' : String(v))
  if (color) {
    const ci = idx(color)
    const mi = idx(measures[0])
    const cats = [...new Set(rows.map((r) => label(r[di])))]
    const names = [...new Set(rows.map((r) => label(r[ci])))]
    if (names.length > MAX_SERIES) {
      return { error: `${names.length} valores de color (máximo ${MAX_SERIES}): filtra o quita el color.` }
    }
    const series = names.map((name) => {
      const byCat = new Map(rows.filter((r) => label(r[ci]) === name).map((r) => [label(r[di]), num(r[mi])]))
      return { name, values: cats.map((c) => byCat.get(c) ?? null) }
    })
    return { cats, series }
  }
  const cats = rows.map((r, i) => (di >= 0 ? label(r[di]) : String(i + 1)))
  return { cats, series: measures.map((m) => ({ name: m, values: rows.map((r) => num(r[idx(m)])) })) }
}

function EChart(props: VisualChartProps) {
  const { mark, rows, format, height = 360 } = props
  const host = useRef<HTMLDivElement>(null)
  const dark = usePrefersDark()
  const shaped = useMemo(() => toSeries(props), [props])
  const tooManySlices = mark === 'pie' && rows.length > MAX_PIE

  const option = useMemo<EChartsCoreOption | null>(() => {
    if ('error' in shaped || tooManySlices) return null
    const { cats, series } = shaped
    const fmt = formatter(format)
    const compact = formatter(format, true)
    const palette = Array.from({ length: MAX_SERIES }, (_, i) => cssVar(`--series-${i + 1}`))
    const text = cssVar('--text')
    const muted = cssVar('--muted')
    const border = cssVar('--border')
    const surface = cssVar('--panel')
    const base = {
      color: palette,
      animation: false,
      textStyle: { color: text, fontFamily: 'inherit' },
      tooltip: {
        trigger: mark === 'pie' ? 'item' : 'axis',
        backgroundColor: surface,
        borderColor: border,
        textStyle: { color: text },
        valueFormatter: (v: unknown) => (typeof v === 'number' ? fmt(v) : String(v ?? '—')),
      },
      legend: series.length > 1 || mark === 'pie' ? { top: 0, itemGap: 16, textStyle: { color: text } } : undefined,
    }
    if (mark === 'pie') {
      return {
        ...base,
        series: [
          {
            type: 'pie',
            top: 28,
            radius: ['0%', '70%'],
            itemStyle: { borderColor: surface, borderWidth: 2 },
            label: { color: text },
            data: cats.map((name, i) => ({ name, value: series[0].values[i] })),
          },
        ],
      }
    }
    return {
      ...base,
      grid: { left: 8, right: 16, top: series.length > 1 ? 32 : 12, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: cats,
        axisLine: { lineStyle: { color: border } },
        axisTick: { show: false },
        axisLabel: { color: muted, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: border, opacity: 0.6 } },
        axisLabel: { color: muted, formatter: (v: number) => compact(v) },
      },
      series: series.map((s) =>
        mark === 'bar'
          ? { name: s.name, type: 'bar', data: s.values, barMaxWidth: 28, barGap: '8%', itemStyle: { borderRadius: [4, 4, 0, 0] } }
          : {
              name: s.name,
              type: 'line',
              data: s.values,
              lineStyle: { width: 2 },
              symbolSize: 8,
              itemStyle: { borderColor: surface, borderWidth: 2 },
              showSymbol: cats.length <= 60,
              connectNulls: false,
            },
      ),
    }
    // `dark` no se usa dentro, pero los tokens CSS cambian con él: recalcular
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [shaped, mark, format, dark, tooManySlices])

  useEffect(() => {
    if (!host.current || !option) return
    const chart = echarts.init(host.current, undefined, { renderer: 'svg' })
    chart.setOption(option)
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(host.current)
    return () => {
      ro.disconnect()
      chart.dispose()
    }
  }, [option])

  if ('error' in shaped) return <p className="muted">{shaped.error}</p>
  if (tooManySlices) {
    return <p className="muted">Demasiadas categorías para un pastel ({rows.length}; máximo {MAX_PIE}). Usa barras.</p>
  }
  return <div className="echart" style={{ height }} ref={host} role="img" aria-label={`Gráfico de ${props.measures.join(', ')}`} />
}
