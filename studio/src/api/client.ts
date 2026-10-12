import createClient from 'openapi-fetch'

import type { components, paths } from '../generated/api'
import { getLang } from '../i18n'

export type Schemas = components['schemas']

/** Typed client generated from the backend's OpenAPI. Regenerate with `npm run gen:api`. */
export const api = createClient<paths>({ baseUrl: '' })

// Server messages (errors, warnings) come back in the studio's language
api.use({
  onRequest({ request }) {
    request.headers.set('Accept-Language', getLang())
    return request
  },
})
