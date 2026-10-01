import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'

import { BrandLoading } from './app/ui/BrandLoading'

import { App } from './app/App'
import { AppProviders } from './app/AppProviders'
import { ErrorBoundary } from './app/ErrorBoundary'
import './styles/theme.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/app.css'
import './styles/mobile.css'
import './styles/system-theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <AppProviders>
        <Suspense fallback={<BrandLoading fullscreen />}><App /></Suspense>
      </AppProviders>
    </ErrorBoundary>
  </StrictMode>,
)
