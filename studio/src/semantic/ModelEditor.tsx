import { useEffect, useState } from 'react'

import type { Schemas } from '../api/client'
import { useCatalog, useCheckModel, useDeleteModel, useSaveModel } from '../api/queries'
import { useT, type MessageKey } from '../i18n'
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
const TYPE_LABEL: Record<Schemas['FieldType'], MessageKey> = {
  nominal: 'fieldType.nominal',
  ordinal: 'fieldType.ordinal',
  temporal: 'fieldType.temporal',
  quantitative: 'fieldType.quantitative',
}
const FORMATS: { v: Schemas['MeasureFormat']; label: MessageKey }[] = [
  { v: 'number', label: 'format.number' },
  { v: 'currency', label: 'format.currency' },
  { v: 'percent', label: 'format.percent' },
]

/** Wait `ms` without changes before returning the value (live validation without a request per keystroke). */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setV(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return v
}

interface Props {
  initial: ModelDraft
  isNew: boolean
}

export function ModelEditor({ initial, isNew }: Props) {
  const t = useT()
  const [d, setD] = useState<ModelDraft>(initial)
  const catalog = useCatalog()
  const save = useSaveModel()
  const del = useDeleteModel()
  const openModels = useStudio((s) => s.openModels)

  const sources = catalog.data?.sources ?? []
  const tables = sources.find((s) => s.id === d.source)?.tables ?? []
  const table = tables.find((x) => x.name === d.table)
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
        { key: nextKey(), name: `measure_${d.measures.length + 1}`, sql: 'COUNT(*)', format: 'number', owner: '', description: '' },
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
          <span>{t('model.name')}</span>
          <input
            className="mono"
            value={d.name}
            disabled={!isNew}
            onChange={(e) => set({ name: e.target.value })}
            aria-invalid={!IDENT.test(d.name)}
          />
        </label>
        <label className="field">
          <span>{t('sql.source')}</span>
          <select value={d.source} onChange={(e) => set({ source: e.target.value, table: '' })}>
            {sources.map((s) => (
              <option key={s.id} value={s.id} disabled={s.status !== 'ok'}>
                {s.id}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t('model.table')}</span>
          <select value={d.table} onChange={(e) => set({ table: e.target.value })}>
            <option value="">{t('model.pick')}</option>
            {tables.map((x) => (
              <option key={x.name}>{x.name}</option>
            ))}
          </select>
        </label>
      </section>

      <section>
        <header className="me-section-head">
          <h3>{t('model.dimensions')}</h3>
          <button type="button" className="btn small" onClick={() => addDims(unusedColumns.slice(0, 1))} disabled={!unusedColumns.length}>
            {t('model.addDimension')}
          </button>
          {unusedColumns.length > 1 && (
            <button type="button" className="btn small ghost" onClick={() => addDims(unusedColumns)}>
              {t('model.addAllColumns')}
            </button>
          )}
        </header>
        <table className="grid me-table">
          <thead>
            <tr>
              <th>{t('model.name')}</th>
              <th>{t('schema.column')}</th>
              <th>{t('schema.type')}</th>
              <th>{t('schema.description')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {d.dimensions.map((x) => (
              <tr key={x.key}>
                <td>
                  <input className="mono" value={x.name} onChange={(e) => setDim(x.key, { name: e.target.value })} aria-invalid={!IDENT.test(x.name)} aria-label={t('model.dimensionName')} />
                </td>
                <td>
                  <select value={x.column} onChange={(e) => setDim(x.key, { column: e.target.value })} aria-label={t('schema.column')}>
                    {!columns.some((c) => c.name === x.column) && <option>{x.column}</option>}
                    {columns.map((c) => (
                      <option key={c.name}>{c.name}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select value={x.type} onChange={(e) => setDim(x.key, { type: e.target.value as Schemas['FieldType'] })} aria-label={t('schema.type')}>
                    {TYPES.map((ty) => (
                      <option key={ty} value={ty}>
                        {t(TYPE_LABEL[ty])}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input value={x.description} onChange={(e) => setDim(x.key, { description: e.target.value })} aria-label={t('schema.description')} />
                </td>
                <td>
                  <button type="button" className="chip-x" aria-label={t('common.remove', { name: x.name })} onClick={() => set({ dimensions: d.dimensions.filter((y) => y.key !== x.key) })}>
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
          <h3>{t('model.measures')}</h3>
          <button type="button" className="btn small" onClick={addMeasure}>
            {t('model.addMeasure')}
          </button>
          <span className="muted small">{t('model.measureHint')}</span>
        </header>
        <div className="me-measures">
          {d.measures.map((m) => (
            <fieldset key={m.key} className="me-measure">
              <input className="mono" value={m.name} onChange={(e) => setMeasure(m.key, { name: e.target.value })} aria-invalid={!IDENT.test(m.name)} aria-label={t('model.measureName')} />
              <input className="mono me-sql" value={m.sql} onChange={(e) => setMeasure(m.key, { sql: e.target.value })} aria-label={t('model.measureSql')} spellCheck={false} />
              <select value={m.format} onChange={(e) => setMeasure(m.key, { format: e.target.value as Schemas['MeasureFormat'] })} aria-label={t('measure.format')}>
                {FORMATS.map((f) => (
                  <option key={f.v} value={f.v}>
                    {t(f.label)}
                  </option>
                ))}
              </select>
              <input value={m.owner} placeholder={t('model.ownerPlaceholder')} onChange={(e) => setMeasure(m.key, { owner: e.target.value })} aria-label={t('model.owner')} aria-invalid={!m.owner.trim()} />
              <input className="me-desc" value={m.description} placeholder={t('model.descriptionPlaceholder')} onChange={(e) => setMeasure(m.key, { description: e.target.value })} aria-label={t('schema.description')} aria-invalid={!m.description.trim()} />
              <button type="button" className="chip-x" aria-label={t('common.remove', { name: m.name })} onClick={() => set({ measures: d.measures.filter((y) => y.key !== m.key) })}>
                ✕
              </button>
            </fieldset>
          ))}
        </div>
      </section>

      <section>
        <header className="me-section-head">
          <h3>{t('model.rls')}</h3>
          <label className="inline small">
            <input
              type="checkbox"
              checked={d.rls !== null}
              onChange={(e) => set({ rls: e.target.checked ? { column: columns[0]?.name ?? '', claim: 'groups' } : null })}
            />
            {t('model.rlsToggle')}
          </label>
        </header>
        {d.rls && (
          <p className="small">
            {t('model.rlsStart')}{' '}
            <select value={d.rls.column} onChange={(e) => set({ rls: { ...d.rls!, column: e.target.value } })} aria-label={t('model.rlsColumn')}>
              {columns.map((c) => (
                <option key={c.name}>{c.name}</option>
              ))}
            </select>{' '}
            {t('model.rlsMiddle')}{' '}
            <select value={d.rls.claim} onChange={(e) => set({ rls: { ...d.rls!, claim: e.target.value } })} aria-label={t('model.rlsClaim')}>
              <option value="groups">{t('claim.groups')}</option>
              <option value="email">email</option>
              <option value="user_id">{t('claim.userId')}</option>
            </select>
            {t('model.rlsEnd')}
          </p>
        )}
      </section>

      <section className="me-status" aria-live="polite">
        {local.length > 0 && <ErrorList title={t('model.beforeValidating')} errors={local} />}
        {local.length === 0 && check.isFetching && <p className="muted small">{t('model.validating')}</p>}
        {shapeError && <ErrorList title={t('model.contractRejects')} errors={[shapeError]} />}
        {!check.isFetching && serverErrors.length > 0 && <ErrorList title={t('model.againstSource')} errors={serverErrors} />}
        {canSave && <p className="ok small">✓ {t('model.valid')}</p>}
      </section>

      <div className="actions">
        {save.isError && <span className="error">{save.error.message}</span>}
        {!isNew && (
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              if (window.confirm(t('model.confirmDelete', { name: d.name }))) {
                del.mutate(d.name, { onSuccess: () => openModels(null) })
              }
            }}
          >
            {t('model.delete')}
          </button>
        )}
        <button className="btn primary" disabled={!canSave || save.isPending}>
          {save.isPending ? t('common.saving') : t('model.save')}
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
