import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useDeleteComputed, usePutComputed } from '../api/queries'

const NAME_RE = /^[a-z_][a-z0-9_]{0,62}$/

interface Props {
  source: string
  table: string
  computed: Schemas['ComputedColumn'][]
}

/** Columnas calculadas: expresiones SQL escalares sobre las columnas de la tabla. */
export function ComputedColumns({ source, table, computed }: Props) {
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
            aria-label={`Borrar columna calculada ${c.name}`}
            disabled={del.isPending}
            onClick={() => del.mutate(c.name)}
          >
            ✕
          </button>
        </span>
      ))}
      {!open && (
        <button className="btn small" onClick={() => edit()}>
          + Columna calculada
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
            placeholder="nombre"
            aria-label="Nombre de la columna"
            aria-invalid={name !== '' && !NAME_RE.test(name)}
          />
          <span className="muted">=</span>
          <input
            className="mono expr"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
            placeholder="precio * unidades * (1 - coalesce(descuento, 0))"
            aria-label="Expresión SQL"
          />
          <button className="btn small primary" disabled={!NAME_RE.test(name) || !expr || put.isPending}>
            {put.isPending ? 'Probando…' : 'Guardar'}
          </button>
          <button type="button" className="btn small ghost" onClick={() => setOpen(false)}>
            Cancelar
          </button>
          {put.isError && <span className="error small">{put.error.message}</span>}
        </form>
      )}
    </div>
  )
}
