/**
 * Visual builder: model fields → Dimension / Measure / Color / Filters shelves.
 * Native HTML5 drag-and-drop, plus clicking a field as an alternative (keyboard / accessibility).
 * The chart type is limited to `allowed_marks` (GET /api/compat); the backend generates the SQL.
 */
import type { EChartsType } from 'echarts/core'
import { useState, type DragEvent } from 'react'

import type { Schemas } from '../api/client'
import { useCompat, useVisualQuery } from '../api/queries'
import { useT, type MessageKey } from '../i18n'
import { GRAIN_LABEL, MARK_LABEL } from '../render/labels'
import { VisualChart } from '../render/VisualChart'
import { VisualDownloads } from '../render/VisualDownloads'
import { AddToReport } from '../reports/AddToReport'
import type { VisualDraft } from '../store'
import { slug, visualYaml } from './draft'

type Model = Schemas['SemanticModel']
type Filter = Schemas['Filter']
type FilterOp = Schemas['FilterOp']
type Shelf = 'dimension' | 'measure' | 'color' | 'filters'
interface DragField {
  kind: 'dimension' | 'measure'
  name: string
}

const DND = 'application/x-d2h-field'
const ACCEPTS: Record<Shelf, DragField['kind']> = { dimension: 'dimension', measure: 'measure', color: 'dimension', filters: 'dimension' }
const OPS: { op: FilterOp; label: MessageKey }[] = [
  { op: 'eq', label: 'op.eq' },
  { op: 'neq', label: 'op.neq' },
  { op: 'in', label: 'op.in' },
  { op: 'gte', label: 'op.gte' },
  { op: 'lte', label: 'op.lte' },
  { op: 'between', label: 'op.between' },
]
const TYPE_ICON: Record<Schemas['FieldType'], string> = { nominal: 'Aa', ordinal: '1→', temporal: '📅', quantitative: '#' }

const EMPTY: VisualDraft = { mark: 'bar', measure: '', filters: [] }

function isComplete(f: Filter): boolean {
  const v = f.value
  if (Array.isArray(v)) return v.length > 0 && v.every((x) => String(x).trim() !== '')
  return v !== null && v !== undefined && String(v).trim() !== ''
}

