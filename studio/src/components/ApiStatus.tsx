import { useHealth } from '../api/queries'

export function ApiStatus() {
  const { data, isPending, isError } = useHealth()
  const [state, label] = isPending
    ? ['pending', 'API…']
    : isError
      ? ['down', 'API sin conexión']
      : ['ok', `API OK · v${data.version}`]
  return (
    <span className="api-status" data-state={state} role="status">
      <span className="dot" aria-hidden />
      {label}
    </span>
  )
}
