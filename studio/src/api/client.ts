import createClient from 'openapi-fetch'

import type { components, paths } from '../generated/api'
import { getLang } from '../i18n'

export type Schemas = components['schemas']

/** Typed client generated from the backend's OpenAPI. Regenerate with `npm run gen:api`. */
export const api = createClient<paths>({ baseUrl: '' })

let onUnauthorized = () => {}

/** Called when a request finds the session gone (expired, revoked): the app shows the sign-in screen. */
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

// Server messages (errors, warnings) come back in the studio's language
api.use({
  onRequest({ request }) {
    request.headers.set('Accept-Language', getLang())
    return request
  },
  onResponse({ request, response }) {
    if (response.status === 401 && !new URL(request.url, window.location.href).pathname.endsWith('/api/me')) onUnauthorized()
    return response
  },
})
