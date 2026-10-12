/**
 * Constructor visual: campos del modelo → repisas Dimensión / Medida / Color / Filtros.
 * Drag-and-drop nativo de HTML5, y clic en un campo como alternativa (teclado / accesibilidad).
 * El tipo de gráfico se limita a `allowed_marks` (GET /api/compat); el SQL lo genera el backend.
 */
import { useState, type DragEvent } from 'react'

import type { Schemas } from '../api/client'
import { useCompat, useVisualQuery } from '../api/queries'
import { GRAIN_LABEL, MARK_LABEL } from '../render/labels'
import { VisualChart } from '../render/VisualChart'
import type { VisualDraft } from '../store'
import { visualYaml } from './draft'

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
const OPS: { op: FilterOp; label: string }[] = [
  { op: 'eq', label: '=' },
  { op: 'neq', label: '≠' },
  { op: 'in', label: 'es uno de' },
  { op: 'gte', label: '≥' },
  { op: 'lte', label: '≤' },
  { op: 'between', label: 'entre' },
]
const TYPE_ICON: Record<Schemas['FieldType'], string> = { nominal: 'Aa', ordinal: '1→', temporal: '📅', quantitative: '#' }

const EMPTY: VisualDraft = { mark: 'bar', measure: '', filters: [] }

function isComplete(f: Filter): boolean {
  const v = f.value
  if (Array.isArray(v)) return v.length > 0 && v.every((x) => String(x).trim() !== '')
  return v !== null && v !== undefined && String(v).trim() !== ''
}

