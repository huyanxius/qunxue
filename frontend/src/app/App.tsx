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
  LoginPage,
  MyResearchPage,
  RegisterPage,
  useAccount,
} from '../modules/account'
import {
  demoKnowledgeDataSource,
  KnowledgeExplorer,
} from '../modules/knowledge-explorer'
import { FoundationPage } from './foundation/FoundationPage'
import { PageContent, PageShell, PageTitle } from './ui/PageShell'
import { ErrorState, LoadingState } from './ui/States'

export type SessionState =
  | { status: 'loading' }
  | { status: 'authenticated' }
  | { status: 'anonymous' }
  | { status: 'expired' }
  | { status: 'error' }

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

function LoginRoute({ sessionState }: { sessionState: SessionState }) {
  const { search } = useLocation()
  const navigate = useNavigate()
  const account = useAccount()
  const destination = loginRedirect(new URLSearchParams(search).get('redirect'))

  if (sessionState.status === 'authenticated') {
    return <Navigate replace to={destination} />
  }

  return (
    <PageShell>
      <PageTitle
        eyebrow="ACCOUNT / LOGIN"
        title="登录"
        lede="继续你的研究，或回到刚才准备查看的页面。"
      />
      <PageContent>
        <LoginPage
          onLogin={account.login}
          onAuthenticated={() => navigate(destination, { replace: true })}
          registerHref={`/register?redirect=${encodeURIComponent(destination)}`}
          sessionExpired={sessionState.status === 'expired'}
        />
      </PageContent>
    </PageShell>
  )
}

function RegisterRoute({ sessionState }: { sessionState: SessionState }) {
  const { search } = useLocation()
  const navigate = useNavigate()
  const account = useAccount()
  const destination = loginRedirect(new URLSearchParams(search).get('redirect'))

  if (sessionState.status === 'authenticated') {
    return <Navigate replace to={destination} />
  }

  return (
    <PageShell>
      <PageTitle
        eyebrow="ACCOUNT / REGISTER"
        title="注册"
        lede="研究内容长期保存在你的账号下；你可以随时手动删除一项研究。"
      />
      <PageContent>
        <RegisterPage
          onRegister={account.register}
          onAuthenticated={() => navigate(destination, { replace: true })}
          loginHref={`/login?redirect=${encodeURIComponent(destination)}`}
        />
      </PageContent>
    </PageShell>
  )
}

function MyResearchRoute() {
  return (
    <PageShell>
      <PageTitle
        eyebrow="ACCOUNT / MY"
        title="我的研究"
        lede="按最近更新时间继续研究；删除操作不可恢复。"
      />
      <PageContent><MyResearchPage /></PageContent>
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
  if (sessionState.status === 'error') {
    return <ErrorState detail="暂时无法确认登录状态，请稍后重试。" />
  }

  const redirect = `${location.pathname}${location.search}${location.hash}`
  return <Navigate replace to={`/login?redirect=${encodeURIComponent(redirect)}`} />
}

export function AppRoutes({
  sessionState,
}: AppRoutesProps) {
  const account = useAccount()
  const resolvedSessionState: SessionState = sessionState ?? account.sessionState
  const protectedRoute = (element: ReactNode) => (
    <ProtectedRoute sessionState={resolvedSessionState}>{element}</ProtectedRoute>
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
      <Route path="/login" element={<LoginRoute sessionState={resolvedSessionState} />} />
      <Route path="/register" element={<RegisterRoute sessionState={resolvedSessionState} />} />
      <Route path="/my" element={protectedRoute(<MyResearchRoute />)} />
    </Routes>
  )
}

export function App() {
  return (
    <BrowserRouter useTransitions={false}>
      <AppRoutes />
    </BrowserRouter>
  )
}
