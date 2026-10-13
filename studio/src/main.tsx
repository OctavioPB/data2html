import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { setUnauthorizedHandler } from './api/client'
import { App } from './App'
import { useLangStore } from './i18n'
import './index.css'

const queryClient = new QueryClient()

// A 401 anywhere means the session ended: re-check who we are (the app falls back to the sign-in screen)
setUnauthorizedHandler(() => void queryClient.invalidateQueries({ queryKey: ['me'] }))

// Changing the language refetches: server messages (errors, profile warnings…) come back localized
useLangStore.subscribe((state, prev) => {
  if (state.lang !== prev.lang) void queryClient.invalidateQueries()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