export function Builder({ model, preset }: { model: Model; preset: VisualDraft | null }) {
  const [v, setV] = useState<VisualDraft>(() => preset ?? { ...EMPTY, measure: Object.keys(model.measures)[0] ?? '' })
  const [over, setOver] = useState<Shelf | null>(null)
  const [copied, setCopied] = useState(false)

  const dim = v.dimension ? model.dimensions[v.dimension] : undefined
  const compat = useCompat(dim?.type ?? null, Boolean(v.color))
  const allowed = compat.data?.marks ?? []
  const mark = allowed.includes(v.mark) ? v.mark : (allowed.find((m) => m !== 'table') ?? allowed[0] ?? v.mark)
  const ready = Boolean(v.measure) && allowed.includes(mark)
  // los filtros a medio escribir no se envían: filtrarían por '' y vaciarían el gráfico
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
  /** Clic en un campo: a la primera repisa libre que lo acepte. */
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

  const title = `${v.measure || 'medida'}${v.dimension ? ` por ${v.dimension}` : ''}`

  return (
    <div className="builder">
      <aside className="fields" aria-label="Campos del modelo">
        <h3>Dimensiones</h3>
        {Object.entries(model.dimensions).map(([name, d]) => (
          <FieldChip key={name} field={{ kind: 'dimension', name }} icon={TYPE_ICON[d.type]} hint={d.description} onAdd={quickAdd} />
        ))}
        <h3>Medidas</h3>
        {Object.entries(model.measures).map(([name, m]) => (
          <FieldChip key={name} field={{ kind: 'measure', name }} icon="Σ" hint={`${m.sql} — ${m.description}`} onAdd={quickAdd} />
        ))}
        <p className="muted small">Arrastra a una repisa o haz clic para añadir.</p>
      </aside>

      <div className="canvas">
        <div className="shelves">
          <div className="shelf" {...dropProps('dimension')}>
            <span className="shelf-label">Dimensión</span>
            {v.dimension ? (
              <Pill name={v.dimension} onRemove={() => setV({ ...v, dimension: null, time_grain: null })} />
            ) : (
              <span className="muted small">arrastra una dimensión</span>
            )}
            {dim?.type === 'temporal' && (
              <select value={v.time_grain ?? ''} onChange={(e) => setV({ ...v, time_grain: (e.target.value || null) as VisualDraft['time_grain'] })} aria-label="Grano de tiempo">
                <option value="">sin agrupar</option>
                {Object.entries(GRAIN_LABEL).map(([g, label]) => (
                  <option key={g} value={g}>
                    por {label}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="shelf" {...dropProps('measure')}>
            <span className="shelf-label">Medida</span>
            {v.measure ? <Pill name={v.measure} kind="measure" /> : <span className="muted small">arrastra una medida</span>}
          </div>
          <div className="shelf" {...dropProps('color')}>
            <span className="shelf-label">Color</span>
            {v.color ? <Pill name={v.color} onRemove={() => setV({ ...v, color: null })} /> : <span className="muted small">opcional</span>}
          </div>
          <div className="shelf shelf-filters" {...dropProps('filters')}>
            <span className="shelf-label">Filtros</span>
            {(v.filters ?? []).length === 0 && <span className="muted small">arrastra dimensiones</span>}
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
          <div className="seg" role="radiogroup" aria-label="Tipo de gráfico">
            {allowed.map((m) => (
              <button key={m} type="button" role="radio" aria-checked={mark === m} onClick={() => setV({ ...v, mark: m })}>
                {MARK_LABEL[m]}
              </button>
            ))}
          </div>
          <span className="muted small">Solo se ofrecen los tipos compatibles con la dimensión elegida.</span>
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
            {copied ? '¡Copiado!' : 'Copiar YAML'}
          </button>
        </div>

        <section className="preview" aria-busy={result.isFetching}>
          <h3>{title}</h3>
          {measure && <p className="muted small">{measure.description}</p>}
          {!v.measure && <p className="muted">Elige una medida.</p>}
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
              />
              <details className="sql-details">
                <summary className="muted small">SQL generado</summary>
                <pre className="mono">{result.data.sql}</pre>
              </details>
            </>
          )}
        </section>
      </div>
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
  return (
    <span className={`pill ${kind}`}>
      {name}
      {onRemove && (
        <button type="button" className="chip-x" aria-label={`Quitar ${name}`} onClick={onRemove}>
          ✕
        </button>
      )}
    </span>
  )
}

function FilterEditor({ filter, onChange, onRemove }: { filter: Filter; onChange: (f: Filter) => void; onRemove: () => void }) {
  const raw = filter.value
  const list = Array.isArray(raw) ? raw.map(String) : raw === null || raw === undefined ? [] : [String(raw)]
  const setOp = (op: FilterOp) => {
    const value = op === 'between' ? [list[0] ?? '', list[1] ?? ''] : op === 'in' ? list : (list[0] ?? '')
    onChange({ ...filter, op, value })
  }
  return (
    <span className="pill filter-pill">
      <span>{filter.dimension}</span>
      <select value={filter.op} onChange={(e) => setOp(e.target.value as FilterOp)} aria-label="Operador">
        {OPS.map((o) => (
          <option key={o.op} value={o.op}>
            {o.label}
          </option>
        ))}
      </select>
      {filter.op === 'between' ? (
        <>
          <input value={list[0] ?? ''} onChange={(e) => onChange({ ...filter, value: [e.target.value, list[1] ?? ''] })} aria-label="Desde" />
          <input value={list[1] ?? ''} onChange={(e) => onChange({ ...filter, value: [list[0] ?? '', e.target.value] })} aria-label="Hasta" />
        </>
      ) : (
        <input
          value={filter.op === 'in' ? list.join(', ') : (list[0] ?? '')}
          placeholder={filter.op === 'in' ? 'a, b, c' : 'valor'}
          onChange={(e) =>
            onChange({
              ...filter,
              value: filter.op === 'in' ? e.target.value.split(',').map((x) => x.trim()).filter(Boolean) : e.target.value,
            })
          }
          aria-label="Valor"
        />
      )}
      <button type="button" className="chip-x" aria-label={`Quitar filtro ${filter.dimension}`} onClick={onRemove}>
        ✕
      </button>
    </span>
  )
}
