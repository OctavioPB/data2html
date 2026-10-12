import { lazy, Suspense } from 'react'

import { ApiStatus } from './components/ApiStatus'
import { CsvUpload } from './components/CsvUpload'
import { Sidebar } from './components/Sidebar'
import { TableDetail } from './components/TableDetail'
import { useStudio } from './store'

// CodeMirror + ECharts solo se descargan al abrir el editor SQL o los modelos
const SqlEditor = lazy(() => import('./sql/SqlEditor').then((m) => ({ default: m.SqlEditor })))
const ModelsView = lazy(() => import('./semantic/ModelsView').then((m) => ({ default: m.ModelsView })))

export function App() {
  const selected = useStudio((s) => s.selected)
  const view = useStudio((s) => s.view)
  const uploading = useStudio((s) => s.uploading)
  return (
    <div className="shell">
      <header className="topbar">
        <h1>data2html</h1>
        <ApiStatus />
      </header>
      <Sidebar />
      <main className="workspace">
        {view === 'sql' ? (
          <Suspense fallback={<p className="muted">Cargando editor…</p>}>
            <SqlEditor />
          </Suspense>
        ) : view === 'models' ? (
          <Suspense fallback={<p className="muted">Cargando…</p>}>
            <ModelsView />
          </Suspense>
        ) : selected ? (
          <TableDetail tableRef={selected} />
        ) : (
          <p className="muted">Elige una tabla o sube un CSV para empezar.</p>
        )}
      </main>
      {uploading && <CsvUpload />}
    </div>
  )
}
