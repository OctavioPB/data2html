/**
 * Dashboard editor: report settings (title, parameters, access) and a 12-column grid of visuals
 * (react-grid-layout) that writes `Visual.layout`. Saving validates on the server and publishes.
 * Tiles preview as the author (every row); in the viewer each reader only sees their own rows.
 */
import type { EChartsType } from 'echarts/core'
import { useMemo, useState, type RefObject } from 'react'
import ReactGridLayout, { useContainerWidth, type Layout } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import type { Schemas } from '../api/client'
import { useDeleteReport, useSaveReport, useVisualQuery } from '../api/queries'
import { useT, type MessageKey } from '../i18n'
import { MARK_LABEL } from '../render/labels'
import { VisualChart } from '../render/VisualChart'
import { VisualDownloads } from '../render/VisualDownloads'
import { slug } from '../semantic/draft'
import { useStudio } from '../store'
import { ID_PATTERN, newReport, paramOf, PARAM_TYPES, previewParams, renameParam, toVisualDraft, type ParamType, type Report, type Visual } from './draft'

type Model = Schemas['SemanticModel']

const ROW = 64
const MARGIN = 12
const HEAD = 64 // tile header, body padding and borders, in px

const PARAM_LABEL: Record<ParamType, MessageKey> = {
  date: 'paramType.date',
  int: 'paramType.int',
  float: 'paramType.float',
  str: 'paramType.str',
  bool: 'paramType.bool',
}

interface Props {
  entry: Schemas['ReportEntry'] | null
  models: Model[]
  takenIds: string[]
}

