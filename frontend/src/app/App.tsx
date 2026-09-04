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
  AccountSettingsPage,
  AdminUsersPage,
  LoginPage,
  PasswordResetPage,
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
import { ResearchTaskNavigationRoute } from './ResearchTaskNavigationRoute'
import { ResearchAgentPage } from './agent/ResearchAgentPage'
import { NewResearchWorkspacePage } from './agent/NewResearchWorkspacePage'
import { ExistingResearchEntryPage } from './research/ExistingResearchEntryPage'
import { ResearchMaterialsPage } from './research/ResearchMaterialsPage'
import { ResearchToolsPage } from './research-tools/ResearchToolsPage'
import { ResearchProjectWorkspacePage } from './research-workspace/ResearchProjectWorkspacePage'
import { legacyResearchWorkspaceDestination } from './research-workspace/researchProjectWorkspaceModel'
import { FoundationPage } from './foundation/FoundationPage'
import { AppHomePage } from './home/AppHomePage'
import { PageContent, PageShell, RailStateProvider } from './ui/PageShell'
import { ErrorState, LoadingState } from './ui/States'
import { RouteMotionSurface } from './route-motion'

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
        onSendRegistrationCode={account.sendRegistrationCode}
        onAuthenticated={() => navigate(destination, { replace: true })}
        loginHref={`/login?redirect=${encodeURIComponent(destination)}`}
      />
    </PageShell>
  )
}

function NewResearchRoute({ userId }: { userId: string | null }) {
  return <NewResearchWorkspacePage userId={userId} />
}

function AccountSettingsRoute() {
  const account = useAccount()
  const navigate = useNavigate()
  const returnToPublicHome = () => navigate('/', { replace: true, state: { loggedOut: true } })
  const leaveAccount = () => {
    void account.logout().then(() => {
      window.setTimeout(returnToPublicHome, 0)
    }).catch(() => {
      returnToPublicHome()
    })
  }
  return (
    <PageShell wide shader>
      <PageContent>
        <AccountSettingsPage
          onLogout={leaveAccount}
          onProfileUpdated={() => account.retrySession()}
          onSessionExpired={() => account.retrySession()}
          onAccountDeactivated={leaveAccount}
          onAccountDeleted={leaveAccount}
        />
      </PageContent>
    </PageShell>
  )
}

function AdminUsersRoute() {
  const navigate = useNavigate()
  return (
    <PageShell wide>
      <PageContent>
        <AdminUsersPage
          onForbidden={() => navigate('/settings', { replace: true })}
          onSessionExpired={() => navigate('/login?redirect=%2Fadmin%2Fusers', { replace: true })}
        />
      </PageContent>
    </PageShell>
  )
}

function PasswordResetRoute() {
  const { token = '' } = useParams<{ token: string }>()
  return (
    <PageShell immersive>
      <PasswordResetPage token={token} loginHref="/login" />
    </PageShell>
  )
}

function LegacyResearchWorkspaceRedirect() {
  const location = useLocation()
  const destination = legacyResearchWorkspaceDestination(
    `${location.pathname}${location.search}${location.hash}`,
  )
  return destination
    ? <Navigate replace to={destination} />
    : <ErrorState detail="研究工作区地址无效。" />
}

function ResearchMaterialsRoute({ userId }: { userId: string | null }) {
  const location = useLocation()
  const destination = legacyResearchWorkspaceDestination(
    `${location.pathname}${location.search}${location.hash}`,
  )
  return destination
    ? <Navigate replace to={destination} />
    : <ResearchMaterialsPage userId={userId} />
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
  const location = useLocation()
  const resolvedSessionState: SessionState = sessionState ?? account.sessionState
  const isLoggedOutNavigation = Boolean(
    location.state && typeof location.state === 'object' && 'loggedOut' in location.state,
  )
  const authenticatedUserId = account.sessionState.status === 'authenticated'
    ? account.sessionState.session.user.userId
    : null
  const protectedRoute = (element: ReactNode) => (
    <ProtectedRoute sessionState={resolvedSessionState}>{element}</ProtectedRoute>
  )
  const productHome = (
    <FoundationPage authenticated={resolvedSessionState.status === 'authenticated'} />
  )

  return (
    <RailStateProvider>
      <RouteMotionSurface>
        <Routes>
      <Route
        path="/"
        element={resolvedSessionState.status === 'authenticated' && !isLoggedOutNavigation
          ? <Navigate replace to="/app" />
          : productHome}
      />
      <Route path="/welcome" element={productHome} />
      <Route path="/app" element={protectedRoute(<AppHomePage />)} />
      <Route path="/agent" element={protectedRoute(<ResearchAgentPage userId={authenticatedUserId} />)} />
      <Route path="/knowledge" element={<KnowledgeExplorerRoute />} />
      <Route path="/knowledge/graph" element={<KnowledgeGraphRoute />} />
      <Route path="/knowledge/:knowledge_id" element={<KnowledgeEntryRoute />} />
      <Route path="/research/new" element={protectedRoute(<NewResearchRoute userId={authenticatedUserId} />)} />
      <Route path="/research/existing" element={protectedRoute(<ExistingResearchEntryPage />)} />
      <Route path="/research/tools" element={protectedRoute(<ResearchToolsPage />)} />
      <Route path="/research/materials" element={protectedRoute(<ResearchMaterialsRoute userId={authenticatedUserId} />)} />
      <Route
        path="/research/:task_id"
        element={protectedRoute(<ResearchTaskNavigationRoute>{null}</ResearchTaskNavigationRoute>)}
      />
      <Route
        path="/research/:task_id/workspace/:tool?"
        element={protectedRoute(<ResearchProjectWorkspacePage userId={authenticatedUserId} />)}
      />
      <Route
        path="/research/:task_id/phenomenon"
        element={protectedRoute(<LegacyResearchWorkspaceRedirect />)}
      />
      <Route
        path="/research/:task_id/match"
        element={protectedRoute(<LegacyResearchWorkspaceRedirect />)}
      />
      <Route
        path="/research/:task_id/framework"
        element={protectedRoute(<LegacyResearchWorkspaceRedirect />)}
      />
      <Route
        path="/research/:task_id/method"
        element={protectedRoute(<LegacyResearchWorkspaceRedirect />)}
      />
      <Route path="/login" element={<LoginRoute sessionState={resolvedSessionState} />} />
      <Route path="/register" element={<RegisterRoute sessionState={resolvedSessionState} />} />
      <Route path="/password-reset/:token" element={<PasswordResetRoute />} />
      <Route path="/my" element={protectedRoute(<Navigate replace to="/app?research=all" />)} />
      <Route path="/settings" element={protectedRoute(<AccountSettingsRoute />)} />
      <Route path="/admin/users" element={protectedRoute(<AdminUsersRoute />)} />
        </Routes>
      </RouteMotionSurface>
    </RailStateProvider>
  )
}

export function App() {
  return (
    <BrowserRouter useTransitions={false}>
      <AppRoutes />
    </BrowserRouter>
  )
}
