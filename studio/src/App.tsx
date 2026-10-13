import { lazy, Suspense } from 'react'

import { ApiStatus } from './components/ApiStatus'
import { AuthGate, UserMenu } from './components/AuthGate'
import { CsvUpload } from './components/CsvUpload'
import { LanguageSwitch } from './components/LanguageSwitch'
import { Sidebar } from './components/Sidebar'
import { TableDetail } from './components/TableDetail'
import { useT } from './i18n'
import { useStudio } from './store'

// CodeMirror + ECharts (and react-grid-layout) are only downloaded when a view that uses them is opened
const SqlEditor = lazy(() => import('./sql/SqlEditor').then((m) => ({ default: m.SqlEditor })))
const ModelsView = lazy(() => import('./semantic/ModelsView').then((m) => ({ default: m.ModelsView })))
const ReportsView = lazy(() => import('./reports/ReportsView').then((m) => ({ default: m.ReportsView })))

export function App() {
  const t = useT()
  const selected = useStudio((s) => s.selected)
  const view = useStudio((s) => s.view)
  const uploading = useStudio((s) => s.uploading)
  return (
    <div className="shell">
      <header className="topbar">
        <h1>data2html</h1>
        <div className="topbar-right">
          <ApiStatus />
          <UserMenu />
          <LanguageSwitch />
        </div>
      </header>
      <AuthGate>
      <Sidebar />
      <main className="workspace">
        {view === 'sql' ? (
          <Suspense fallback={<p className="muted">{t('app.loadingEditor')}</p>}>
            <SqlEditor />
          </Suspense>
        ) : view === 'models' ? (
          <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
            <ModelsView />
          </Suspense>
        ) : view === 'reports' ? (
          <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
            <ReportsView />
          </Suspense>
        ) : selected ? (
          <TableDetail tableRef={selected} />
        ) : (
          <p className="muted">{t('app.empty')}</p>
        )}
      </main>
      {uploading && <CsvUpload />}
      </AuthGate>
    </div>
  )
}
