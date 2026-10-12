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
import { CodeEditor } from './CodeEditor'
import { PromoteDialog } from './PromoteDialog'
import { schemaFor } from './schema'
import { QuickChart } from './QuickChart'

const nf = new Intl.NumberFormat('es-MX')
const DRAFT_KEY = 'd2h.sql.draft' // comodidad por navegador; el historial real vive en el servidor

function loadDraft(): { source: string; sql: string } {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (raw) return JSON.parse(raw) as { source: string; sql: string }
  } catch {
    /* almacenamiento no disponible: empezar vacío */
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
      /* sin almacenamiento: el borrador no persiste, no pasa nada */
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
            Fuente{' '}
            <select value={source?.id ?? ''} onChange={(e) => setDraft({ ...draft, source: e.target.value })}>
              {sources.map((s) => (
                <option key={s.id} value={s.id} disabled={s.status !== 'ok'}>
                  {s.id}
                  {s.status !== 'ok' ? ' (sin conexión)' : ''}
                </option>
              ))}
            </select>
          </label>
          {running ? (
            <button className="btn primary" onClick={stop}>
              ■ Detener
            </button>
          ) : (
            <button className="btn primary" onClick={execute} disabled={!draft.sql.trim() || !source}>
              ▶ Ejecutar <span className="kbd">Ctrl+Enter</span>
            </button>
          )}
          <SaveButton source={source?.id ?? ''} sql={draft.sql} />
          <span className="muted small sql-status" role="status">
            {running && <Elapsed since={run.startedAt} />}
            {!running && finished && run && finished.queryId === run.queryId && !result.error && (
              <>
                {nf.format(result.total ?? 0)} filas · {(finished.elapsedMs / 1000).toFixed(2)} s
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
                Resultado
              </button>
              <button role="tab" aria-selected={view === 'chart'} onClick={() => setView('chart')}>
                Gráfico
              </button>
            </nav>
            {result.firstPage && result.columns.length > 0 && run && (
              <span className="inline">
                {view === 'result' && (
                  <button className="btn small" onClick={() => setView('chart')}>
                    Crear visual
                  </button>
                )}
                <button className="btn small" onClick={() => setPromoting(true)} title="Definir la medida en el modelo semántico">
                  Publicar como medida…
                </button>
              </span>
            )}
          </div>
          {result.error && <p className="error">{result.error}</p>}
          {!run && <p className="muted">Escribe una consulta y ejecútala con Ctrl+Enter.</p>}
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
            Historial
          </button>
          <button role="tab" aria-selected={side === 'saved'} onClick={() => setSide('saved')}>
            Guardadas
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
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(t)
  }, [])
  return <>Ejecutando… {((now - since) / 1000).toFixed(1)} s</>
}

function SaveButton({ source, sql }: { source: string; sql: string }) {
  const save = useSaveQuery()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  if (!open) {
    return (
      <button className="btn" onClick={() => setOpen(true)} disabled={!sql.trim()}>
        Guardar…
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
      <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre" maxLength={80} />
      <button className="btn small primary" disabled={!name.trim() || save.isPending}>
        Guardar
      </button>
      <button type="button" className="btn small ghost" onClick={() => setOpen(false)}>
        Cancelar
      </button>
      {save.isError && <span className="error small">{save.error.message}</span>}
    </form>
  )
}

function HistoryList({ onPick }: { onPick: (e: { source: string; sql: string }) => void }) {
  const { data } = useSqlHistory()
  if (!data?.length) return <p className="muted small">Aún no hay consultas.</p>
  return (
    <ul className="query-list">
      {data.map((e, i) => (
        <li key={`${e.at}-${i}`}>
          <button onClick={() => onPick(e)} title={e.error ?? e.sql}>
            <code>{e.sql.slice(0, 140)}</code>
            <span className={e.ok ? 'muted small' : 'error small'}>
              {e.source} · {e.ok ? `${nf.format(e.rows ?? 0)} filas` : (e.error ?? 'error').slice(0, 60)} ·{' '}
              {(e.elapsed_ms / 1000).toFixed(2)} s
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function SavedList({ onPick }: { onPick: (q: { source: string; sql: string }) => void }) {
  const { data } = useSavedQueries()
  const del = useDeleteSaved()
  if (!data?.length) return <p className="muted small">Sin consultas guardadas.</p>
  return (
    <ul className="query-list">
      {data.map((q) => (
        <li key={q.name} className="saved-item">
          <button onClick={() => onPick(q)} title={q.sql}>
            <strong>{q.name}</strong>
            <span className="muted small">{q.source}</span>
          </button>
          <button className="chip-x" aria-label={`Borrar ${q.name}`} onClick={() => del.mutate(q.name)}>
            ✕
          </button>
        </li>
      ))}
    </ul>
  )
}
