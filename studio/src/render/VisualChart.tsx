/**
 * Renders a visual from ALREADY aggregated rows (it never re-aggregates). Used by the SQL editor's quick
 * view, the builder and the report editor. The live viewer has the same mapping in plain JS
 * (backend/src/data2html/render/static/viewer.js): change both together.
 *
 * Mapping (html-renderer skill): bar/line/pie → ECharts; kpi → formatted number; table → DOM <table>
 * (React escapes the text). Style (dataviz skill): one hue per series in the validated palette's fixed
 * order (--series-N), bars with a 4px rounded end and 2px gaps, 2px lines, 8px markers with a 2px ring,
 * recessive grid, legend only with ≥2 series, tooltip always.
 */
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption, EChartsType } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useEffect, useMemo, useRef } from 'react'

import type { Schemas } from '../api/client'
import { t as translate, useLang, useT, type MessageKey, type Params } from '../i18n'
import type { Cell, Column } from '../explore/usePagedRows'
import { usePrefersDark } from '../explore/usePrefersDark'
import { formatPeriod } from '../i18n/format'
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
  /** Temporal dimension grouped by period: its values are labelled by the grain ("abr 2025"). */
  timeGrain?: Schemas['TimeGrain'] | null
  format?: Schemas['MeasureFormat']
  height?: number
  /** The ECharts instance while one is drawn (null otherwise): for PNG downloads. */
  onChart?: (chart: EChartsType | null) => void
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function VisualChart(props: VisualChartProps) {
  const t = useT()
  const { mark, columns, rows, measures } = props
  if (mark === 'table') return <DataTable columns={columns} rows={rows} format={props.format} measures={measures} dimension={props.dimension} timeGrain={props.timeGrain} />
  if (mark === 'kpi') return <Kpi {...props} />
  if (rows.length === 0) return <p className="muted">{t('chart.noRows')}</p>
  return <EChart {...props} />
}

function DataTable({ columns, rows, format, measures, dimension, timeGrain }: Pick<VisualChartProps, 'columns' | 'rows' | 'format' | 'measures' | 'dimension' | 'timeGrain'>) {
  const fmt = formatter(format)
  const di = dimension ? columns.findIndex((c) => c.name === dimension) : -1
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
                    {v === null ? '∅' : isMeasure && typeof v === 'number' ? fmt(v) : j === di && timeGrain && typeof v === 'string' ? formatPeriod(v, timeGrain) : String(v)}
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
  const t = useT()
  if (rows.length !== 1) return <p className="muted">{t('chart.kpiOneRow')}</p>
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

/** Rows → categories and series. With `color`, one series per value (a pivot, not an aggregation). */
function toSeries(
  props: VisualChartProps,
): { cats: string[]; series: Series[] } | { error: MessageKey; params: Params } {
  const { columns, rows, dimension, color, measures } = props
  const idx = (name: string) => columns.findIndex((c) => c.name === name)
  const di = dimension ? idx(dimension) : -1
  const num = (v: Cell) => (typeof v === 'number' ? v : v === null ? null : Number(v))
  const plain = (v: Cell) => (v === null ? '∅' : String(v))
  const grain = props.timeGrain
  const label = (v: Cell) => (grain && typeof v === 'string' ? formatPeriod(v, grain) : plain(v))
  if (color) {
    const ci = idx(color)
    const mi = idx(measures[0])
    const cats = [...new Set(rows.map((r) => label(r[di])))]
    const names = [...new Set(rows.map((r) => label(r[ci])))]
    if (names.length > MAX_SERIES) {
      return { error: 'chart.tooManyColors', params: { n: names.length, max: MAX_SERIES } }
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

const PIE_LABEL_MIN_WIDTH = 380

/** Pie slice labels only when the chart is wide enough to show them whole; otherwise the legend and the
 * tooltip identify the slices. Same rule as the viewer (render/static/viewer.js). */
function fitPieLabels(chart: echarts.ECharts) {
  const series = (chart.getOption() as { series?: { type?: string }[] }).series
  if (series?.[0]?.type !== 'pie') return
  const show = chart.getWidth() >= PIE_LABEL_MIN_WIDTH
  chart.setOption({ series: [{ label: { show }, labelLine: { show }, radius: ['0%', show ? '62%' : '72%'] }] })
}

function EChart(props: VisualChartProps) {
  const { mark, rows, format, height = 360 } = props
  const host = useRef<HTMLDivElement>(null)
  const t = useT()
  const lang = useLang()
  const dark = usePrefersDark()
  // Keyed by content, not by the props object: parents pass fresh arrays (`measures={[m]}`) on every
  // render, and `onChart` re-renders the parent, which would re-create the chart in a loop.
  const dataKey = JSON.stringify([props.columns, props.rows, props.dimension, props.color, props.measures, props.timeGrain])
  // oxlint-disable-next-line react-hooks/exhaustive-deps
  const shaped = useMemo(() => toSeries(props), [dataKey])
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
            radius: ['0%', '62%'],
            itemStyle: { borderColor: surface, borderWidth: 2 },
            label: { color: text, overflow: 'none' },
            labelLine: { length: 10, length2: 8 },
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
    // `dark` and `lang` are not used directly: CSS tokens and number formats change with them
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [shaped, mark, format, dark, lang, tooManySlices])

  const onChart = useRef(props.onChart)
  onChart.current = props.onChart

  useEffect(() => {
    if (!host.current || !option) return
    const chart = echarts.init(host.current, undefined, { renderer: 'svg' })
    chart.setOption(option)
    fitPieLabels(chart)
    onChart.current?.(chart)
    const ro = new ResizeObserver(() => {
      chart.resize()
      fitPieLabels(chart)
    })
    ro.observe(host.current)
    return () => {
      ro.disconnect()
      onChart.current?.(null)
      chart.dispose()
    }
  }, [option])

  if ('error' in shaped) return <p className="muted">{translate(shaped.error, shaped.params)}</p>
  if (tooManySlices) {
    return <p className="muted">{t('chart.tooManySlices', { n: rows.length, max: MAX_PIE })}</p>
  }
  return (
    <div
      className="echart"
      style={{ height }}
      ref={host}
      role="img"
      aria-label={t('chart.ariaLabel', { measures: props.measures.join(', ') })}
    />
  )
}
