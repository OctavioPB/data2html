/**
 * Downloads of a visual (Phase 8): CSV from the server (the same aggregated rows the preview shows,
 * with formula-injection guards and a BOM for Excel) and PNG from the drawn chart.
 */
import type { EChartsType } from 'echarts/core'

import type { Schemas } from '../api/client'
import { errorMessage } from '../api/queries'
import { getLang } from '../i18n'

function save(href: string, filename: string) {
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
}

/** CSV of a builder/editor visual (author preview). */
export async function downloadVisualCsv(req: Schemas['VisualRequest']): Promise<void> {
  const r = await fetch('/api/visual/export.csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept-Language': getLang() },
    body: JSON.stringify(req),
    credentials: 'same-origin',
  })
  if (!r.ok) throw new Error(errorMessage(await r.json().catch(() => undefined), r.status))
  const name = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') ?? '')?.[1] ?? 'visual.csv'
  const url = URL.createObjectURL(await r.blob())
  save(url, name)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** PNG of a chart. The studio draws SVG, so it is rasterized on a canvas at 2× for sharp text. */
export async function downloadChartPng(chart: EChartsType, filename: string, background: string): Promise<void> {
  const svg = chart.getDataURL({ type: 'svg', backgroundColor: background })
  const img = new Image()
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('svg'))
    img.src = svg
  })
  const scale = 2
  const canvas = document.createElement('canvas')
  canvas.width = chart.getWidth() * scale
  canvas.height = chart.getHeight() * scale
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = background
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  save(canvas.toDataURL('image/png'), filename)
}
