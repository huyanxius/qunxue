import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router'
import { useCallback, useState, type ReactNode } from 'react'

import {
  LoginPage,
  MyResearchPage,
  RegisterPage,
  useAccount,
} from '../modules/account'
import {
  KnowledgeEntryPage,
  KnowledgeExplorerPage,
  type KnowledgeEntrySummary,
  readKnowledgeUrlState,
  writeKnowledgeUrlState,
} from '../modules/knowledge-explorer'
import { KnowledgeGraphIntegration } from './KnowledgeGraphIntegration'
import { FoundationPage } from './foundation/FoundationPage'
import {
  NewResearchPage,
  PhenomenonWorkspace,
} from '../modules/socio-match-workspace'
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

function KnowledgeExplorerRoute() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = readKnowledgeUrlState(searchParams)
  const [graphOpen, setGraphOpen] = useState(false)
  const [focusEntry, setFocusEntry] = useState<KnowledgeEntrySummary>()

  const updateState = useCallback((nextState: typeof state) => {
    setSearchParams(writeKnowledgeUrlState(nextState))
  }, [setSearchParams])
  const resolveRelease = useCallback((releaseId: string) => {
    setSearchParams((current) => writeKnowledgeUrlState({
      ...readKnowledgeUrlState(current),
      releaseId,
    }))
  }, [setSearchParams])

  return (
    <PageShell>
      <PageContent>
        <KnowledgeExplorerPage
          state={state}
          onStateChange={updateState}
          onReleaseResolved={resolveRelease}
          onOpenEntry={(knowledgeId) => {
            const query = writeKnowledgeUrlState(state).toString()
            navigate(`/knowledge/${encodeURIComponent(knowledgeId)}${query ? `?${query}` : ''}`)
          }}
          onLocateEntry={(entry) => {
            setFocusEntry(entry)
            setGraphOpen(true)
          }}
        />
        {state.releaseId ? (
          <>
            <div className="knowledge-graph-launch">
              <button type="button" onClick={() => setGraphOpen((open) => !open)}>
                {graphOpen ? '收起知识图谱' : '打开知识图谱'}
              </button>
            </div>
            {graphOpen ? (
              <KnowledgeGraphIntegration
                releaseId={state.releaseId}
                focusEntry={focusEntry}
                onSelectKnowledge={(knowledgeId) => {
                  const query = writeKnowledgeUrlState(state).toString()
                  navigate(`/knowledge/${encodeURIComponent(knowledgeId)}${query ? `?${query}` : ''}`)
                }}
              />
            ) : null}
          </>
        ) : null}
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
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = readKnowledgeUrlState(searchParams)
  const resolveRelease = useCallback((releaseId: string) => {
    setSearchParams((current) => writeKnowledgeUrlState({
      ...readKnowledgeUrlState(current),
      releaseId,
    }))
  }, [setSearchParams])

  if (!knowledgeId) {
    return (
      <PageShell>
        <PageContent><ErrorState detail="知识条目地址无效。" /></PageContent>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageContent>
        <KnowledgeEntryPage
          knowledgeId={knowledgeId}
          releaseId={state.releaseId}
          onReleaseResolved={resolveRelease}
          onReturnToResearch={state.returnTo ? () => navigate(state.returnTo) : undefined}
          onReturnToKnowledge={() => {
            const query = writeKnowledgeUrlState({ ...state, returnTo: undefined }).toString()
            navigate(`/knowledge${query ? `?${query}` : ''}`)
          }}
          onStartResearch={({ theoryId, theoryName }) => {
            navigate(
              `/research/new?seed_theory_id=${encodeURIComponent(theoryId)}`,
              { state: { seedTheoryName: theoryName } },
            )
          }}
        />
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

function NewResearchRoute() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const seedTheoryId = searchParams.get('seed_theory_id')
  const seedTheoryName = (
    location.state as { seedTheoryName?: string } | null
  )?.seedTheoryName
  const seedTheory = seedTheoryId
    ? { theoryId: seedTheoryId, name: seedTheoryName }
    : null
  return (
    <PageShell>
      <PageTitle
        eyebrow="RESEARCH / NEW"
        title="新建研究任务"
        lede="先留下你观察到的现象，再决定是否确认演示 AI 提出的候选。"
      />
      <PageContent>
        <NewResearchPage
          seedTheory={seedTheory}
          onStarted={(taskId) => navigate(`/research/${taskId}/phenomenon`)}
        />
      </PageContent>
    </PageShell>
  )
}

function PhenomenonRoute() {
  const { task_id: taskId } = useParams<{ task_id: string }>()
  return (
    <PageShell>
      <PageTitle
        eyebrow="RESEARCH / PHENOMENON"
        title="确认现象"
        lede="编辑演示候选；只有你的确认会形成后续匹配可用的现象快照。"
      />
      <PageContent>
        {taskId ? <PhenomenonWorkspace taskId={taskId} /> : <ErrorState detail="研究任务地址无效。" />}
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
      <Route path="/research/new" element={protectedRoute(<NewResearchRoute />)} />
      <Route path="/research/:task_id/phenomenon" element={protectedRoute(<PhenomenonRoute />)} />
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
