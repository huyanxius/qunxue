import {
  BrowserRouter,
  Route,
  Routes,
  useNavigate,
  useParams,
} from 'react-router'

import {
  demoKnowledgeDataSource,
  KnowledgeExplorer,
} from '../modules/knowledge-explorer'
import { SocioMatchWorkspace } from '../modules/socio-match-workspace'
import { FoundationPage } from './foundation/FoundationPage'

const demoDataNotice =
  '当前页面仅使用虚构占位数据验证信息结构、状态和导航，不代表正式知识库、学术来源或审核结论。'

function KnowledgeExplorerRoute() {
  const navigate = useNavigate()

  return (
    <KnowledgeExplorer
      dataSource={demoKnowledgeDataSource}
      dataNotice={demoDataNotice}
      homeHref="/"
      onNavigateHome={() => navigate('/')}
    />
  )
}

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

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<FoundationPage />} />
      <Route path="/knowledge" element={<KnowledgeExplorerRoute />} />
      <Route
        path="/research/:taskId"
        element={<SocioMatchWorkspaceRoute />}
      />
    </Routes>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
