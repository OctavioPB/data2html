import createClient from 'openapi-fetch'

import type { components, paths } from '../generated/api'

export type Schemas = components['schemas']

/** Cliente tipado desde el OpenAPI del backend. Regenera con `npm run gen:api`. */
export const api = createClient<paths>({ baseUrl: '' })
