/**
 * "Publicar como medida…": la consulta del editor SQL se convierte en una medida (+ dimensión) del modelo
 * semántico de su tabla, con dueño y descripción. Luego abre el constructor con ese visual. Así el número
 * queda definido una vez en el modelo (ADR 0004), no incrustado en un visual.
 */
import { useEffect, useState } from 'react'

import { api, type Schemas } from '../api/client'
import { errorMessage, useSaveModel, useSuggest } from '../api/queries'
import { fromDraft, IDENT, nextKey, slug, toDraft, type ModelDraft } from '../semantic/draft'
import { useStudio } from '../store'

interface Props {
  source: string
  sql: string
  onClose: () => void
}

export function PromoteDialog({ source, sql, onClose }: Props) {
  const suggest = useSuggest()
  const save = useSaveModel()
  const openModels = useStudio((s) => s.openModels)
  const [modelName, setModelName] = useState('')
  const [measureName, setMeasureName] = useState('')
  const [dimName, setDimName] = useState('')
  const [format, setFormat] = useState<Schemas['MeasureFormat']>('number')
  const [owner, setOwner] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    suggest.mutate(
      { source, sql },
      {
        onSuccess: (s) => {
          setModelName(s.model ?? slug(s.table.split('.').pop() ?? s.table, 'modelo'))
          setMeasureName(s.measure_name)
          setDimName(s.dimension?.name ?? '')
        },
      },
    )
    // una sugerencia por apertura del diálogo
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const s = suggest.data
  const valid =
    s && IDENT.test(modelName) && IDENT.test(measureName) && (!s.dimension || IDENT.test(dimName)) &&
    (s.measure_exists || (owner.trim() && description.trim()))

  const confirm = async () => {
    if (!s || !valid) return
    setError(null)
    // modelo existente (si lo hay) + lo que falte
    let draft: ModelDraft = { name: modelName, source: s.source, table: s.table, dimensions: [], measures: [], rls: null }
    if (s.model) {
      const { data, error: err, response } = await api.GET('/api/semantic/{name}', { params: { path: { name: s.model } } })
      if (!data) return setError(errorMessage(err, response.status))
      draft = toDraft(data.model)
    }
    if (s.dimension && !s.dimension.exists && !draft.dimensions.some((d) => d.name === dimName)) {
      draft.dimensions.push({ key: nextKey(), name: dimName, column: s.dimension.column, type: s.dimension.type, description: '' })
    }
    if (!s.measure_exists) {
      draft.measures.push({ key: nextKey(), name: measureName, sql: s.measure_sql, format, owner, description })
    }
    save.mutate(fromDraft(draft), {
      onSuccess: () => {
        openModels(draft.name, {
          mark: s.dimension ? 'bar' : 'kpi',
          measure: measureName,
          dimension: s.dimension ? dimName : null,
          time_grain: s.dimension?.type === 'temporal' ? 'month' : null,
          filters: [],
        })
        onClose()
      },
      onError: (e) => setError(e.message),
    })
  }

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal aria-labelledby="promote-title">
        <header>
          <h2 id="promote-title">Publicar como medida</h2>
          <button className="btn ghost" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </header>
        {suggest.isPending && <p className="muted">Analizando la consulta…</p>}
        {suggest.isError && <p className="error">{suggest.error.message}</p>}
        {s && (
          <>
            <p className="muted small">
              La medida se define una sola vez en el modelo de <span className="mono">{s.source}.{s.table}</span>; los
              visuales solo la nombran.
            </p>
            {s.warnings.map((w) => (
              <p key={w} className="warnings">
                ⚠ {w}
              </p>
            ))}
            <label className="field">
              <span>Modelo {s.model ? '(existente)' : '(nuevo)'}</span>
              <input className="mono" value={modelName} disabled={Boolean(s.model)} onChange={(e) => setModelName(e.target.value)} aria-invalid={!IDENT.test(modelName)} />
            </label>
            <label className="field">
              <span>Medida {s.measure_exists && '(ya existe en el modelo: se reutiliza)'}</span>
              <input className="mono" value={measureName} disabled={s.measure_exists} onChange={(e) => setMeasureName(e.target.value)} aria-invalid={!IDENT.test(measureName)} />
            </label>
            <pre className="mono promote-sql">{s.measure_sql}</pre>
            {!s.measure_exists && (
              <div className="promote-grid">
                <label className="field">
                  <span>Formato</span>
                  <select value={format} onChange={(e) => setFormat(e.target.value as Schemas['MeasureFormat'])}>
                    <option value="number">número</option>
                    <option value="currency">moneda</option>
                    <option value="percent">porcentaje</option>
                  </select>
                </label>
                <label className="field">
                  <span>Dueño (área responsable)</span>
                  <input value={owner} onChange={(e) => setOwner(e.target.value)} aria-invalid={!owner.trim()} />
                </label>
                <label className="field promote-desc">
                  <span>Descripción (qué mide y qué excluye)</span>
                  <input value={description} onChange={(e) => setDescription(e.target.value)} aria-invalid={!description.trim()} />
                </label>
              </div>
            )}
            {s.dimension && (
              <label className="field">
                <span>
                  Dimensión sobre <span className="mono">{s.dimension.column}</span> {s.dimension.exists && '(ya existe)'}
                </span>
                <input className="mono" value={dimName} disabled={s.dimension.exists} onChange={(e) => setDimName(e.target.value)} aria-invalid={!IDENT.test(dimName)} />
              </label>
            )}
          </>
        )}
        <footer className="actions">
          {error && <span className="error">{error}</span>}
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn primary" disabled={!valid || save.isPending} onClick={() => void confirm()}>
            {save.isPending ? 'Validando y guardando…' : 'Guardar y abrir en el constructor'}
          </button>
        </footer>
      </div>
    </div>
  )
}
