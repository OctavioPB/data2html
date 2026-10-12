import { useCatalog } from '../api/queries'
import { useStudio } from '../store'

export function Sidebar() {
  const { data, isPending, isError } = useCatalog()
  const selected = useStudio((s) => s.selected)
  const select = useStudio((s) => s.select)
  const setUploading = useStudio((s) => s.setUploading)
  const view = useStudio((s) => s.view)
  const openSql = useStudio((s) => s.openSql)
  const openModels = useStudio((s) => s.openModels)

  return (
    <aside className="sidebar">
      <nav className="nav-group" aria-label="Herramientas">
        <button className="nav-item" aria-pressed={view === 'sql'} onClick={openSql}>
          <span aria-hidden>⌨</span> Editor SQL
        </button>
        <button className="nav-item" aria-pressed={view === 'models'} onClick={() => openModels()}>
          <span aria-hidden>Σ</span> Modelos y visuales
        </button>
      </nav>
      <div className="sidebar-head">
        <h2>Fuentes</h2>
        <button className="btn small" onClick={() => setUploading(true)}>
          + CSV
        </button>
      </div>
      {isPending && <p className="muted">Cargando…</p>}
      {isError && <p className="muted">No se pudo leer el catálogo.</p>}
      {data?.sources.map((src) => (
        <section key={src.id} className="source">
          <h3>
            {src.id} {src.kind !== src.id && <span className="muted">{src.kind}</span>}
          </h3>
          {src.status === 'error' && (
            <p className="error small" title={src.error ?? undefined}>
              Sin conexión: {src.error}
            </p>
          )}
          {src.status === 'ok' && src.tables.length === 0 && (
            <p className="muted small">{src.kind === 'csv' ? 'Sin tablas. Sube un CSV.' : 'Sin tablas visibles.'}</p>
          )}
          <ul>
            {src.tables.map((t) => {
              const active = view === 'table' && selected?.source === src.id && selected.table === t.name
              return (
                <li key={t.name}>
                  <button
                    className="table-item"
                    aria-pressed={active}
                    title={t.description || undefined}
                    onClick={() => select({ source: src.id, table: t.name })}
                  >
                    {t.name}
                    <span className="muted small">{t.row_count?.toLocaleString('es-MX') ?? ''}</span>
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
