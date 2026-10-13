import { useCatalog, useRefreshSource } from '../api/queries'
import { useT } from '../i18n'
import { formatNumber } from '../i18n/format'
import { useStudio } from '../store'
import { IngestPanel } from './IngestPanel'

export function Sidebar() {
  const t = useT()
  const { data, isPending, isError } = useCatalog()
  const refresh = useRefreshSource()
  const selected = useStudio((s) => s.selected)
  const select = useStudio((s) => s.select)
  const setUploading = useStudio((s) => s.setUploading)
  const view = useStudio((s) => s.view)
  const openSql = useStudio((s) => s.openSql)
  const openModels = useStudio((s) => s.openModels)
  const openReports = useStudio((s) => s.openReports)

  return (
    <aside className="sidebar">
      <nav className="nav-group" aria-label={t('nav.tools')}>
        <button className="nav-item" aria-pressed={view === 'sql'} onClick={openSql}>
          <span aria-hidden>⌨</span> {t('nav.sqlEditor')}
        </button>
        <button className="nav-item" aria-pressed={view === 'models'} onClick={() => openModels()}>
          <span aria-hidden>Σ</span> {t('nav.models')}
        </button>
        <button className="nav-item" aria-pressed={view === 'reports'} onClick={() => openReports()}>
          <span aria-hidden>▦</span> {t('nav.reports')}
        </button>
      </nav>
      <div className="sidebar-head">
        <h2>{t('sidebar.sources')}</h2>
        <button className="btn small" onClick={() => setUploading(true)}>
          {t('sidebar.addCsv')}
        </button>
      </div>
      {isPending && <p className="muted">{t('common.loading')}</p>}
      {isError && <p className="muted">{t('sidebar.catalogError')}</p>}
      {data?.sources.map((src) => (
        <section key={src.id} className="source">
          <h3 className="source-head">
            <span>
              {src.id} {src.kind !== src.id && <span className="muted">{src.kind}</span>}
            </span>
            {(src.kind === 'postgres' || src.kind === 'mysql') && (
              <button
                type="button"
                className="icon-only"
                title={t('sidebar.refresh')}
                aria-label={t('sidebar.refreshSource', { source: src.id })}
                disabled={refresh.isPending && refresh.variables === src.id}
                onClick={() => refresh.mutate(src.id)}
              >
                ↻
              </button>
            )}
          </h3>
          {src.status === 'error' && (
            <p className="error small" title={src.error ?? undefined}>
              {t('sidebar.offline', { error: src.error ?? '' })}
            </p>
          )}
          {src.status === 'ok' && src.tables.length === 0 && src.kind !== 'dynamodb' && (
            <p className="muted small">{src.kind === 'csv' ? t('sidebar.noCsvTables') : t('sidebar.noTables')}</p>
          )}
          {src.kind === 'dynamodb' && <IngestPanel source={src.id} />}
          <ul>
            {src.tables.map((tbl) => {
              const active = view === 'table' && selected?.source === src.id && selected.table === tbl.name
              return (
                <li key={tbl.name}>
                  <button
                    className="table-item"
                    aria-pressed={active}
                    title={tbl.description || undefined}
                    onClick={() => select({ source: src.id, table: tbl.name })}
                  >
                    {tbl.name}
                    <span className="muted small">{tbl.row_count !== null ? formatNumber(tbl.row_count) : ''}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </aside>
  )
}
