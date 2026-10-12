import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useT, type MessageKey } from '../i18n'

type Filter = Schemas['ColumnFilter']
type Op = Filter['op']
type Scalar = string | number | boolean

const OPS: { op: Op; label: MessageKey }[] = [
  { op: '=', label: 'op.eq' },
  { op: '!=', label: 'op.neq' },
  { op: '<', label: 'op.lt' },
  { op: '<=', label: 'op.lte' },
  { op: '>', label: 'op.gt' },
  { op: '>=', label: 'op.gte' },
  { op: 'contains', label: 'op.contains' },
  { op: 'starts_with', label: 'op.startsWith' },
  { op: 'between', label: 'op.between' },
  { op: 'in', label: 'op.in' },
  { op: 'is_null', label: 'op.isNull' },
  { op: 'not_null', label: 'op.notNull' },
]
const OP_LABEL = Object.fromEntries(OPS.map((o) => [o.op, o.label])) as Record<Op, MessageKey>
const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|U\w*INT|FLOAT|DOUBLE|REAL|DECIMAL)/i

function parseValue(raw: string, type: string): Scalar {
  const v = raw.trim()
  if (NUMERIC.test(type) && v !== '' && !Number.isNaN(Number(v))) return Number(v)
  if (/^BOOLEAN/i.test(type) && (v === 'true' || v === 'false')) return v === 'true'
  return v
}

interface Props {
  columns: Schemas['ExploreColumn'][]
  filters: Filter[]
  onChange: (filters: Filter[]) => void
}

export function FilterBar({ columns, filters, onChange }: Props) {
  const t = useT()
  const [adding, setAdding] = useState(false)
  const [column, setColumn] = useState('')
  const [op, setOp] = useState<Op>('=')
  const [a, setA] = useState('')
  const [b, setB] = useState('')

  const col = columns.find((c) => c.name === column) ?? columns[0]
  const needsValue = op !== 'is_null' && op !== 'not_null'

  const describe = (f: Filter): string => {
    const sep = f.op === 'between' ? ` ${t('op.and')} ` : ', '
    const v = Array.isArray(f.value) ? f.value.join(sep) : (f.value ?? '')
    return `${f.column} ${t(OP_LABEL[f.op])} ${v}`.trim()
  }

  const add = () => {
    if (!col) return
    const type = col.type
    let value: Filter['value'] = null
    if (op === 'between') value = [parseValue(a, type), parseValue(b, type)]
    else if (op === 'in') value = a.split(',').map((x) => parseValue(x, type)).filter((x) => x !== '')
    else if (needsValue) value = parseValue(a, type)
    onChange([...filters, { column: col.name, op, value }])
    setAdding(false)
    setA('')
    setB('')
  }

  return (
    <div className="filter-bar">
      {filters.map((f, i) => (
        <span key={i} className="chip">
          {describe(f)}
          <button
            className="chip-x"
            aria-label={t('filter.remove', { filter: describe(f) })}
            onClick={() => onChange(filters.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </span>
      ))}
      {!adding && (
        <button className="btn small" onClick={() => setAdding(true)} disabled={!columns.length}>
          {t('filter.add')}
        </button>
      )}
      {adding && col && (
        <form
          className="filter-form"
          onSubmit={(e) => {
            e.preventDefault()
            add()
          }}
        >
          <select value={col.name} onChange={(e) => setColumn(e.target.value)} aria-label={t('schema.column')}>
            {columns.map((c) => <option key={c.name}>{c.name}</option>)}
          </select>
          <select value={op} onChange={(e) => setOp(e.target.value as Op)} aria-label={t('filter.operator')}>
            {OPS.map((o) => <option key={o.op} value={o.op}>{t(o.label)}</option>)}
          </select>
          {needsValue && (
            <input
              autoFocus
              value={a}
              onChange={(e) => setA(e.target.value)}
              placeholder={
                op === 'in' ? 'a, b, c' : /^DATE|^TIMESTAMP/i.test(col.type) ? t('csv.fmt.ymd') : t('filter.value')
              }
              aria-label={t('filter.valueLabel')}
            />
          )}
          {op === 'between' && (
            <input value={b} onChange={(e) => setB(e.target.value)} placeholder={t('filter.to')} aria-label={t('filter.toLabel')} />
          )}
          <button className="btn small primary">{t('filter.apply')}</button>
          <button type="button" className="btn small ghost" onClick={() => setAdding(false)}>
            {t('common.cancel')}
          </button>
        </form>
      )}
    </div>
  )
}
