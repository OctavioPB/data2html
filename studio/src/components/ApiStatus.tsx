import { useHealth } from '../api/queries'
import { useT } from '../i18n'

export function ApiStatus() {
  const t = useT()
  const { data, isPending, isError } = useHealth()
  const [state, label] = isPending
    ? ['pending', t('api.pending')]
    : isError
      ? ['down', t('api.down')]
      : ['ok', t('api.ok', { version: data.version })]
  return (
    <span className="api-status" data-state={state} role="status">
      <span className="dot" aria-hidden />
      {label}
    </span>
  )
}
