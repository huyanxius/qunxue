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
  const { task_id = '' } = useParams<{ task_id: string }>()
  const navigate = useNavigate()

  return (
    <SocioMatchWorkspace
      taskId={task_id}
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
        <Route path="/research/:task_id" element={<SocioMatchWorkspaceRoute />} />
      </Routes>
    </BrowserRouter>
  )
}
