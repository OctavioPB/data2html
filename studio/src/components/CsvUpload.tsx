import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useCsvConfirm, useCsvDiscard, useCsvPreview } from '../api/queries'
import { useStudio } from '../store'

type Choice = Schemas['ColumnChoice']
type CsvType = Choice['type']
type DateFormat = NonNullable<Choice['date_format']>

const TYPES: CsvType[] = ['VARCHAR', 'BIGINT', 'DOUBLE', 'BOOLEAN', 'DATE', 'TIMESTAMP']
const DATE_FORMATS: { value: DateFormat; label: string }[] = [
  { value: '%Y-%m-%d', label: 'AAAA-MM-DD' },
  { value: '%d/%m/%Y', label: 'DD/MM/AAAA' },
  { value: '%m/%d/%Y', label: 'MM/DD/AAAA' },
  { value: '%d-%m-%Y', label: 'DD-MM-AAAA' },
  { value: '%m-%d-%Y', label: 'MM-DD-AAAA' },
]
const TABLE_RE = /^[a-z_][a-z0-9_]{0,62}$/

/** Ajusta las opciones al cambiar de tipo: el backend rechaza combinaciones sin sentido. */
function withType(c: Choice, type: CsvType): Choice {
  const isDate = type === 'DATE' || type === 'TIMESTAMP'
  return {
    ...c,
    type,
    date_format: isDate ? (c.date_format ?? null) : null,
    decimal_comma: type === 'DOUBLE' ? c.decimal_comma : false,
  }
}

export function CsvUpload() {
  const setUploading = useStudio((s) => s.setUploading)
  const select = useStudio((s) => s.select)
  const preview = useCsvPreview()
  const confirm = useCsvConfirm()
  const discard = useCsvDiscard()
  const [table, setTable] = useState('')
  const [columns, setColumns] = useState<Choice[]>([])

  const data = preview.data
  const close = () => {
    if (data && !confirm.isSuccess) discard.mutate(data.upload_id)
    setUploading(false)
  }

  const onFile = (file: File | undefined) => {
    if (!file) return
    if (data) discard.mutate(data.upload_id)
    preview.mutate(file, {
      onSuccess: (p) => {
        setTable(p.suggested_table)
        setColumns(p.columns.map(({ name, type, date_format, decimal_comma }) => ({
          name, type, date_format, decimal_comma,
        })))
      },
    })
  }

  const onConfirm = () => {
    if (!data) return
    confirm.mutate(
      { upload_id: data.upload_id, table, columns },
      {
        onSuccess: (t) => {
          select({ source: 'csv', table: t.name })
          setUploading(false)
        },
      },
    )
  }

  const update = (i: number, c: Choice) => setColumns(columns.map((old, j) => (j === i ? c : old)))
  const validName = TABLE_RE.test(table)

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && close()}>
      <div className="dialog" role="dialog" aria-modal aria-labelledby="csv-title">
        <header>
          <h2 id="csv-title">Subir CSV</h2>
          <button className="btn ghost" onClick={close} aria-label="Cerrar">
            ✕
          </button>
        </header>

        <input type="file" accept=".csv,.txt,text/csv" onChange={(e) => onFile(e.target.files?.[0])} />
        {preview.isPending && <p className="muted">Analizando…</p>}
        {preview.isError && <p className="error">{preview.error.message}</p>}

        {data && (
          <>
            <p className="muted small">
              {data.filename} · codificación {data.encoding} · separador «{data.delimiter}»
            </p>
            {data.warnings.length > 0 && (
              <ul className="warnings">
                {data.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            )}

            <label className="field">
              <span>Nombre de la tabla</span>
              <input value={table} onChange={(e) => setTable(e.target.value)} aria-invalid={!validName} />
              {!validName && (
                <span className="error small">Minúsculas, dígitos y _; empieza con letra o _.</span>
              )}
            </label>

            <div className="scroll">
              <table className="grid">
                <thead>
                  <tr>
                    <th>Columna</th>
                    <th>Tipo</th>
                    <th>Opciones</th>
                    <th>Avisos</th>
                  </tr>
                </thead>
                <tbody>
                  {columns.map((c, i) => (
                    <tr key={c.name}>
                      <td className="mono">{c.name}</td>
                      <td>
                        <select
                          value={c.type}
                          aria-label={`Tipo de ${c.name}`}
                          onChange={(e) => update(i, withType(c, e.target.value as CsvType))}
                        >
                          {TYPES.map((t) => <option key={t}>{t}</option>)}
                        </select>
                      </td>
                      <td>
                        {(c.type === 'DATE' || c.type === 'TIMESTAMP') && (
                          <select
                            value={c.date_format ?? ''}
                            aria-label={`Formato de fecha de ${c.name}`}
                            onChange={(e) =>
                              update(i, { ...c, date_format: (e.target.value || null) as DateFormat | null })
                            }
                          >
                            <option value="">automático (ISO)</option>
                            {DATE_FORMATS.map((f) => (
                              <option key={f.value} value={f.value}>{f.label}</option>
                            ))}
                          </select>
                        )}
                        {c.type === 'DOUBLE' && (
                          <label className="inline">
                            <input
                              type="checkbox"
                              checked={c.decimal_comma ?? false}
                              onChange={(e) => update(i, { ...c, decimal_comma: e.target.checked })}
                            />
                            coma decimal
                          </label>
                        )}
                      </td>
                      <td className="small">{data.columns[i]?.warnings?.join(' · ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 className="small muted">Muestra ({Math.min(data.rows.length, 5)} filas, tal como vienen)</h3>
            <div className="scroll">
              <table className="grid sample">
                <thead>
                  <tr>{columns.map((c) => <th key={c.name}>{c.name}</th>)}</tr>
                </thead>
                <tbody>
                  {data.rows.slice(0, 5).map((r, i) => (
                    <tr key={i}>{r.map((v, j) => <td key={j}>{v ?? <span className="muted">∅</span>}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <footer className="actions">
          {confirm.isError && <span className="error">{confirm.error.message}</span>}
          <button className="btn" onClick={close}>Cancelar</button>
          <button
            className="btn primary"
            disabled={!data || !validName || confirm.isPending}
            onClick={onConfirm}
          >
            {confirm.isPending ? 'Convirtiendo…' : 'Crear tabla'}
          </button>
        </footer>
      </div>
    </div>
  )
}
