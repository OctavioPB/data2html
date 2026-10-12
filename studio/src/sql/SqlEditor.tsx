import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import {
  cancelJob,
  errorMessage,
  newQueryId,
  useCatalog,
  useDeleteSaved,
  useSavedQueries,
  useSaveQuery,
  useSqlHistory,
} from '../api/queries'
import { ExploreGrid } from '../explore/ExploreGrid'
import { usePagedRows, type FetchPage } from '../explore/usePagedRows'
import { useT } from '../i18n'
import { formatNumber } from '../i18n/format'
import { CodeEditor } from './CodeEditor'
import { PromoteDialog } from './PromoteDialog'
import { QuickChart } from './QuickChart'
import { schemaFor } from './schema'

const DRAFT_KEY = 'd2h.sql.draft' // per-browser convenience; the real history lives on the server

function loadDraft(): { source: string; sql: string } {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (raw) return JSON.parse(raw) as { source: string; sql: string }
  } catch {
    /* storage unavailable: start empty */
  }
  return { source: 'csv', sql: '' }
}

interface Run {
  source: string
  sql: string
  queryId: string
  startedAt: number
}

export function SqlEditor() {
  const t = useT()
  const qc = useQueryClient()
  const catalog = useCatalog()
  const [draft, setDraft] = useState(loadDraft)
  const [run, setRun] = useState<Run | null>(null)
  const [finished, setFinished] = useState<{ queryId: string; elapsedMs: number } | null>(null)
  const [view, setView] = useState<'result' | 'chart'>('result')
  const [side, setSide] = useState<'history' | 'saved'>('history')
  const [promoting, setPromoting] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
    } catch {
      /* no storage: the draft does not persist, nothing else breaks */
    }
  }, [draft])

  const sources = catalog.data?.sources ?? []
  const source = sources.find((s) => s.id === draft.source) ?? sources[0]
  const schema = useMemo(() => schemaFor(source?.tables ?? []), [source])

  const fetcher = useMemo<FetchPage | null>(() => {
    if (!run) return null
    return async (offset, limit, withTotal, signal) => {
      const { data, error, response } = await api.POST('/api/sql/run', {
        body: { source: run.source, sql: run.sql, query_id: run.queryId, offset, limit, with_total: withTotal },
        signal,
      })
      if (offset === 0) {
        setFinished({ queryId: run.queryId, elapsedMs: data?.elapsed_ms ?? Date.now() - run.startedAt })
        void qc.invalidateQueries({ queryKey: ['sql-history'] })
      }
      if (!response.ok || !data) throw new Error(errorMessage(error, response.status))
      return data
    }
  }, [run, qc])
  const result = usePagedRows(fetcher)
  const running = run !== null && finished?.queryId !== run.queryId

  const execute = () => {
    if (!source || !draft.sql.trim()) return
    setRun({ source: source.id, sql: draft.sql, queryId: newQueryId(), startedAt: Date.now() })
    setView('result')
  }
  const stop = () => run && void cancelJob(run.queryId)

  return (
    <div className="sql-view">
      <div className="sql-main">
        <div className="sql-toolbar">
          <label>
            {t('sql.source')}{' '}
            <select value={source?.id ?? ''} onChange={(e) => setDraft({ ...draft, source: e.target.value })}>
              {sources.map((s) => (
                <option key={s.id} value={s.id} disabled={s.status !== 'ok'}>
                  {s.id}
                  {s.status !== 'ok' ? ` ${t('sql.sourceOffline')}` : ''}
                </option>
              ))}
            </select>
          </label>
          {running ? (
            <button className="btn primary" onClick={stop}>
              ■ {t('sql.stop')}
            </button>
          ) : (
            <button className="btn primary" onClick={execute} disabled={!draft.sql.trim() || !source}>
              ▶ {t('sql.run')} <span className="kbd">Ctrl+Enter</span>
            </button>
          )}
          <SaveButton source={source?.id ?? ''} sql={draft.sql} />
          <span className="muted small sql-status" role="status">
            {running && <Elapsed since={run.startedAt} />}
            {!running && finished && run && finished.queryId === run.queryId && !result.error && (
              <>
                {t('common.rows', { n: formatNumber(result.total ?? 0) })} ·{' '}
                {(finished.elapsedMs / 1000).toFixed(2)} s
              </>
            )}
          </span>
        </div>

        <div className="sql-editor-box">
          <CodeEditor
            value={draft.sql}
            onChange={(sql) => setDraft((d) => ({ ...d, sql }))}
            onRun={execute}
            schema={schema}
          />
        </div>

        <div className="sql-results">
          <div className="sql-results-head">
            <nav className="tabs" role="tablist">
              <button role="tab" aria-selected={view === 'result'} onClick={() => setView('result')}>
                {t('sql.result')}
              </button>
              <button role="tab" aria-selected={view === 'chart'} onClick={() => setView('chart')}>
                {t('sql.chart')}
              </button>
            </nav>
            {result.firstPage && result.columns.length > 0 && run && (
              <span className="inline">
                {view === 'result' && (
                  <button className="btn small" onClick={() => setView('chart')}>
                    {t('sql.createVisual')}
                  </button>
                )}
                <button className="btn small" onClick={() => setPromoting(true)} title={t('sql.publishHint')}>
                  {t('sql.publish')}
                </button>
              </span>
            )}
          </div>
          {result.error && <p className="error">{result.error}</p>}
          {!run && <p className="muted">{t('sql.empty')}</p>}
          {view === 'result' && result.columns.length > 0 && (
            <div className="grid-wrap">
              <div className="grid-fill">
                <ExploreGrid
                  columns={result.columns}
                  rows={result.total ?? 0}
                  getRow={result.getRow}
                  ensureRange={result.ensureRange}
                />
              </div>
            </div>
          )}
          {view === 'chart' && result.firstPage && (
            <QuickChart
              key={run?.queryId}
              columns={result.columns}
              rows={result.firstPage}
              total={result.total}
            />
          )}
        </div>
      </div>

      <aside className="sql-side">
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={side === 'history'} onClick={() => setSide('history')}>
            {t('sql.history')}
          </button>
          <button role="tab" aria-selected={side === 'saved'} onClick={() => setSide('saved')}>
            {t('sql.saved')}
          </button>
        </nav>
        {side === 'history' ? (
          <HistoryList onPick={(e) => setDraft({ source: e.source, sql: e.sql })} />
        ) : (
          <SavedList onPick={(q) => setDraft({ source: q.source, sql: q.sql })} />
        )}
      </aside>
      {promoting && run && <PromoteDialog source={run.source} sql={run.sql} onClose={() => setPromoting(false)} />}
    </div>
  )
}

