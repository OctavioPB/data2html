import { useEffect, useState } from 'react'

import type { Schemas } from '../api/client'
import { useCatalog, useCheckModel, useDeleteModel, useSaveModel } from '../api/queries'
import { useStudio } from '../store'
import {
  fromDraft,
  guessType,
  IDENT,
  localErrors,
  nextKey,
  slug,
  type DimRow,
  type MeasureRow,
  type ModelDraft,
} from './draft'

const TYPES: Schemas['FieldType'][] = ['nominal', 'ordinal', 'temporal', 'quantitative']
const TYPE_LABEL: Record<Schemas['FieldType'], string> = {
  nominal: 'nominal (categorías)',
  ordinal: 'ordinal (con orden)',
  temporal: 'temporal (fecha)',
  quantitative: 'cuantitativa',
}
const FORMATS: { v: Schemas['MeasureFormat']; label: string }[] = [
  { v: 'number', label: 'número' },
  { v: 'currency', label: 'moneda' },
  { v: 'percent', label: 'porcentaje' },
]

/** Espera `ms` sin cambios antes de devolver el valor (validación en vivo sin una petición por tecla). */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

interface Props {
  initial: ModelDraft
  isNew: boolean
}

export function ModelEditor({ initial, isNew }: Props) {
  const [d, setD] = useState<ModelDraft>(initial)
  const catalog = useCatalog()
  const save = useSaveModel()
  const del = useDeleteModel()
  const openModels = useStudio((s) => s.openModels)

  const sources = catalog.data?.sources ?? []
  const tables = sources.find((s) => s.id === d.source)?.tables ?? []
  const table = tables.find((t) => t.name === d.table)
  const columns = table?.columns ?? []

  const local = localErrors(d)
  const candidate = useDebounced(local.length === 0 ? fromDraft(d) : null, 500)
  const check = useCheckModel(candidate)
  const serverErrors = check.data ?? []
  const shapeError = check.isError ? check.error.message : null
  const canSave = local.length === 0 && !check.isFetching && !shapeError && serverErrors.length === 0

  const set = (patch: Partial<ModelDraft>) => setD((x) => ({ ...x, ...patch }))
  const setDim = (key: number, patch: Partial<DimRow>) =>
    set({ dimensions: d.dimensions.map((x) => (x.key === key ? { ...x, ...patch } : x)) })
  const setMeasure = (key: number, patch: Partial<MeasureRow>) =>
    set({ measures: d.measures.map((x) => (x.key === key ? { ...x, ...patch } : x)) })

  const unusedColumns = columns.filter((c) => !d.dimensions.some((x) => x.column === c.name))
  const addDims = (cols: Schemas['ColumnOut'][]) =>
    set({
      dimensions: [
        ...d.dimensions,
        ...cols.map((c) => ({
          key: nextKey(), name: slug(c.name), column: c.name, type: guessType(c.type), description: c.description,
        })),
      ],
    })
  const addMeasure = () =>
    set({
      measures: [
        ...d.measures,
        { key: nextKey(), name: `medida_${d.measures.length + 1}`, sql: 'COUNT(*)', format: 'number', owner: '', description: '' },
      ],
    })

  return (
    <form
      className="model-editor"
      onSubmit={(e) => {
        e.preventDefault()
        if (canSave) save.mutate(fromDraft(d), { onSuccess: () => openModels(d.name) })
      }}
    >
      <section className="me-head">
        <label className="field">
          <span>Nombre</span>
          <input
            className="mono"
            value={d.name}
            disabled={!isNew}
            onChange={(e) => set({ name: e.target.value })}
            aria-invalid={!IDENT.test(d.name)}
          />
        </label>
        <label className="field">
          <span>Fuente</span>
          <select value={d.source} onChange={(e) => set({ source: e.target.value, table: '' })}>
            {sources.map((s) => (
              <option key={s.id} value={s.id} disabled={s.status !== 'ok'}>
                {s.id}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Tabla</span>
          <select value={d.table} onChange={(e) => set({ table: e.target.value })}>
            <option value="">(elige)</option>
            {tables.map((t) => (
              <option key={t.name}>{t.name}</option>
            ))}
          </select>
        </label>
      </section>

      <section>
        <header className="me-section-head">
          <h3>Dimensiones</h3>
          <button type="button" className="btn small" onClick={() => addDims(unusedColumns.slice(0, 1))} disabled={!unusedColumns.length}>
            + Dimensión
          </button>
          {unusedColumns.length > 1 && (
            <button type="button" className="btn small ghost" onClick={() => addDims(unusedColumns)}>
              + Todas las columnas
            </button>
          )}
        </header>
        <table className="grid me-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Columna</th>
              <th>Tipo</th>
              <th>Descripción</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {d.dimensions.map((x) => (
              <tr key={x.key}>
                <td>
                  <input className="mono" value={x.name} onChange={(e) => setDim(x.key, { name: e.target.value })} aria-invalid={!IDENT.test(x.name)} aria-label="Nombre de la dimensión" />
                </td>
                <td>
                  <select value={x.column} onChange={(e) => setDim(x.key, { column: e.target.value })} aria-label="Columna">
                    {!columns.some((c) => c.name === x.column) && <option>{x.column}</option>}
                    {columns.map((c) => (
                      <option key={c.name}>{c.name}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select value={x.type} onChange={(e) => setDim(x.key, { type: e.target.value as Schemas['FieldType'] })} aria-label="Tipo">
                    {TYPES.map((t) => (
                      <option key={t} value={t}>
                        {TYPE_LABEL[t]}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input value={x.description} onChange={(e) => setDim(x.key, { description: e.target.value })} aria-label="Descripción" />
                </td>
                <td>
                  <button type="button" className="chip-x" aria-label={`Quitar ${x.name}`} onClick={() => set({ dimensions: d.dimensions.filter((y) => y.key !== x.key) })}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <header className="me-section-head">
          <h3>Medidas</h3>
          <button type="button" className="btn small" onClick={addMeasure}>
            + Medida
          </button>
          <span className="muted small">Una expresión agregada sobre columnas de la tabla, p. ej. SUM(monto - descuento).</span>
        </header>
        <div className="me-measures">
          {d.measures.map((m) => (
            <fieldset key={m.key} className="me-measure">
              <input className="mono" value={m.name} onChange={(e) => setMeasure(m.key, { name: e.target.value })} aria-invalid={!IDENT.test(m.name)} aria-label="Nombre de la medida" />
              <input className="mono me-sql" value={m.sql} onChange={(e) => setMeasure(m.key, { sql: e.target.value })} aria-label="SQL de la medida" spellCheck={false} />
              <select value={m.format} onChange={(e) => setMeasure(m.key, { format: e.target.value as Schemas['MeasureFormat'] })} aria-label="Formato">
                {FORMATS.map((f) => (
                  <option key={f.v} value={f.v}>
                    {f.label}
                  </option>
                ))}
              </select>
              <input value={m.owner} placeholder="dueño (área)" onChange={(e) => setMeasure(m.key, { owner: e.target.value })} aria-label="Dueño" aria-invalid={!m.owner.trim()} />
              <input className="me-desc" value={m.description} placeholder="¿qué mide y qué excluye?" onChange={(e) => setMeasure(m.key, { description: e.target.value })} aria-label="Descripción" aria-invalid={!m.description.trim()} />
              <button type="button" className="chip-x" aria-label={`Quitar ${m.name}`} onClick={() => set({ measures: d.measures.filter((y) => y.key !== m.key) })}>
                ✕
              </button>
            </fieldset>
          ))}
        </div>
      </section>

      <section>
        <header className="me-section-head">
          <h3>Seguridad por fila (RLS)</h3>
          <label className="inline small">
            <input
              type="checkbox"
              checked={d.rls !== null}
              onChange={(e) => set({ rls: e.target.checked ? { column: columns[0]?.name ?? '', claim: 'groups' } : null })}
            />
            filtrar por la identidad del lector
          </label>
        </header>
        {d.rls && (
          <p className="small">
            Cada lector ve solo las filas donde{' '}
            <select value={d.rls.column} onChange={(e) => set({ rls: { ...d.rls!, column: e.target.value } })} aria-label="Columna RLS">
              {columns.map((c) => (
                <option key={c.name}>{c.name}</option>
              ))}
            </select>{' '}
            esté en su{' '}
            <select value={d.rls.claim} onChange={(e) => set({ rls: { ...d.rls!, claim: e.target.value } })} aria-label="Atributo de identidad">
              <option value="groups">grupos</option>
              <option value="email">email</option>
              <option value="user_id">usuario</option>
            </select>
            . En el studio (autor) se ve todo.
          </p>
        )}
      </section>

      <section className="me-status" aria-live="polite">
        {local.length > 0 && <ErrorList title="Antes de validar" errors={local} />}
        {local.length === 0 && check.isFetching && <p className="muted small">Validando contra la fuente…</p>}
        {shapeError && <ErrorList title="El contrato rechaza el modelo" errors={[shapeError]} />}
        {!check.isFetching && serverErrors.length > 0 && <ErrorList title="Contra la fuente" errors={serverErrors} />}
        {canSave && <p className="ok small">✓ El modelo es válido y todas las medidas corren contra la fuente.</p>}
      </section>

      <div className="actions">
        {save.isError && <span className="error">{save.error.message}</span>}
        {!isNew && (
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              if (window.confirm(`¿Borrar el modelo '${d.name}'? El YAML se elimina de content/semantic/.`)) {
                del.mutate(d.name, { onSuccess: () => openModels(null) })
              }
            }}
          >
            Borrar
          </button>
        )}
        <button className="btn primary" disabled={!canSave || save.isPending}>
          {save.isPending ? 'Guardando…' : 'Guardar modelo'}
        </button>
      </div>
    </form>
  )
}

function ErrorList({ title, errors }: { title: string; errors: string[] }) {
  return (
    <div className="error-list">
      <strong className="small">{title}</strong>
      <ul>
        {errors.map((e) => (
          <li key={e}>{e}</li>
        ))}
      </ul>
    </div>
  )
}