export function ReportEditor({ entry, models, takenIds }: Props) {
  const t = useT()
  const isNew = entry === null
  const [saved, setSaved] = useState<Report | null>(entry?.report ?? null)
  const [draft, setDraft] = useState<Report>(() => entry?.report ?? newReport('', '', models[0]?.name ?? ''))
  const save = useSaveReport()
  const del = useDeleteReport()
  const openReports = useStudio((s) => s.openReports)
  const openModels = useStudio((s) => s.openModels)
  const model = models.find((m) => m.name === draft.semantic_model)
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)
  const idTaken = isNew && takenIds.includes(draft.id)
  const canSave = dirty && draft.title.trim() !== '' && ID_PATTERN.test(draft.id) && !idTaken && Boolean(model)

  const update = (patch: Partial<Report>) => setDraft((d) => ({ ...d, ...patch }))
  const setVisual = (id: string, patch: Partial<Visual>) =>
    setDraft((d) => ({ ...d, visuals: d.visuals.map((v) => (v.id === id ? { ...v, ...patch } : v)) }))

  const submit = () =>
    save.mutate(draft, {
      onSuccess: (e) => {
        setSaved(e.report)
        if (isNew) openReports(e.report.id)
      },
    })

  return (
    <div className="report-editor">
      <header className="report-head">
        <label className="field grow">
          <span>{t('reports.titleLabel')}</span>
          <input
            value={draft.title}
            onChange={(e) => update(isNew ? { title: e.target.value, id: slug(e.target.value, 'report') } : { title: e.target.value })}
          />
        </label>
        {isNew ? (
          <>
            <label className="field">
              <span>{t('reports.idLabel')}</span>
              <input className="mono" value={draft.id} onChange={(e) => update({ id: e.target.value })} aria-invalid={idTaken || !ID_PATTERN.test(draft.id)} />
            </label>
            <label className="field">
              <span>{t('reports.model')}</span>
              <select value={draft.semantic_model} onChange={(e) => update({ semantic_model: e.target.value })}>
                {models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : (
          <span className="muted small">
            <span className="mono">/r/{draft.id}</span> · {draft.semantic_model}
          </span>
        )}
        <div className="report-actions">
          <span className="muted small" aria-live="polite">
            {dirty ? t('reports.unsaved') : t('reports.saved')}
          </span>
          {!isNew && (
            <a className="btn small" href={`/r/${draft.id}`} target="_blank" rel="noreferrer" aria-disabled={dirty}>
              {t('reports.openViewer')} ↗
            </a>
          )}
          <button className="btn small primary" disabled={!canSave || save.isPending} onClick={submit}>
            {save.isPending ? t('common.saving') : isNew ? t('reports.create') : t('reports.save')}
          </button>
          {!isNew && (
            <button
              className="btn small"
              onClick={() => {
                if (window.confirm(t('reports.confirmDelete', { id: draft.id }))) {
                  del.mutate(draft.id, { onSuccess: () => openReports(null) })
                }
              }}
            >
              {t('reports.delete')}
            </button>
          )}
        </div>
      </header>
      {idTaken && <p className="error small">{t('reports.idTaken', { id: draft.id })}</p>}
      {save.isError && <p className="error">{save.error.message}</p>}
      {entry && entry.errors.length > 0 && !dirty && (
        <ul className="error small">
          {entry.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}

      <section className="report-settings">
        <label className="field">
          <span>{t('reports.access')}</span>
          <input
            value={(draft.access ?? []).join(', ')}
            onChange={(e) => update({ access: e.target.value.split(',').map((g) => g.trim()).filter(Boolean) })}
            placeholder="—"
          />
          <span className="muted small">{t('reports.accessHint')}</span>
        </label>
        <div className="field">
          <span>{t('reports.mode')}</span>
          <select
            value={draft.mode ?? 'live'}
            onChange={(e) => {
              const mode = e.target.value as Report['mode']
              update(mode === 'live' ? { mode, refresh_hours: null } : { mode })
            }}
          >
            <option value="live">{t('reports.modeLive')}</option>
            <option value="snapshot">{t('reports.modeSnapshot')}</option>
          </select>
          {draft.mode === 'snapshot' && (
            <label className="inline-field">
              {t('reports.refreshHours')}
              <input
                type="number"
                min={1}
                max={2160}
                value={draft.refresh_hours ?? ''}
                placeholder="—"
                onChange={(e) => update({ refresh_hours: e.target.value === '' ? null : Number(e.target.value) })}
              />
            </label>
          )}
          <span className="muted small">{draft.mode === 'snapshot' ? t('reports.modeSnapshotHint') : t('reports.modeLiveHint')}</span>
        </div>
        <ParamsEditor
          report={draft}
          onChange={(params, rename) =>
            update(rename ? { params, visuals: renameParam(draft.visuals, rename[0], rename[1]) } : { params })
          }
        />
      </section>

      {model && draft.visuals.length === 0 && (
        <div className="muted">
          <p>{t('reports.empty')}</p>
          <button className="btn small" onClick={() => openModels(model.name)}>
            {t('reports.openBuilder')}
          </button>
        </div>
      )}
      {model && draft.visuals.length > 0 && (
        <>
          <p className="muted small">
            {t('reports.dragHint')} {t('reports.previewNote')}
          </p>
          <Grid report={draft} model={model} onLayout={(layout) => update({ visuals: applyLayout(draft.visuals, layout) })} setVisual={setVisual}
            onRemove={(id) => update({ visuals: draft.visuals.filter((v) => v.id !== id) })} />
        </>
      )}
    </div>
  )
}

/** Grid positions → `Visual.layout`, keeping the same object when nothing moved. */
function applyLayout(visuals: Visual[], layout: Layout): Visual[] {
  const pos = new Map(layout.map((l) => [l.i, l]))
  let changed = false
  const next = visuals.map((v) => {
    const l = pos.get(v.id)
    if (!l || (l.x === v.layout.x && l.y === v.layout.y && l.w === v.layout.w && l.h === v.layout.h)) return v
    changed = true
    return { ...v, layout: { x: l.x, y: l.y, w: l.w, h: l.h } }
  })
  return changed ? next : visuals
}

function Grid({ report, model, onLayout, setVisual, onRemove }: {
  report: Report
  model: Model
  onLayout: (l: Layout) => void
  setVisual: (id: string, patch: Partial<Visual>) => void
  onRemove: (id: string) => void
}) {
  const { width, containerRef, mounted } = useContainerWidth()
  const layout = useMemo(() => report.visuals.map((v) => ({ i: v.id, ...v.layout, minW: 2, minH: 2 })), [report.visuals])
  const preview = useMemo(() => previewParams(report), [report])
  return (
    <div ref={containerRef as RefObject<HTMLDivElement>} className="report-grid">
      {mounted && (
        <ReactGridLayout
          layout={layout}
          width={width}
          gridConfig={{ cols: 12, rowHeight: ROW, margin: [MARGIN, MARGIN] }}
          dragConfig={{ handle: '.tile-handle' }}
          onLayoutChange={onLayout}
        >
          {report.visuals.map((v) => (
            <div key={v.id} className="tile">
              <Tile visual={v} model={model} preview={preview} setVisual={setVisual} onRemove={onRemove} />
            </div>
          ))}
        </ReactGridLayout>
      )}
    </div>
  )
}

function Tile({ visual, model, preview, setVisual, onRemove }: {
  visual: Visual
  model: Model
  preview: ReturnType<typeof previewParams>
  setVisual: (id: string, patch: Partial<Visual>) => void
  onRemove: (id: string) => void
}) {
  const t = useT()
  // the preview does not depend on the mark: switching it redraws the same rows
  const request = useMemo(
    () => ({ model: model.name, visual: { ...toVisualDraft(visual), mark: 'table' as const }, ...preview }),
    // oxlint-disable-next-line react-hooks/exhaustive-deps
    [model.name, visual.measure, visual.dimension, visual.time_grain, visual.color, JSON.stringify(visual.filters), preview],
  )
  const result = useVisualQuery(request)
  const [chart, setChart] = useState<EChartsType | null>(null)
  const allowed = result.data?.allowed_marks ?? [visual.mark]
  const height = visual.layout.h * ROW + (visual.layout.h - 1) * MARGIN - HEAD
  return (
    <>
      <div className="tile-head">
        <span className="tile-handle" title={t('reports.moveVisual', { title: visual.title })} aria-hidden>
          ⠿
        </span>
        <input
          className="tile-title"
          value={visual.title}
          aria-label={t('reports.visualTitle', { id: visual.id })}
          onChange={(e) => setVisual(visual.id, { title: e.target.value })}
        />
        <select value={visual.mark} aria-label={t('quick.chartType')} onChange={(e) => setVisual(visual.id, { mark: e.target.value as Visual['mark'] })}>
          {allowed.map((m) => (
            <option key={m} value={m}>
              {t(MARK_LABEL[m])}
            </option>
          ))}
        </select>
        <VisualDownloads request={request} chart={chart} name={visual.id} />
        <button className="chip-x" aria-label={t('reports.removeVisual', { title: visual.title })} onClick={() => onRemove(visual.id)}>
          ✕
        </button>
      </div>
      <div className="tile-body">
        {result.isError && <p className="error small">{result.error.message}</p>}
        {result.isPending && <p className="muted small">{t('common.loading')}</p>}
        {result.data && (
          <VisualChart
            mark={visual.mark}
            columns={result.data.columns}
            rows={result.data.rows}
            dimension={visual.dimension ?? null}
            color={visual.color ?? null}
            measures={[visual.measure]}
            format={model.measures[visual.measure]?.format}
            height={Math.max(80, height)}
            timeGrain={visual.time_grain ?? null}
            onChart={setChart}
          />
        )}
      </div>
    </>
  )
}

function ParamsEditor({ report, onChange }: {
  report: Report
  onChange: (p: Report['params'], rename?: [from: string, to: string]) => void
}) {
  const t = useT()
  const entries = Object.entries(report.params ?? {}).map(([name, p]) => [name, paramOf(p)] as const)
  const write = (rows: (readonly [string, Schemas['Param']])[], rename?: [string, string]) =>
    onChange(Object.fromEntries(rows), rename)
  return (
    <fieldset className="params-editor">
      <legend>{t('reports.params')}</legend>
      {entries.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th>{t('reports.paramName')}</th>
              <th>{t('reports.paramType')}</th>
              <th>{t('reports.paramDefault')}</th>
              <th>{t('reports.paramLabel')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, p], i) => {
              const set = (patch: Partial<Schemas['Param']>, newName = name) =>
                write(
                  entries.map((e, j) => (j === i ? ([newName, { ...p, ...patch }] as const) : e)),
                  newName !== name ? [name, newName] : undefined,
                )
              return (
                <tr key={i}>
                  <td>
                    <input className="mono" value={name} aria-label={t('reports.paramName')} onChange={(e) => set({}, e.target.value)} />
                  </td>
                  <td>
                    <select value={p.type} aria-label={t('reports.paramType')} onChange={(e) => set({ type: e.target.value as ParamType, default: null })}>
                      {PARAM_TYPES.map((pt) => (
                        <option key={pt} value={pt}>
                          {t(PARAM_LABEL[pt])}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type={p.type === 'date' ? 'date' : p.type === 'int' || p.type === 'float' ? 'number' : 'text'}
                      value={p.default === null || p.default === undefined ? '' : String(p.default)}
                      aria-label={t('reports.paramDefault')}
                      onChange={(e) => {
                        const raw = e.target.value
                        const value = raw === '' ? null : p.type === 'int' || p.type === 'float' ? Number(raw) : raw
                        set({ default: value })
                      }}
                    />
                  </td>
                  <td>
                    <input value={p.label ?? ''} aria-label={t('reports.paramLabel')} onChange={(e) => set({ label: e.target.value })} />
                  </td>
                  <td>
                    <button className="chip-x" aria-label={t('reports.removeParam', { name })} onClick={() => write(entries.filter((_, j) => j !== i))}>
                      ✕
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <button
        className="btn small"
        onClick={() => {
          let n = entries.length + 1
          while (entries.some(([name]) => name === `param_${n}`)) n++
          write([...entries, [`param_${n}`, { type: 'date', default: null, label: '' }]])
        }}
      >
        {t('reports.addParam')}
      </button>
    </fieldset>
  )
}