function Elapsed({ since }: { since: number }) {
  const t = useT()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(timer)
  }, [])
  return <>{t('sql.running', { s: ((now - since) / 1000).toFixed(1) })}</>
}

function SaveButton({ source, sql }: { source: string; sql: string }) {
  const t = useT()
  const save = useSaveQuery()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  if (!open) {
    return (
      <button className="btn" onClick={() => setOpen(true)} disabled={!sql.trim()}>
        {t('sql.saveAs')}
      </button>
    )
  }
  return (
    <form
      className="inline-form"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate({ name: name.trim(), source, sql }, { onSuccess: () => setOpen(false) })
      }}
    >
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={t('sql.namePlaceholder')}
        maxLength={80}
      />
      <button className="btn small primary" disabled={!name.trim() || save.isPending}>
        {t('common.save')}
      </button>
      <button type="button" className="btn small ghost" onClick={() => setOpen(false)}>
        {t('common.cancel')}
      </button>
      {save.isError && <span className="error small">{save.error.message}</span>}
    </form>
  )
}

function HistoryList({ onPick }: { onPick: (e: { source: string; sql: string }) => void }) {
  const t = useT()
  const { data } = useSqlHistory()
  if (!data?.length) return <p className="muted small">{t('sql.noHistory')}</p>
  return (
    <ul className="query-list">
      {data.map((e, i) => (
        <li key={`${e.at}-${i}`}>
          <button onClick={() => onPick(e)} title={e.error ?? e.sql}>
            <code>{e.sql.slice(0, 140)}</code>
            <span className={e.ok ? 'muted small' : 'error small'}>
              {e.source} ·{' '}
              {e.ok ? t('common.rows', { n: formatNumber(e.rows ?? 0) }) : (e.error ?? t('sql.error')).slice(0, 60)} ·{' '}
              {(e.elapsed_ms / 1000).toFixed(2)} s
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function SavedList({ onPick }: { onPick: (q: { source: string; sql: string }) => void }) {
  const t = useT()
  const { data } = useSavedQueries()
  const del = useDeleteSaved()
  if (!data?.length) return <p className="muted small">{t('sql.noSaved')}</p>
  return (
    <ul className="query-list">
      {data.map((q) => (
        <li key={q.name} className="saved-item">
          <button onClick={() => onPick(q)} title={q.sql}>
            <strong>{q.name}</strong>
            <span className="muted small">{q.source}</span>
          </button>
          <button className="chip-x" aria-label={t('common.delete', { name: q.name })} onClick={() => del.mutate(q.name)}>
            ✕
          </button>
        </li>
      ))}
    </ul>
  )
}
