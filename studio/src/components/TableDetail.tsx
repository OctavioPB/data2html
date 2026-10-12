import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useCatalog, usePatchDescriptions } from '../api/queries'
import { Explorer } from '../explore/Explorer'
import { useT } from '../i18n'
import { formatNumber } from '../i18n/format'
import { ProfileView } from '../profile/ProfileView'
import { useStudio, type TableRef } from '../store'

export function TableDetail({ tableRef }: { tableRef: TableRef }) {
  const t = useT()
  const { data } = useCatalog()
  const tab = useStudio((s) => s.tab)
  const setTab = useStudio((s) => s.setTab)
  const table = data?.sources
    .find((s) => s.id === tableRef.source)
    ?.tables.find((x) => x.name === tableRef.table)
  if (!table) return <p className="muted">{t('table.gone')}</p>
  // key: resets the query and drafts when the table changes
  const key = `${tableRef.source}.${table.name}`

  return (
    <div className="table-view">
      <header className="table-head">
        <h2>{table.name}</h2>
        <span className="muted">
          {tableRef.source}
          {table.row_count !== null && ` · ${t('table.rows', { n: formatNumber(table.row_count) })}`} ·{' '}
          {t('table.columns', { n: table.columns.length })}
        </span>
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'data'} onClick={() => setTab('data')}>
            {t('table.tab.data')}
          </button>
          <button role="tab" aria-selected={tab === 'profile'} onClick={() => setTab('profile')}>
            {t('table.tab.profile')}
          </button>
          <button role="tab" aria-selected={tab === 'schema'} onClick={() => setTab('schema')}>
            {t('table.tab.schema')}
          </button>
        </nav>
      </header>
      {tab === 'data' && <Explorer key={key} source={tableRef.source} table={table} />}
      {tab === 'profile' && <ProfileView key={key} source={tableRef.source} table={table} />}
      {tab === 'schema' && <TableForm key={key} tableRef={tableRef} table={table} />}
    </div>
  )
}

function TableForm({ tableRef, table }: { tableRef: TableRef; table: Schemas['TableOut'] }) {
  const t = useT()
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
        <span>{t('schema.description')}</span>
        <textarea
          rows={2}
          maxLength={2000}
          value={description}
          placeholder={t('schema.descriptionPlaceholder')}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>

      <table className="grid">
        <thead>
          <tr>
            <th>{t('schema.column')}</th>
            <th>{t('schema.type')}</th>
            <th>{t('schema.description')}</th>
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
                  aria-label={t('schema.columnDescription', { name: c.name })}
                  onChange={(e) => setColumns({ ...columns, [c.name]: e.target.value })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="actions">
        {patch.isError && <span className="error">{patch.error.message}</span>}
        {patch.isSuccess && !dirty && <span className="muted">{t('common.saved')}</span>}
        <button className="btn primary" disabled={!dirty || patch.isPending}>
          {patch.isPending ? t('common.saving') : t('schema.save')}
        </button>
      </div>
    </form>
  )
}
