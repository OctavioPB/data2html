import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useCatalog, usePatchDescriptions } from '../api/queries'
import { Explorer } from '../explore/Explorer'
import { useStudio, type TableRef } from '../store'

export function TableDetail({ tableRef }: { tableRef: TableRef }) {
  const { data } = useCatalog()
  const tab = useStudio((s) => s.tab)
  const setTab = useStudio((s) => s.setTab)
  const table = data?.sources
    .find((s) => s.id === tableRef.source)
    ?.tables.find((t) => t.name === tableRef.table)
  if (!table) return <p className="muted">La tabla ya no existe.</p>
  // key: reinicia consulta y borradores al cambiar de tabla
  const key = `${tableRef.source}.${table.name}`

  return (
    <div className="table-view">
      <header className="table-head">
        <h2>{table.name}</h2>
        <span className="muted">
          {tableRef.source} · {table.row_count?.toLocaleString('es-MX') ?? '?'} filas ·{' '}
          {table.columns.length} columnas
        </span>
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'data'} onClick={() => setTab('data')}>
            Datos
          </button>
          <button role="tab" aria-selected={tab === 'schema'} onClick={() => setTab('schema')}>
            Esquema
          </button>
        </nav>
      </header>
      {tab === 'data' ? (
        <Explorer key={key} source={tableRef.source} table={table} />
      ) : (
        <TableForm key={key} tableRef={tableRef} table={table} />
      )}
    </div>
  )
}

function TableForm({ tableRef, table }: { tableRef: TableRef; table: Schemas['TableOut'] }) {
  const patch = usePatchDescriptions(tableRef.source, tableRef.table)
  const [description, setDescription] = useState(table.description)
  const [columns, setColumns] = useState(() =>
    Object.fromEntries(table.columns.map((c) => [c.name, c.description])),
  )
  const dirty =
    description !== table.description || table.columns.some((c) => columns[c.name] !== c.description)

  return (
    <form
      className="table-detail"
      onSubmit={(e) => {
        e.preventDefault()
        patch.mutate({ description, columns })
      }}
    >
      <label className="field">
        <span>Descripción</span>
        <textarea
          rows={2}
          maxLength={2000}
          value={description}
          placeholder="¿Qué contiene esta tabla? ¿De dónde sale?"
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>

      <table className="grid">
        <thead>
          <tr>
            <th>Columna</th>
            <th>Tipo</th>
            <th>Descripción</th>
          </tr>
        </thead>
        <tbody>
          {table.columns.map((c) => (
            <tr key={c.name}>
              <td className="mono">{c.name}</td>
              <td className="mono muted">{c.type}</td>
              <td>
                <input
                  maxLength={2000}
                  value={columns[c.name] ?? ''}
                  aria-label={`Descripción de ${c.name}`}
                  onChange={(e) => setColumns({ ...columns, [c.name]: e.target.value })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="actions">
        {patch.isError && <span className="error">{patch.error.message}</span>}
        {patch.isSuccess && !dirty && <span className="muted">Guardado</span>}
        <button className="btn primary" disabled={!dirty || patch.isPending}>
          {patch.isPending ? 'Guardando…' : 'Guardar descripciones'}
        </button>
      </div>
    </form>
  )
}
