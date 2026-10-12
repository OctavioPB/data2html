import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // mismo origen en desarrollo: el studio llama a rutas relativas
    proxy: { '/api': API, '/health': API },
  },
})
