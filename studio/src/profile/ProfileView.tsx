import { useState } from 'react'

import type { Schemas } from '../api/client'
import { useProfile, useRefreshProfile } from '../api/queries'
import { CorrelationMatrix } from './charts'
import { fmtCompact } from './format'
import { ColumnCard } from './ColumnCard'

const nf = new Intl.NumberFormat('es-MX')

interface Props {
  source: string
  table: Schemas['TableOut']
}

export function ProfileView({ source, table }: Props) {
  const computedKey = table.computed.map((c) => `${c.name}=${c.expr}`).join('|')
  const { data, isPending, isError, error, cancel, refetch } = useProfile(source, table.name, computedKey)
  const refresh = useRefreshProfile(source, table.name, computedKey)
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson')

  if (isPending) {
    return (
      <div className="profile-head">
        <p className="muted">Perfilando… (en tablas grandes puede tardar unos segundos)</p>
        <button className="btn small" onClick={cancel}>
          Cancelar
        </button>
      </div>
    )
  }
  if (isError) {
    return (
      <div className="profile-head">
        <p className="error">{error.message}</p>
        <button className="btn small" onClick={() => void refetch()}>
          Reintentar
        </button>
      </div>
    )
  }

  const flagged = data.columns.filter((c) => c.warnings.length > 0)

  return (
    <div className="profile">
      <div className="profile-head">
        {data.sampled ? (
          <p className="sample-banner" role="note">
            <strong>Muestra:</strong> perfil calculado sobre {nf.format(data.rows)} filas al azar de una
            fuente remota. Los conteos y distintos son de la muestra, no de la tabla completa.
          </p>
        ) : (
          <p className="muted small">
            Perfil de las {nf.format(data.rows)} filas
            {data.sample_size ? ' (la tabla completa cupo en la muestra)' : ''}.
          </p>
        )}
        <span className="muted small">
          {(data.elapsed_ms / 1000).toFixed(1)} s · {new Date(data.profiled_at).toLocaleString('es-MX')}
        </span>
        <button className="btn small" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? 'Recalculando…' : 'Recalcular'}
        </button>
      </div>

      {flagged.length > 0 && (
        <section className="profile-warnings">
          <h3>Avisos</h3>
          <ul>
            {flagged.flatMap((c) =>
              c.warnings.map((w) => (
                <li key={`${c.name}-${w.code}`}>
                  <span aria-hidden>⚠</span>{' '}
                  <a href={`#perfil-${c.name}`} onClick={(e) => jump(e, c.name)} className="mono">
                    {c.name}
                  </a>
                  : {w.message}
                </li>
              )),
            )}
          </ul>
        </section>
      )}

      <div className="col-grid">
        {data.columns.map((c) => (
          <ColumnCard key={c.name} col={c} />
        ))}
      </div>

      {data.correlations && (
        <section className="profile-corr">
          <header>
            <h3>Correlaciones</h3>
            <div className="seg" role="radiogroup" aria-label="Método">
              {(['pearson', 'spearman'] as const).map((m) => (
                <button key={m} role="radio" aria-checked={method === m} onClick={() => setMethod(m)}>
                  {m === 'pearson' ? 'Pearson' : 'Spearman'}
                </button>
              ))}
            </div>
            <span className="muted small">
              n = {fmtCompact(data.correlations.n)}
              {data.correlations.n < data.rows ? ' (muestra)' : ''} · {method === 'pearson' ? 'relación lineal' : 'relación monótona (rangos)'}
            </span>
          </header>
          <CorrelationMatrix columns={data.correlations.columns} values={data.correlations[method]} />
        </section>
      )}
    </div>
  )
}

/** El hash de la URL es la tabla abierta: el salto a una columna no debe tocarlo. */
function jump(e: React.MouseEvent, name: string) {
  e.preventDefault()
  document.getElementById(`perfil-${name}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
