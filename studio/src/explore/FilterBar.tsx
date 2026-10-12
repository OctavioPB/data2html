import { useState } from 'react'

import type { Schemas } from '../api/client'

type Filter = Schemas['ColumnFilter']
type Op = Filter['op']
type Scalar = string | number | boolean

const OPS: { op: Op; label: string }[] = [
  { op: '=', label: '=' },
  { op: '!=', label: '≠' },
  { op: '<', label: '<' },
  { op: '<=', label: '≤' },
  { op: '>', label: '>' },
  { op: '>=', label: '≥' },
  { op: 'contains', label: 'contiene' },
  { op: 'starts_with', label: 'empieza con' },
  { op: 'between', label: 'entre' },
  { op: 'in', label: 'es uno de' },
  { op: 'is_null', label: 'está vacío' },
  { op: 'not_null', label: 'no está vacío' },
]
const OP_LABEL = Object.fromEntries(OPS.map((o) => [o.op, o.label])) as Record<Op, string>
const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|U\w*INT|FLOAT|DOUBLE|REAL|DECIMAL)/i

function parseValue(raw: string, type: string): Scalar {
  const v = raw.trim()
  if (NUMERIC.test(type) && v !== '' && !Number.isNaN(Number(v))) return Number(v)
  if (/^BOOLEAN/i.test(type) && (v === 'true' || v === 'false')) return v === 'true'
  return v
}

function describe(f: Filter): string {
  const v = Array.isArray(f.value) ? f.value.join(f.op === 'between' ? ' y ' : ', ') : (f.value ?? '')
  return `${f.column} ${OP_LABEL[f.op]} ${v}`.trim()
}

interface Props {
  columns: Schemas['ExploreColumn'][]
  filters: Filter[]
  onChange: (filters: Filter[]) => void
}

export function FilterBar({ columns, filters, onChange }: Props) {
  const [adding, setAdding] = useState(false)
  const [column, setColumn] = useState('')
  const [op, setOp] = useState<Op>('=')
  const [a, setA] = useState('')
  const [b, setB] = useState('')

  const col = columns.find((c) => c.name === column) ?? columns[0]
  const needsValue = op !== 'is_null' && op !== 'not_null'

  const add = () => {
    if (!col) return
    const t = col.type
    let value: Filter['value'] = null
    if (op === 'between') value = [parseValue(a, t), parseValue(b, t)]
    else if (op === 'in') value = a.split(',').map((x) => parseValue(x, t)).filter((x) => x !== '')
    else if (needsValue) value = parseValue(a, t)
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
            aria-label={`Quitar filtro ${describe(f)}`}
            onClick={() => onChange(filters.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </span>
      ))}
      {!adding && (
        <button className="btn small" onClick={() => setAdding(true)} disabled={!columns.length}>
          + Filtro
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
          <select value={col.name} onChange={(e) => setColumn(e.target.value)} aria-label="Columna">
            {columns.map((c) => <option key={c.name}>{c.name}</option>)}
          </select>
          <select value={op} onChange={(e) => setOp(e.target.value as Op)} aria-label="Operador">
            {OPS.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
          </select>
          {needsValue && (
            <input
              autoFocus
              value={a}
              onChange={(e) => setA(e.target.value)}
              placeholder={op === 'in' ? 'a, b, c' : /^DATE|^TIMESTAMP/i.test(col.type) ? 'AAAA-MM-DD' : 'valor'}
              aria-label="Valor"
            />
          )}
          {op === 'between' && (
            <input value={b} onChange={(e) => setB(e.target.value)} placeholder="hasta" aria-label="Hasta" />
          )}
          <button className="btn small primary">Aplicar</button>
          <button type="button" className="btn small ghost" onClick={() => setAdding(false)}>
            Cancelar
          </button>
        </form>
      )}
    </div>
  )
}
