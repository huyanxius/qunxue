import { BrowserRouter, Route, Routes } from 'react-router'

import { SocioMatchWorkspace } from '../modules/socio-match-workspace'
import { FoundationPage } from './foundation/FoundationPage'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<FoundationPage />} />
        <Route path="/research/:taskId" element={<SocioMatchWorkspace />} />
      </Routes>
    </BrowserRouter>
  )
}
