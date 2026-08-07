import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router'
import type { ReactNode } from 'react'

import {
  demoKnowledgeDataSource,
  KnowledgeExplorer,
} from '../modules/knowledge-explorer'
import { FoundationPage } from './foundation/FoundationPage'
import { PageContent, PageShell, PageTitle } from './ui/PageShell'
import { LoadingState } from './ui/States'

export type SessionState =
  | { status: 'loading' }
  | { status: 'authenticated' }
  | { status: 'anonymous' }
  | { status: 'expired' }

type AppRoutesProps = {
  sessionState?: SessionState
}

const demoDataNotice =
  '当前页面仅使用虚构占位数据验证信息结构、状态和导航，不代表正式知识库、学术来源或审核结论。'

function KnowledgeExplorerRoute() {
  const navigate = useNavigate()

  return (
    <PageShell>
      <PageContent>
        <KnowledgeExplorer
          dataSource={demoKnowledgeDataSource}
          dataNotice={demoDataNotice}
          homeHref="/"
          onNavigateHome={() => navigate('/')}
        />
      </PageContent>
    </PageShell>
  )
}

function PlaceholderPage({
  eyebrow,
  title,
}: {
  eyebrow: string
  title: string
}) {
  return (
    <PageShell>
      <PageTitle
        eyebrow={eyebrow}
        title={title}
        lede="页面已保留稳定入口；具体业务能力将在对应边界完成后接入。"
      />
      <PageContent>
        <p className="page-placeholder">此处暂不展示业务数据或预设结果。</p>
      </PageContent>
    </PageShell>
  )
}

function KnowledgeEntryRoute() {
  const { knowledge_id: knowledgeId } = useParams<{ knowledge_id: string }>()

  return (
    <PageShell>
      <PageTitle eyebrow="KNOWLEDGE / ENTRY" title="知识条目" />
      <PageContent>
        <p className="page-placeholder">
          {knowledgeId ? `正在保留条目 ${knowledgeId} 的稳定地址。` : '正在保留条目的稳定地址。'}
        </p>
        <Link className="text-link" to="/knowledge">返回知识浏览</Link>
      </PageContent>
    </PageShell>
  )
}

function loginRedirect(value: string | null) {
  if (!value?.startsWith('/')) return '/'

  const origin = 'https://qunxue.local'
  try {
    const target = new URL(value, origin)
    return target.origin === origin
      ? `${target.pathname}${target.search}${target.hash}`
      : '/'
  } catch {
    return '/'
  }
}

function LoginRoute() {
  const { search } = useLocation()
  const destination = loginRedirect(new URLSearchParams(search).get('redirect'))

  return (
    <PageShell>
      <PageTitle eyebrow="ACCOUNT / LOGIN" title="登录" />
      <PageContent>
        <p className="page-placeholder">登录能力将在会话契约完成后接入。</p>
        <Link className="text-link" to={destination}>登录成功后继续</Link>
      </PageContent>
    </PageShell>
  )
}

function ProtectedRoute({
  sessionState,
  children,
}: {
  sessionState: SessionState
  children: ReactNode
}) {
  const location = useLocation()

  if (sessionState.status === 'loading') {
    return <LoadingState message="正在确认登录状态" />
  }
  if (sessionState.status === 'authenticated') return children

  const redirect = `${location.pathname}${location.search}${location.hash}`
  return <Navigate replace to={`/login?redirect=${encodeURIComponent(redirect)}`} />
}

export function AppRoutes({
  sessionState = { status: 'anonymous' },
}: AppRoutesProps) {
  const protectedRoute = (element: ReactNode) => (
    <ProtectedRoute sessionState={sessionState}>{element}</ProtectedRoute>
  )

  return (
    <Routes>
      <Route path="/" element={<FoundationPage />} />
      <Route path="/knowledge" element={<KnowledgeExplorerRoute />} />
      <Route path="/knowledge/:knowledge_id" element={<KnowledgeEntryRoute />} />
      <Route path="/research/new" element={protectedRoute(<PlaceholderPage eyebrow="RESEARCH / NEW" title="新建研究任务" />)} />
      <Route path="/research/:task_id/phenomenon" element={protectedRoute(<PlaceholderPage eyebrow="RESEARCH / PHENOMENON" title="确认现象" />)} />
      <Route path="/research/:task_id/match" element={protectedRoute(<PlaceholderPage eyebrow="RESEARCH / MATCH" title="匹配理论" />)} />
      <Route path="/research/:task_id/framework" element={protectedRoute(<PlaceholderPage eyebrow="RESEARCH / FRAMEWORK" title="研究框架" />)} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/register" element={<PlaceholderPage eyebrow="ACCOUNT / REGISTER" title="注册" />} />
      <Route path="/my" element={protectedRoute(<PlaceholderPage eyebrow="ACCOUNT / MY" title="我的研究" />)} />
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
