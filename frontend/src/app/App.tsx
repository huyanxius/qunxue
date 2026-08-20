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
  readKnowledgeGraphReturnTo,
  saveKnowledgeListScroll,
  readKnowledgeUrlState,
  writeKnowledgeUrlState,
} from '../modules/knowledge-explorer'
import {
  FullscreenKnowledgeGraphPage,
  type FullscreenKnowledgeGraphState,
} from '../modules/knowledge-graph'
import { KnowledgeGraphIntegration } from './KnowledgeGraphIntegration'
import { ResearchAgentPage } from './agent/ResearchAgentPage'
import { NewResearchWorkspacePage } from './agent/NewResearchWorkspacePage'
import { ResearchDocumentWorkbench } from './research-workspace/ResearchDocumentWorkbench'
import { FoundationPage } from './foundation/FoundationPage'
import { AppHomePage } from './home/AppHomePage'
import {
  PhenomenonWorkspace,
  ResearchWorkspaceShell,
} from '../modules/socio-match-workspace'
import { PageContent, PageShell } from './ui/PageShell'
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
    <PageShell workspace defaultRailCollapsed>
      <PageContent>
        <KnowledgeExplorerPage
          state={state}
          onStateChange={updateState}
          onReleaseResolved={resolveRelease}
          onOpenEntry={(knowledgeId) => {
            saveKnowledgeListScroll(state, window.scrollY)
            const query = writeKnowledgeUrlState(state).toString()
            navigate(`/knowledge/${encodeURIComponent(knowledgeId)}${query ? `?${query}` : ''}`)
          }}
          onLocateEntry={(entry) => {
            setFocusEntry(entry)
            setGraphOpen(true)
          }}
          onOpenGraph={() => setGraphOpen(true)}
        />
        {state.releaseId ? (
          <>
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

function KnowledgeEntryRoute() {
  const { knowledge_id: knowledgeId } = useParams<{ knowledge_id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = readKnowledgeUrlState(searchParams)
  const graphReturnTo = readKnowledgeGraphReturnTo(searchParams)
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
    <PageShell workspace defaultRailCollapsed>
      <PageContent>
        <KnowledgeEntryPage
          knowledgeId={knowledgeId}
          releaseId={state.releaseId}
          onReleaseResolved={resolveRelease}
          onReturnToResearch={state.returnTo ? () => navigate(state.returnTo) : undefined}
          onReturnToKnowledge={() => {
            if (graphReturnTo) {
              navigate(graphReturnTo)
              return
            }
            const query = writeKnowledgeUrlState({ ...state, returnTo: undefined }).toString()
            navigate(`/knowledge${query ? `?${query}` : ''}`)
          }}
          returnToKnowledgeLabel={graphReturnTo ? '返回知识图谱' : '返回知识库'}
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

function KnowledgeGraphRoute() {
  const [searchParams, setSearchParams] = useSearchParams()
  const state: FullscreenKnowledgeGraphState = {
    releaseId: searchParams.get('knowledge_release_id') ?? undefined,
    query: searchParams.get('query') ?? undefined,
    centerId: searchParams.get('center') ?? undefined,
    pendingEnabled: searchParams.get('pending') === '1',
  }
  const updateState = useCallback((changes: Partial<FullscreenKnowledgeGraphState>) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      const keys: Record<keyof FullscreenKnowledgeGraphState, string> = {
        releaseId: 'knowledge_release_id',
        query: 'query',
        centerId: 'center',
        pendingEnabled: 'pending',
      }
      for (const [stateKey, value] of Object.entries(changes)) {
        const queryKey = keys[stateKey as keyof FullscreenKnowledgeGraphState]
        if (stateKey === 'pendingEnabled') {
          if (value) next.set(queryKey, '1')
          else next.delete(queryKey)
        } else if (value) next.set(queryKey, String(value))
        else next.delete(queryKey)
      }
      return next
    })
  }, [setSearchParams])
  const entryHref = useCallback((knowledgeId: string) => {
    const returnTo = `/knowledge/graph?${searchParams.toString()}`
    const detailParams = new URLSearchParams({
      knowledge_release_id: state.releaseId ?? '',
      return_to: returnTo,
    })
    return `/knowledge/${encodeURIComponent(knowledgeId)}?${detailParams}`
  }, [searchParams, state.releaseId])
  return (
    <PageShell workspace>
      <FullscreenKnowledgeGraphPage
        state={state}
        onStateChange={updateState}
        entryHref={entryHref}
      />
    </PageShell>
  )
}

function loginRedirect(value: string | null) {
  if (!value?.startsWith('/')) return '/app'

  const origin = 'https://qunxue.local'
  try {
    const target = new URL(value, origin)
    return target.origin === origin
      ? `${target.pathname}${target.search}${target.hash}`
      : '/app'
  } catch {
    return '/app'
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
    <PageShell immersive>
      <LoginPage
        onLogin={account.login}
        onAuthenticated={() => navigate(destination, { replace: true })}
        registerHref={`/register?redirect=${encodeURIComponent(destination)}`}
        sessionExpired={sessionState.status === 'expired'}
      />
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
    <PageShell immersive>
      <RegisterPage
        onRegister={account.register}
        onAuthenticated={() => navigate(destination, { replace: true })}
        loginHref={`/login?redirect=${encodeURIComponent(destination)}`}
      />
    </PageShell>
  )
}

function MyResearchRoute() {
  return (
    <PageShell wide>
      <PageContent>
        <section className="research-library">
          <header className="research-library__header">
            <h1>我的研究</h1>
            <a href="/research/new">新建研究</a>
          </header>
          <div className="research-library__toolbar">
            <nav aria-label="研究库视图">
              <span aria-current="page">全部研究</span>
            </nav>
          </div>
          <section className="research-library__content" aria-label="研究任务列表">
            <MyResearchPage />
          </section>
        </section>
      </PageContent>
    </PageShell>
  )
}

function NewResearchRoute() {
  return <NewResearchWorkspacePage />
}

function PhenomenonRoute() {
  const { task_id: taskId } = useParams<{ task_id: string }>()
  return (
    <PageShell wide>
      <ResearchWorkspaceShell
        currentStage="phenomenon"
        eyebrow="研究任务"
        title="确认现象"
        lede="核对系统整理的表述、语境与依据。确认后会形成可恢复的现象快照。"
        taskLabel={taskId ? `任务 ${taskId.slice(0, 8)}` : undefined}
        context={(
          <>
            <p>当前步骤说明</p>
            <h2>判断仍然属于你</h2>
            <p>候选只是对输入的整理，不是已经成立的研究结论。确认前可以直接修改。</p>
            <ul>
              <li>检查研究对象与变化是否准确</li>
              <li>确认依据能回到原始输入</li>
              <li>缺失信息不会被系统自动补成事实</li>
            </ul>
          </>
        )}
      >
        {taskId ? <PhenomenonWorkspace taskId={taskId} /> : <ErrorState detail="研究任务地址无效。" />}
      </ResearchWorkspaceShell>
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
  const productHome = (
    <FoundationPage authenticated={resolvedSessionState.status === 'authenticated'} />
  )

  return (
    <Routes>
      <Route
        path="/"
        element={resolvedSessionState.status === 'authenticated'
          ? <Navigate replace to="/app" />
          : productHome}
      />
      <Route path="/welcome" element={productHome} />
      <Route path="/app" element={protectedRoute(<AppHomePage />)} />
      <Route path="/agent" element={protectedRoute(<ResearchAgentPage />)} />
      <Route path="/knowledge" element={<KnowledgeExplorerRoute />} />
      <Route path="/knowledge/graph" element={<KnowledgeGraphRoute />} />
      <Route path="/knowledge/:knowledge_id" element={<KnowledgeEntryRoute />} />
      <Route path="/research/new" element={protectedRoute(<NewResearchRoute />)} />
      <Route path="/research/:task_id/phenomenon" element={protectedRoute(<PhenomenonRoute />)} />
      <Route path="/research/:task_id/match" element={protectedRoute(<ResearchDocumentWorkbench />)} />
      <Route path="/research/:task_id/framework" element={protectedRoute(<ResearchDocumentWorkbench />)} />
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
