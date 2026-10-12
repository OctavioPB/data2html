import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useDeleteComputed, usePutComputed } from '../api/queries'
import { useT } from '../i18n'

const NAME_RE = /^[a-z_][a-z0-9_]{0,62}$/

interface Props {
  source: string
  table: string
  computed: Schemas['ComputedColumn'][]
}

/** Computed columns: scalar SQL expressions over the table's columns. */
export function ComputedColumns({ source, table, computed }: Props) {
  const t = useT()
  const put = usePutComputed(source, table)
  const del = useDeleteComputed(source, table)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [expr, setExpr] = useState('')

  const edit = (c?: Schemas['ComputedColumn']) => {
    setName(c?.name ?? '')
    setExpr(c?.expr ?? '')
    put.reset()
    setOpen(true)
  }

  return (
    <div className="computed">
      {computed.map((c) => (
        <span key={c.name} className="chip computed-chip" title={`${c.expr} → ${c.type}`}>
          <button className="chip-label" onClick={() => edit(c)}>
            ƒ {c.name}
          </button>
          <button
            className="chip-x"
            aria-label={t('computed.delete', { name: c.name })}
            disabled={del.isPending}
            onClick={() => del.mutate(c.name)}
          >
            ✕
          </button>
        </span>
      ))}
      {!open && (
        <button className="btn small" onClick={() => edit()}>
          {t('computed.add')}
        </button>
      )}
      {open && (
        <form
          className="computed-form"
          onSubmit={(e) => {
            e.preventDefault()
            put.mutate({ name, expr }, { onSuccess: () => setOpen(false) })
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('computed.namePlaceholder')}
            aria-label={t('computed.name')}
            aria-invalid={name !== '' && !NAME_RE.test(name)}
          />
          <span className="muted">=</span>
          <input
            className="mono expr"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
            placeholder="precio * unidades * (1 - coalesce(descuento, 0))"
            aria-label={t('computed.expr')}
          />
          <button className="btn small primary" disabled={!NAME_RE.test(name) || !expr || put.isPending}>
            {put.isPending ? t('computed.testing') : t('common.save')}
          </button>
          <button type="button" className="btn small ghost" onClick={() => setOpen(false)}>
            {t('common.cancel')}
          </button>
          {put.isError && <span className="error small">{put.error.message}</span>}
        </form>
      )}
    </div>
  )
}