export function Builder({ model, preset }: { model: Model; preset: VisualDraft | null }) {
  const t = useT()
  const [v, setV] = useState<VisualDraft>(() => preset ?? { ...EMPTY, measure: Object.keys(model.measures)[0] ?? '' })
  const [over, setOver] = useState<Shelf | null>(null)
  const [copied, setCopied] = useState(false)
  const [adding, setAdding] = useState(false)
  const [chart, setChart] = useState<EChartsType | null>(null)

  const dim = v.dimension ? model.dimensions[v.dimension] : undefined
  const compat = useCompat(dim?.type ?? null, Boolean(v.color))
  const allowed = compat.data?.marks ?? []
  const mark = allowed.includes(v.mark) ? v.mark : (allowed.find((m) => m !== 'table') ?? allowed[0] ?? v.mark)
  const ready = Boolean(v.measure) && allowed.includes(mark)
  // half-typed filters are not sent: they would filter by '' and empty the chart
  const filters = (v.filters ?? []).filter(isComplete)
  const request = ready ? { model: model.name, visual: { ...v, mark, filters } } : null
  const result = useVisualQuery(request)
  const measure = v.measure ? model.measures[v.measure] : undefined

  const place = (shelf: Shelf, name: string) => {
    if (shelf === 'measure') setV({ ...v, measure: name })
    else if (shelf === 'dimension') {
      const temporal = model.dimensions[name]?.type === 'temporal'
      setV({ ...v, dimension: name, time_grain: temporal ? (v.time_grain ?? 'month') : null })
    } else if (shelf === 'color') setV({ ...v, color: name === v.dimension ? null : name })
    else setV({ ...v, filters: [...(v.filters ?? []), { dimension: name, op: 'eq', value: '' }] })
  }
  /** Clicking a field: to the first free shelf that accepts it. */
  const quickAdd = (f: DragField) => {
    if (f.kind === 'measure') return place('measure', f.name)
    if (!v.dimension) return place('dimension', f.name)
    if (!v.color && f.name !== v.dimension) return place('color', f.name)
    place('filters', f.name)
  }

  const dropProps = (shelf: Shelf) => ({
    onDragOver: (e: DragEvent) => {
      if (e.dataTransfer.types.includes(DND)) {
        e.preventDefault()
        setOver(shelf)
      }
    },
    onDragLeave: () => setOver(null),
    onDrop: (e: DragEvent) => {
      setOver(null)
      const f = JSON.parse(e.dataTransfer.getData(DND)) as DragField
      if (f.kind === ACCEPTS[shelf]) place(shelf, f.name)
    },
    'data-over': over === shelf,
    'data-accepts': ACCEPTS[shelf],
  })

  const measureName = v.measure || t('builder.measurePlaceholder')
  const title = v.dimension ? t('builder.title', { measure: measureName, dimension: v.dimension }) : measureName

  return (
    <div className="builder">
      <aside className="fields" aria-label={t('builder.fields')}>
        <h3>{t('model.dimensions')}</h3>
        {Object.entries(model.dimensions).map(([name, d]) => (
          <FieldChip key={name} field={{ kind: 'dimension', name }} icon={TYPE_ICON[d.type]} hint={d.description} onAdd={quickAdd} />
        ))}
        <h3>{t('model.measures')}</h3>
        {Object.entries(model.measures).map(([name, m]) => (
          <FieldChip key={name} field={{ kind: 'measure', name }} icon="Σ" hint={`${m.sql} — ${m.description}`} onAdd={quickAdd} />
        ))}
        <p className="muted small">{t('builder.dragHint')}</p>
      </aside>

      <div className="canvas">
        <div className="shelves">
          <div className="shelf" {...dropProps('dimension')}>
            <span className="shelf-label">{t('builder.shelf.dimension')}</span>
            {v.dimension ? (
              <Pill name={v.dimension} onRemove={() => setV({ ...v, dimension: null, time_grain: null })} />
            ) : (
              <span className="muted small">{t('builder.dropDimension')}</span>
            )}
            {dim?.type === 'temporal' && (
              <select
                value={v.time_grain ?? ''}
                onChange={(e) => setV({ ...v, time_grain: (e.target.value || null) as VisualDraft['time_grain'] })}
                aria-label={t('builder.timeGrain')}
              >
                <option value="">{t('builder.ungrouped')}</option>
                {Object.entries(GRAIN_LABEL).map(([g, label]) => (
                  <option key={g} value={g}>
                    {t(label)}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="shelf" {...dropProps('measure')}>
            <span className="shelf-label">{t('builder.shelf.measure')}</span>
            {v.measure ? <Pill name={v.measure} kind="measure" /> : <span className="muted small">{t('builder.dropMeasure')}</span>}
          </div>
          <div className="shelf" {...dropProps('color')}>
            <span className="shelf-label">{t('builder.shelf.color')}</span>
            {v.color ? <Pill name={v.color} onRemove={() => setV({ ...v, color: null })} /> : <span className="muted small">{t('builder.optional')}</span>}
          </div>
          <div className="shelf shelf-filters" {...dropProps('filters')}>
            <span className="shelf-label">{t('builder.shelf.filters')}</span>
            {(v.filters ?? []).length === 0 && <span className="muted small">{t('builder.dropFilters')}</span>}
            {(v.filters ?? []).map((f, i) => (
              <FilterEditor
                key={i}
                filter={f}
                onChange={(nf) => setV({ ...v, filters: v.filters!.map((x, j) => (j === i ? nf : x)) })}
                onRemove={() => setV({ ...v, filters: v.filters!.filter((_, j) => j !== i) })}
              />
            ))}
          </div>
        </div>

        <div className="builder-bar">
          <div className="seg" role="radiogroup" aria-label={t('quick.chartType')}>
            {allowed.map((m) => (
              <button key={m} type="button" role="radio" aria-checked={mark === m} onClick={() => setV({ ...v, mark: m })}>
                {t(MARK_LABEL[m])}
              </button>
            ))}
          </div>
          <span className="muted small">{t('builder.compatHint')}</span>
          <button
            type="button"
            className="btn small"
            disabled={!ready}
            onClick={() => {
              void navigator.clipboard?.writeText(visualYaml({ ...v, mark, filters }, title)).then(() => {
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              })
            }}
          >
            {copied ? t('builder.copied') : t('builder.copyYaml')}
          </button>
          <button type="button" className="btn small primary" disabled={!ready} onClick={() => setAdding(true)}>
            {t('builder.addToReport')}
          </button>
          <VisualDownloads request={request} chart={result.data ? chart : null} name={slug(title, 'visual')} />
        </div>

        <section className="preview" aria-busy={result.isFetching}>
          <h3>{title}</h3>
          {measure && <p className="muted small">{measure.description}</p>}
          {!v.measure && <p className="muted">{t('builder.pickMeasure')}</p>}
          {result.isError && <p className="error">{result.error.message}</p>}
          {result.data && v.measure && (
            <>
              <VisualChart
                mark={mark}
                columns={result.data.columns}
                rows={result.data.rows}
                dimension={v.dimension ?? null}
                color={v.color ?? null}
                measures={[v.measure]}
                format={measure?.format}
                timeGrain={v.time_grain ?? null}
                onChart={setChart}
              />
              <details className="sql-details">
                <summary className="muted small">{t('builder.generatedSql')}</summary>
                <pre className="mono">{result.data.sql}</pre>
              </details>
            </>
          )}
        </section>
      </div>
      {adding && (
        <AddToReport model={model.name} visual={{ ...v, mark, filters }} title={title} onClose={() => setAdding(false)} />
      )}
    </div>
  )
}

function FieldChip({ field, icon, hint, onAdd }: { field: DragField; icon: string; hint?: string | null; onAdd: (f: DragField) => void }) {
  return (
    <button
      type="button"
      className={`field-chip ${field.kind}`}
      draggable
      title={hint ?? undefined}
      onDragStart={(e) => {
        e.dataTransfer.setData(DND, JSON.stringify(field))
        e.dataTransfer.effectAllowed = 'copy'
      }}
      onClick={() => onAdd(field)}
    >
      <span className="field-icon" aria-hidden>
        {icon}
      </span>
      {field.name}
    </button>
  )
}

function Pill({ name, kind = 'dimension', onRemove }: { name: string; kind?: 'dimension' | 'measure'; onRemove?: () => void }) {
  const t = useT()
  return (
    <span className={`pill ${kind}`}>
      {name}
      {onRemove && (
        <button type="button" className="chip-x" aria-label={t('common.remove', { name })} onClick={onRemove}>
          ✕
        </button>
      )}
    </span>
  )
}

function FilterEditor({ filter, onChange, onRemove }: { filter: Filter; onChange: (f: Filter) => void; onRemove: () => void }) {
  const t = useT()
  const raw = filter.value
  const list = Array.isArray(raw) ? raw.map(String) : raw === null || raw === undefined ? [] : [String(raw)]
  const setOp = (op: FilterOp) => {
    const value = op === 'between' ? [list[0] ?? '', list[1] ?? ''] : op === 'in' ? list : (list[0] ?? '')
    onChange({ ...filter, op, value })
  }
  return (
    <span className="pill filter-pill">
      <span>{filter.dimension}</span>
      <select value={filter.op} onChange={(e) => setOp(e.target.value as FilterOp)} aria-label={t('filter.operator')}>
        {OPS.map((o) => (
          <option key={o.op} value={o.op}>
            {t(o.label)}
          </option>
        ))}
      </select>
      {filter.op === 'between' ? (
        <>
          <input value={list[0] ?? ''} onChange={(e) => onChange({ ...filter, value: [e.target.value, list[1] ?? ''] })} aria-label={t('filter.from')} />
          <input value={list[1] ?? ''} onChange={(e) => onChange({ ...filter, value: [list[0] ?? '', e.target.value] })} aria-label={t('filter.toLabel')} />
        </>
      ) : (
        <input
          value={filter.op === 'in' ? list.join(', ') : (list[0] ?? '')}
          placeholder={filter.op === 'in' ? 'a, b, c' : t('filter.value')}
          onChange={(e) =>
            onChange({
              ...filter,
              value: filter.op === 'in' ? e.target.value.split(',').map((x) => x.trim()).filter(Boolean) : e.target.value,
            })
          }
          aria-label={t('filter.valueLabel')}
        />
      )}
      <button type="button" className="chip-x" aria-label={t('filter.remove', { filter: filter.dimension })} onClick={onRemove}>
        ✕
      </button>
    </span>
  )
}
