import { ApiStatus } from './components/ApiStatus'
import { CsvUpload } from './components/CsvUpload'
import { Sidebar } from './components/Sidebar'
import { TableDetail } from './components/TableDetail'
import { useStudio } from './store'

export function App() {
  const selected = useStudio((s) => s.selected)
  const uploading = useStudio((s) => s.uploading)
  return (
    <div className="shell">
      <header className="topbar">
        <h1>data2html</h1>
        <ApiStatus />
      </header>
      <Sidebar />
      <main className="workspace">
        {selected ? (
          <TableDetail tableRef={selected} />
        ) : (
          <p className="muted">Elige una tabla o sube un CSV para empezar.</p>
        )}
      </main>
      {uploading && <CsvUpload />}
    </div>
  )
}
