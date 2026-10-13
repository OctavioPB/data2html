// data2html live viewer. The page carries no data: each visual asks the server for its aggregated rows
// with the reader's session (RLS applied there). Text goes in with textContent, never innerHTML.
// Chart mapping mirrors the studio (studio/src/render/VisualChart.tsx; html-renderer skill).
'use strict'
;(() => {
  const view = JSON.parse(document.getElementById('d2h-view').textContent)
  const LANGS = ['en', 'es']
  const LOCALES = { en: 'en-US', es: 'es-MX' }
  const MAX_SERIES = 8
  const MAX_PIE = 8
  const LANG_KEY = 'd2h.lang'

  // ------------------------------------------------------------------ language
  function initialLang() {
    try {
      const saved = localStorage.getItem(LANG_KEY)
      if (LANGS.includes(saved)) return saved
    } catch { /* storage blocked: follow the browser */ }
    return (navigator.language || 'en').toLowerCase().startsWith('es') ? 'es' : 'en'
  }
  let lang = initialLang()
  const t = (key, params) =>
    (view.strings[lang][key] ?? key).replace(/\{(\w+)\}/g, (_, k) => String(params?.[k] ?? ''))

  // ------------------------------------------------------------------ state
  const params = {}
  for (const [name, p] of Object.entries(view.params)) params[name] = p.default ?? ''
  let applied = { ...params }
  let cross = [] // [{ dimension, value, from }]
  const marks = Object.fromEntries(view.visuals.map((v) => [v.id, v.mark]))
  const cards = new Map() // visual id → { body, chart, data, ctrl }
  const dark = window.matchMedia('(prefers-color-scheme: dark)')

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag)
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue
      if (k === 'class') node.className = v
      else if (k === 'text') node.textContent = v
      else if (k.startsWith('on')) node.addEventListener(k.slice(2), v)
      else node.setAttribute(k, v === true ? '' : String(v))
    }
    for (const c of children) if (c) node.append(c)
    return node
  }
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

  function applyTheme() {
    const root = document.documentElement.style
    const palette = dark.matches ? view.theme.palette.dark : view.theme.palette.light
    palette.forEach((c, i) => root.setProperty(`--series-${i + 1}`, c))
    root.setProperty('--font', view.theme.font)
  }
  const palette = () => (dark.matches ? view.theme.palette.dark : view.theme.palette.light)

  function formatter(format, compact = false) {
    const base = compact ? { notation: 'compact', maximumFractionDigits: 1 } : {}
    let opts = { maximumFractionDigits: 2, ...base }
    if (format === 'currency') {
      opts = { style: 'currency', currency: view.theme.currency, maximumFractionDigits: compact ? 1 : 2, ...base }
    } else if (format === 'percent') {
      opts = { style: 'percent', maximumFractionDigits: 1, ...base }
    }
    const nf = new Intl.NumberFormat(LOCALES[lang], opts)
    return (v) => (typeof v === 'number' ? nf.format(v) : v === null || v === undefined ? '—' : String(v))
  }
  const label = (v) => (v === null || v === undefined ? '∅' : String(v))

  /** A period start ("2025-04-01") by its grain: "abr 2025", "T2 2025"/"Q2 2025", "2025"… (UTC: no day shift). */
  function period(value, grain) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value ?? ''))
    if (!grain || !m) return label(value)
    const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
    const date = new Date(Date.UTC(y, mo - 1, d))
    if (grain === 'year') return String(y)
    if (grain === 'quarter') return `${lang === 'es' ? 'T' : 'Q'}${Math.floor((mo - 1) / 3) + 1} ${y}`
    if (grain === 'month') return date.toLocaleDateString(LOCALES[lang], { month: 'short', year: 'numeric', timeZone: 'UTC' })
    return date.toLocaleDateString(LOCALES[lang], { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
  }

  // ------------------------------------------------------------------ layout
  function render() {
    document.documentElement.lang = lang
    applyTheme()
    for (const c of cards.values()) c.chart?.dispose()
    cards.clear()
    const app = document.getElementById('app')
    app.replaceChildren(header(), controls(), chips(), grid())
    view.visuals.forEach((v) => load(v))
  }

  function header() {
    const langSwitch = el('div', { class: 'seg', role: 'group', 'aria-label': t('language') },
      ...LANGS.map((l) => el('button', {
        type: 'button', text: l.toUpperCase(), 'aria-pressed': String(l === lang),
        onclick: () => {
          if (l === lang) return
          lang = l
          try { localStorage.setItem(LANG_KEY, l) } catch { /* not persisted */ }
          render()
        },
      })))
    const logout = el('form', { method: 'post', action: '/logout' },
      el('button', { class: 'btn', type: 'submit', text: t('signOut') }))
    return el('header', { class: 'top' },
      el('h1', { text: view.title }),
      el('div', { class: 'top-right' },
        el('span', { class: 'muted small', text: t('signedInAs', { user: view.user }) }), langSwitch, logout))
  }

  function controls() {
    const names = Object.keys(view.params)
    if (names.length === 0) return null
    const form = el('form', { class: 'controls', 'aria-label': t('params') })
    for (const name of names) {
      const p = view.params[name]
      const caption = p.label || name
      let input
      if (p.type === 'bool') {
        input = el('select', { name },
          el('option', { value: 'true', text: t('yes') }), el('option', { value: 'false', text: t('no') }))
        input.value = String(params[name] === true || params[name] === 'true')
      } else {
        const type = p.type === 'date' ? 'date' : p.type === 'int' || p.type === 'float' ? 'number' : 'text'
        input = el('input', { name, type, step: p.type === 'float' ? 'any' : undefined, value: params[name] })
      }
      input.addEventListener('change', () => { params[name] = input.value })
      form.append(el('label', {}, caption, input))
    }
    form.append(el('button', { class: 'btn primary', type: 'submit', text: t('apply') }))
    form.addEventListener('submit', (e) => {
      e.preventDefault()
      for (const input of form.querySelectorAll('input, select')) params[input.name] = input.value
      applied = { ...params }
      view.visuals.forEach((v) => load(v))
    })
    return form
  }

  function chips() {
    const row = el('div', { class: 'chips', 'aria-live': 'polite' })
    if (cross.length === 0) {
      if (view.visuals.some((v) => v.crossFilter) && view.visuals.length > 1) {
        row.append(el('span', { class: 'muted small', text: t('crossHint') }))
      }
      return row
    }
    row.append(el('span', { class: 'muted', text: t('filteredBy') }))
    for (const f of cross) {
      const name = `${f.dimension} = ${f.value}`
      row.append(el('span', { class: 'chip' }, name,
        el('button', { type: 'button', text: '×', 'aria-label': t('removeFilter', { filter: name }),
          onclick: () => setCross(cross.filter((x) => x !== f)) })))
    }
    return row
  }

  function setCross(next) {
    cross = next
    document.querySelector('.chips').replaceWith(chips())
    view.visuals.forEach((v) => load(v))
  }

  function grid() {
    const g = el('main', { class: 'grid' })
    for (const v of view.visuals) {
      const select = el('select', { 'aria-label': t('chartType') },
        ...v.allowed.map((m) => el('option', { value: m, text: t(`mark.${m}`) })))
      select.value = marks[v.id]
      const body = el('div', { class: 'card-body' })
      const asOf = el('p', { class: 'as-of' }) // snapshot reports: when this reader's data was taken
      // downloads: the same rows the reader sees (CSV from the server, with RLS) or the drawn chart (PNG)
      const csv = el('a', { class: 'icon-btn', text: 'CSV', title: t('downloadCsv'), 'aria-label': t('downloadCsv'),
        href: '#', onclick: () => { csv.href = dataUrl(v, '.csv') } })
      const png = el('button', { class: 'icon-btn', type: 'button', text: 'PNG', title: t('downloadPng'),
        'aria-label': t('downloadPng'), onclick: () => downloadPng(v) })
      const card = el('section', { class: 'card', 'aria-label': v.title, 'data-visual': v.id },
        el('div', { class: 'card-head' }, el('h2', { text: v.title, title: v.title }),
          el('div', { class: 'card-tools' }, v.allowed.length > 1 ? select : null, csv, png)),
        asOf, body)
      const L = v.layout
      card.style.gridColumn = `${L.x + 1} / span ${L.w}`
      card.style.gridRow = `${L.y + 1} / span ${L.h}`
      card.style.setProperty('--h', String(L.h))
      select.addEventListener('change', () => {
        marks[v.id] = select.value
        const c = cards.get(v.id)
        if (c?.data) draw(v, c.data) // same data, new mark: no new query
      })
      cards.set(v.id, { v, body, asOf, chart: null, data: null, ctrl: null })
      g.append(card)
    }
    return g
  }

  // ------------------------------------------------------------------ data
  /** URL of a visual's data with the applied parameters and the other visuals' cross-filters. */
  function dataUrl(v, suffix = '') {
    const qs = new URLSearchParams()
    for (const [name, value] of Object.entries(applied)) if (value !== '' && value !== null) qs.append(`p.${name}`, String(value))
    for (const f of cross) if (f.from !== v.id) qs.append('cf', `${f.dimension}:${f.value}`)
    return `/api/r/${encodeURIComponent(view.id)}/visuals/${encodeURIComponent(v.id)}${suffix}?${qs}`
  }

  function downloadPng(v) {
    const c = cards.get(v.id)
    if (!c?.chart) return // tables and KPIs: use CSV
    const a = el('a', { href: c.chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: cssVar('--panel') }),
      download: `${view.id}-${v.id}.png` })
    a.click()
  }

  function setPngAvailable(v, available) {
    const btn = document.querySelector(`.card[data-visual="${v.id}"] button.icon-btn`)
    if (btn) btn.disabled = !available
  }

  async function load(v) {
    const c = cards.get(v.id)
    c.ctrl?.abort()
    const ctrl = new AbortController()
    c.ctrl = ctrl
    if (!c.data) state(c, t('loading'))
    try {
      const r = await fetch(dataUrl(v), {
        headers: { 'Accept-Language': lang }, credentials: 'same-origin', signal: ctrl.signal,
      })
      if (r.status === 401) {
        window.location.assign(`/login?next=${encodeURIComponent(location.pathname)}`)
        return
      }
      const body = await r.json()
      if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : r.statusText)
      c.data = body
      c.asOf.textContent = body.as_of
        ? t('asOf', { when: new Date(body.as_of).toLocaleString(LOCALES[lang], { dateStyle: 'medium', timeStyle: 'short' }) })
        : ''
      draw(v, body)
    } catch (e) {
      if (e.name === 'AbortError') return
      c.data = null
      c.chart?.dispose()
      c.chart = null
      const p = el('p', { class: 'state error', role: 'alert', text: t('error', { error: e.message }) })
      p.append(el('button', { class: 'btn', type: 'button', text: t('retry'), onclick: () => load(v) }))
      c.body.replaceChildren(p)
    }
  }

  function state(c, text) {
    if (c.v) setPngAvailable(c.v, false)
    c.chart?.dispose()
    c.chart = null
    c.body.replaceChildren(el('p', { class: 'state', text }))
  }

  // ------------------------------------------------------------------ drawing
  function draw(v, data) {
    drawMark(v, data)
    setPngAvailable(v, Boolean(cards.get(v.id)?.chart))
  }

  function drawMark(v, data) {
    const c = cards.get(v.id)
    const mark = marks[v.id]
    c.chart?.dispose()
    c.chart = null
    if (mark === 'table') return c.body.replaceChildren(table(v, data))
    if (mark === 'kpi') return c.body.replaceChildren(kpi(v, data))
    if (data.rows.length === 0) return state(c, t('noRows'))
    const shaped = toSeries(v, data)
    if (shaped.error) return state(c, shaped.error)
    if (mark === 'pie' && shaped.cats.length > MAX_PIE) {
      return state(c, t('tooManySlices', { n: shaped.cats.length, max: MAX_PIE }))
    }
    const host = el('div', { class: 'chart', role: 'img',
      'aria-label': t('chartAria', { measure: v.measure, dimension: v.dimension ?? '' }) })
    c.body.replaceChildren(host)
    const chart = window.echarts.init(host)
    chart.setOption(option(v, mark, shaped))
    if (v.crossFilter && mark !== 'line') {
      chart.on('click', (e) => {
        const value = shaped.raw[e.dataIndex]
        if (value === null || value === undefined) return
        const others = cross.filter((f) => f.from !== v.id)
        const same = cross.find((f) => f.from === v.id && f.value === String(value))
        setCross(same ? others : [...others, { dimension: v.dimension, value: String(value), from: v.id }])
      })
    }
    c.chart = chart
  }

  function table(v, data) {
    const fmt = formatter(v.format)
    const isMeasure = data.columns.map((col) => col.name === v.measure)
    const isDim = data.columns.map((col) => col.name === v.dimension)
    const head = el('tr', {}, ...data.columns.map((col, j) =>
      el('th', { class: isMeasure[j] ? 'num' : undefined, scope: 'col', text: col.name })))
    const rows = data.rows.map((r) => el('tr', {}, ...r.map((cell, j) =>
      el('td', { class: isMeasure[j] ? 'num' : undefined,
        text: isMeasure[j] ? fmt(cell) : isDim[j] ? period(cell, v.grain) : label(cell) }))))
    return el('div', { class: 'table-wrap' }, el('table', {}, el('thead', {}, head), el('tbody', {}, ...rows)))
  }

  function kpi(v, data) {
    if (data.rows.length !== 1) return el('p', { class: 'state', text: t('kpiOneRow') })
    const i = data.columns.findIndex((col) => col.name === v.measure)
    return el('div', { class: 'kpi' },
      el('div', { class: 'kpi-value', text: formatter(v.format)(data.rows[0][i]) }),
      el('div', { class: 'kpi-label', text: v.measure }))
  }

  /** Rows → categories and series. With `color`, one series per value (a pivot, never an aggregation). */
  function toSeries(v, data) {
    const idx = (name) => data.columns.findIndex((col) => col.name === name)
    const di = v.dimension ? idx(v.dimension) : -1
    const mi = idx(v.measure)
    const num = (x) => (typeof x === 'number' ? x : x === null ? null : Number(x))
    if (v.color) {
      const ci = idx(v.color)
      const raw = [...new Set(data.rows.map((r) => r[di]))]
      const cats = raw.map((x) => period(x, v.grain))
      const names = [...new Set(data.rows.map((r) => label(r[ci])))]
      if (names.length > MAX_SERIES) return { error: t('tooManyColors', { n: names.length, max: MAX_SERIES }) }
      const series = names.map((name) => {
        const byCat = new Map(data.rows.filter((r) => label(r[ci]) === name).map((r) => [period(r[di], v.grain), num(r[mi])]))
        return { name, values: cats.map((cat) => byCat.get(cat) ?? null) }
      })
      return { cats, raw, series }
    }
    const raw = data.rows.map((r, i) => (di >= 0 ? r[di] : i + 1))
    return { cats: raw.map((x) => period(x, v.grain)), raw, series: [{ name: v.measure, values: data.rows.map((r) => num(r[mi])) }] }
  }

  // Tooltip as DOM (text only; styles through CSSOM, which the CSP allows)
  function tip(title, rows, fmt) {
    const box = el('div', { class: 'tip' })
    if (title) box.append(el('strong', { text: title }))
    for (const r of rows) {
      const dot = el('span', { class: 'tip-dot' })
      dot.style.background = r.color
      box.append(el('div', { class: 'tip-row' }, dot, el('span', { text: r.name }),
        el('span', { class: 'tip-value', text: fmt(r.value) })))
    }
    return box
  }

  function option(v, mark, { cats, series }) {
    const selected = cross.find((f) => f.from === v.id)?.value
    const dim = (cat) => (selected !== undefined && cat !== selected ? { opacity: 0.35 } : undefined)
    const fmt = formatter(v.format)
    const compact = formatter(v.format, true)
    const text = cssVar('--text')
    const muted = cssVar('--muted')
    const border = cssVar('--border')
    const surface = cssVar('--panel')
    const base = {
      color: palette(),
      animation: false,
      textStyle: { color: text, fontFamily: view.theme.font },
      tooltip: {
        trigger: mark === 'pie' ? 'item' : 'axis',
        backgroundColor: surface,
        borderColor: border,
        textStyle: { color: text },
        formatter: (p) => {
          const items = Array.isArray(p) ? p : [p]
          const title = mark === 'pie' ? null : items[0]?.name
          return tip(title, items.map((i) => ({ color: i.color, name: mark === 'pie' ? i.name : i.seriesName, value: i.value })), fmt)
        },
      },
      legend: series.length > 1 || mark === 'pie' ? { top: 0, itemGap: 16, textStyle: { color: text } } : undefined,
    }
    if (mark === 'pie') {
      return {
        ...base,
        series: [{
          type: 'pie', top: 28, radius: ['0%', '70%'],
          itemStyle: { borderColor: surface, borderWidth: 2 },
          label: { color: text },
          data: cats.map((name, i) => ({ name, value: series[0].values[i], itemStyle: dim(name) })),
        }],
      }
    }
    return {
      ...base,
      grid: { left: 8, right: 16, top: series.length > 1 ? 32 : 12, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category', data: cats,
        axisLine: { lineStyle: { color: border } }, axisTick: { show: false },
        axisLabel: { color: muted, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: border, opacity: 0.6 } },
        axisLabel: { color: muted, formatter: (x) => compact(x) },
      },
      series: series.map((s) => mark === 'bar'
        ? { name: s.name, type: 'bar', data: s.values.map((value, i) => ({ value, itemStyle: dim(cats[i]) })), barMaxWidth: 28, barGap: '8%', itemStyle: { borderRadius: [4, 4, 0, 0] }, cursor: v.crossFilter ? 'pointer' : 'default' }
        : { name: s.name, type: 'line', data: s.values, lineStyle: { width: 2 }, symbolSize: 8,
            itemStyle: { borderColor: surface, borderWidth: 2 }, showSymbol: cats.length <= 60, connectNulls: false }),
    }
  }

  // ------------------------------------------------------------------ start
  window.addEventListener('resize', () => { for (const c of cards.values()) c.chart?.resize() })
  dark.addEventListener('change', () => {
    applyTheme()
    for (const v of view.visuals) { const c = cards.get(v.id); if (c?.data) draw(v, c.data) }
  })
  render()
})()
