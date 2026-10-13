import { useModels, useReports } from '../api/queries'
import { useT } from '../i18n'
import { useStudio } from '../store'
import { ReportEditor } from './ReportEditor'

export function ReportsView() {
  const t = useT()
  const { data, isPending, isError, error } = useReports()
  const models = useModels()
  const id = useStudio((s) => s.report)
  const openReports = useStudio((s) => s.openReports)

  if (isPending || models.isPending) return <p className="muted">{t('reports.loading')}</p>
  if (isError) return <p className="error">{error.message}</p>

  const entry = data.reports.find((e) => e.report.id === id)
  const isNew = id === ''

  return (
    <div className="models-view">
      <aside className="model-list">
        <button className="btn small primary" onClick={() => openReports('')}>
          {t('reports.new')}
        </button>
        <ul>
          {data.reports.map((e) => (
            <li key={e.report.id}>
              <button aria-pressed={e.report.id === id} onClick={() => openReports(e.report.id)}>
                <span>{e.report.title}</span>
                <span className="muted small">
                  <span className="mono">{e.report.id}</span> · {e.report.semantic_model} ·{' '}
                  {t('reports.visuals', { n: e.report.visuals.length })}
                </span>
                {e.errors.length > 0 && <span className="error small">⚠ {t('reports.problems', { n: e.errors.length })}</span>}
              </button>
            </li>
          ))}
        </ul>
        {Object.entries(data.broken).map(([file, err]) => (
          <p key={file} className="error small" title={err}>
            ⚠ {t('reports.broken', { file })}
          </p>
        ))}
        {data.reports.length === 0 && <p className="muted small">{t('reports.none')}</p>}
      </aside>

      <section className="model-main">
        {id === null && (
          <div className="muted">
            <p>{t('reports.intro1')}</p>
            <p>{t('reports.intro2')}</p>
          </div>
        )}
        {id !== null && !isNew && !entry && <p className="error">{t('reports.missing', { id })}</p>}
        {(isNew || entry) && (
          <ReportEditor
            key={id}
            entry={entry ?? null}
            models={models.data?.models.map((m) => m.model) ?? []}
            takenIds={data.reports.map((e) => e.report.id)}
          />
        )}
      </section>
    </div>
  )
}
