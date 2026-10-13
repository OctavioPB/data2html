import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = 'http://localhost:8000'
// Keep the browser's Host header (Vite's shorthand rewrites it): the backend's CSRF check compares Origin
// with the request's own origin, which must stay http://localhost:5173 through the proxy.
const backend = { target: API, changeOrigin: false }

export default defineConfig({
  plugins: [react()],
  server: {
    // same origin in development: the studio calls relative paths, the session cookie is shared, and the
    // sign-in pages and "Open viewer" links work too
    proxy: Object.fromEntries(
      ['/api', '/health', '/r', '/r-static', '/login', '/auth', '/logout', '/dev'].map((p) => [p, backend]),
    ),
  },
})
