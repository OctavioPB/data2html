import { useState } from 'react'

import { useCatalog, useModels } from '../api/queries'
import { useT } from '../i18n'
import { useStudio } from '../store'
import { Builder } from './Builder'
import { toDraft, type ModelDraft } from './draft'
import { ModelEditor } from './ModelEditor'

export function ModelsView() {
  const t = useT()
  const { data, isPending, isError, error } = useModels()
  const catalog = useCatalog()
  const name = useStudio((s) => s.model)
  const preset = useStudio((s) => s.builderPreset)
  const openModels = useStudio((s) => s.openModels)
  const [tab, setTab] = useState<'builder' | 'definition'>('builder')

  if (isPending) return <p className="muted">{t('models.loading')}</p>
  if (isError) return <p className="error">{error.message}</p>

  const entry = data.models.find((m) => m.model.name === name)
  const isNew = name === ''
  const firstSource = catalog.data?.sources.find((s) => s.status === 'ok')?.id ?? 'csv'
  const blank: ModelDraft = { name: '', source: firstSource, table: '', dimensions: [], measures: [], rls: null }
  const active = isNew ? 'definition' : entry && entry.errors.length > 0 ? 'definition' : tab

  return (
    <div className="models-view">
      <aside className="model-list">
        <button className="btn small primary" onClick={() => openModels('')}>
          {t('models.new')}
        </button>
        <ul>
          {data.models.map((m) => (
            <li key={m.model.name}>
              <button aria-pressed={m.model.name === name} onClick={() => openModels(m.model.name)}>
                <span className="mono">{m.model.name}</span>
                <span className="muted small">
                  {m.model.source} · {m.model.table}
                </span>
                {m.errors.length > 0 && (
                  <span className="error small">⚠ {t('models.problems', { n: m.errors.length })}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
        {Object.entries(data.broken).map(([file, err]) => (
          <p key={file} className="error small" title={err}>
            ⚠ {t('models.broken', { file })}
          </p>
        ))}
        {data.models.length === 0 && <p className="muted small">{t('models.none')}</p>}
      </aside>

      <section className="model-main">
        {name === null && (
          <div className="muted">
            <p>{t('models.intro1')}</p>
            <p>{t('models.intro2')}</p>
          </div>
        )}
        {name !== null && !isNew && !entry && <p className="error">{t('models.missing', { name })}</p>}
        {(isNew || entry) && (
          <>
            <header className="table-head">
              <h2>{isNew ? t('models.newTitle') : name}</h2>
              {entry && (
                <span className="muted">
                  {entry.model.source} · {entry.model.table} ·{' '}
                  {t('models.counts', {
                    dims: Object.keys(entry.model.dimensions).length,
                    measures: Object.keys(entry.model.measures).length,
                  })}
                </span>
              )}
              {!isNew && (
                <nav className="tabs" role="tablist">
                  <button role="tab" aria-selected={active === 'builder'} onClick={() => setTab('builder')} disabled={Boolean(entry?.errors.length)}>
                    {t('models.tab.builder')}
                  </button>
                  <button role="tab" aria-selected={active === 'definition'} onClick={() => setTab('definition')}>
                    {t('models.tab.definition')}
                  </button>
                </nav>
              )}
            </header>
            {entry && entry.errors.length > 0 && <p className="error small">{t('models.fixFirst')}</p>}
            {active === 'builder' && entry ? (
              <Builder key={`${entry.model.name}-${JSON.stringify(preset)}`} model={entry.model} preset={preset} />
            ) : (
              <ModelEditor key={name} initial={entry ? toDraft(entry.model) : blank} isNew={isNew} />
            )}
          </>
        )}
      </section>
    </div>
  )
}
