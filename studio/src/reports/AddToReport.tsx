/**
 * "Add to report…" from the visual builder: append the visual to an existing report of the same model, or
 * start a new one. Saving publishes (the viewer serves it), so the backend validates before writing.
 */
import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useReports, useSaveReport } from '../api/queries'
import { useT } from '../i18n'
import { slug } from '../semantic/draft'
import { useStudio } from '../store'
import { addVisual, ID_PATTERN, newReport } from './draft'

interface Props {
  model: string
  visual: Schemas['VisualDraft']
  title: string
  onClose: () => void
}

export function AddToReport({ model, visual, title, onClose }: Props) {
  const t = useT()
  const reports = useReports()
  const save = useSaveReport()
  const openReports = useStudio((s) => s.openReports)
  const candidates = (reports.data?.reports ?? []).filter((e) => e.report.semantic_model === model)
  const [target, setTarget] = useState<string>('') // '' = new report
  const [visualTitle, setVisualTitle] = useState(title)
  const [newTitle, setNewTitle] = useState('')
  const newId = slug(newTitle, 'report')
  const exists = (reports.data?.reports ?? []).some((e) => e.report.id === newId)
  const chosen = candidates.find((e) => e.report.id === target)?.report
  const valid = visualTitle.trim() !== '' && (chosen ? true : newTitle.trim() !== '' && ID_PATTERN.test(newId) && !exists)

  const submit = () => {
    const base = chosen ?? newReport(newId, newTitle.trim(), model)
    save.mutate(addVisual(base, visual, visualTitle.trim()), {
      onSuccess: (entry) => {
        onClose()
        openReports(entry.report.id)
      },
    })
  }

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog narrow" role="dialog" aria-modal aria-labelledby="add-report-title">
        <header>
          <h2 id="add-report-title">{t('addToReport.title')}</h2>
          <button className="btn ghost" onClick={onClose} aria-label={t('common.close')}>
            ✕
          </button>
        </header>
        <form
          className="form-stack"
          onSubmit={(e) => {
            e.preventDefault()
            if (valid) submit()
          }}
        >
          <label className="field">
            <span>{t('addToReport.visualTitle')}</span>
            <input value={visualTitle} onChange={(e) => setVisualTitle(e.target.value)} autoFocus />
          </label>
          <label className="field">
            <span>{t('addToReport.report')}</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">{t('addToReport.newReport')}</option>
              {candidates.map((e) => (
                <option key={e.report.id} value={e.report.id}>
                  {e.report.title} ({e.report.id})
                </option>
              ))}
            </select>
          </label>
          {!chosen && (
            <label className="field">
              <span>{t('reports.titleLabel')}</span>
              <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
              {newTitle && (
                <span className={exists ? 'error small' : 'muted small'}>
                  {exists ? t('reports.idTaken', { id: newId }) : t('reports.idWillBe', { id: newId })}
                </span>
              )}
            </label>
          )}
          <p className="muted small">{t('addToReport.publishNote')}</p>
          <div className="actions">
            {save.isError && <p className="error small">{save.error.message}</p>}
            <button type="button" className="btn" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn primary" disabled={!valid || save.isPending}>
              {save.isPending ? t('common.saving') : t('addToReport.confirm')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
