import {
  BrowserRouter,
  Route,
  Routes,
  useNavigate,
  useParams,
} from 'react-router'

import { SocioMatchWorkspace } from '../modules/socio-match-workspace'
import { FoundationPage } from './foundation/FoundationPage'

function SocioMatchWorkspaceRoute() {
  const { taskId = '' } = useParams<{ taskId: string }>()
  const navigate = useNavigate()

  return (
    <SocioMatchWorkspace
      taskId={taskId}
      homeHref="/"
      onNavigateHome={() => navigate('/')}
    />
  )
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<FoundationPage />} />
        <Route
          path="/research/:taskId"
          element={<SocioMatchWorkspaceRoute />}
        />
      </Routes>
    </BrowserRouter>
  )
}
