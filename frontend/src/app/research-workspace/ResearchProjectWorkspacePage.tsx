import {
  ChartBarIcon,
  FileTextIcon,
  FolderOpenIcon,
  MapTrifoldIcon,
  ScalesIcon,
  WrenchIcon,
} from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'

import { readResearchTaskNavigationViaApi } from '../../api/researchWorkspace'
import type { AgentConversation } from '../../modules/research-agent'
import { ResearchMaterialsPanel } from '../../modules/research-materials'
import { MethodPlanWorkspace } from '../../modules/research-method'
import { useResearchTask, type ResearchTask } from '../../modules/socio-match-workspace'
import { ResearchAgentConversationPage } from '../agent/ResearchAgentConversationPage'
import { PageContent, PageShell } from '../ui/PageShell'
import { ErrorState, LoadingState } from '../ui/States'
import { ResearchDocumentWorkbench, type ResearchDocumentWorkspaceContext } from './ResearchDocumentWorkbench'
import {
  readResearchWorkspaceResumePath,
  rememberResearchWorkspaceResumePath,
  researchWorkspaceDestination,
  researchWorkspaceToolFromProject,
  type ResearchWorkspacePosition,
  type ResearchWorkspaceTool,
} from './researchProjectWorkspaceModel'
import './research-project-workspace.css'

const MIN_AGENT_WIDTH = 320
const MAX_AGENT_WIDTH = 680
const DEFAULT_AGENT_WIDTH = 430

const tools: ReadonlyArray<{
  id: ResearchWorkspaceTool
  label: string
  icon: typeof MapTrifoldIcon
}> = [
  { id: 'map', label: '地图', icon: MapTrifoldIcon },
  { id: 'materials', label: '材料', icon: FolderOpenIcon },
  { id: 'analysis', label: '分析', icon: ChartBarIcon },
  { id: 'theory', label: '理论', icon: ScalesIcon },
  { id: 'method', label: '方法', icon: WrenchIcon },
  { id: 'writing', label: '文稿', icon: FileTextIcon },
]

const toolIds = new Set(tools.map((tool) => tool.id))

type ResearchProjectWorkspacePageProps = {
  readonly userId?: string | null
}

function clampAgentWidth(value: number) {
  return Math.round(Math.min(MAX_AGENT_WIDTH, Math.max(MIN_AGENT_WIDTH, value)))
}

function readAgentWidth(taskId: string) {
  try {
    const stored = Number(window.localStorage.getItem(`qunxue.research-workspace.agent-width.v1:${taskId}`))
    return Number.isFinite(stored) && stored > 0 ? clampAgentWidth(stored) : DEFAULT_AGENT_WIDTH
  } catch {
    return DEFAULT_AGENT_WIDTH
  }
}

function projectTitle(task: ResearchTask, navigation: Awaited<ReturnType<typeof readResearchTaskNavigationViaApi>>) {
  return task.projectTitle?.trim()
    || navigation.phenomenon_summary?.phenomenon?.trim()
    || '未命名研究'
}

export function ResearchProjectWorkspacePage({ userId = null }: ResearchProjectWorkspacePageProps) {
  const { task_id: taskId = '', tool: toolParam } = useParams<{ task_id: string; tool?: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const task = useResearchTask(taskId)
  const navigation = useQuery({
    queryKey: ['research-project-navigation', taskId],
    queryFn: () => readResearchTaskNavigationViaApi(taskId),
    enabled: Boolean(taskId),
    refetchOnWindowFocus: false,
    retry: false,
  })
  const [agentConversation, setAgentConversation] = useState<AgentConversation | null>(null)
  const [documentContext, setDocumentContext] = useState<ResearchDocumentWorkspaceContext | null>(null)
  const [centerRefreshKey, setCenterRefreshKey] = useState(0)
  const [agentWidth, setAgentWidth] = useState(() => readAgentWidth(taskId))
  const resizePointer = useRef<number | null>(null)
  const layoutRef = useRef<HTMLDivElement | null>(null)

  const tool = toolIds.has(toolParam as ResearchWorkspaceTool)
    ? toolParam as ResearchWorkspaceTool
    : null

  useEffect(() => {
    if (!taskId || !tool) return
    rememberResearchWorkspaceResumePath(taskId, `${location.pathname}${location.search}${location.hash}`)
  }, [location.hash, location.pathname, location.search, taskId, tool])

  useEffect(() => {
    setDocumentContext(null)
  }, [tool])

  const resizeAgent = useCallback((clientX: number) => {
    const bounds = layoutRef.current?.getBoundingClientRect()
    if (!bounds?.width) return
    setAgentWidth(clampAgentWidth(Math.min(bounds.width - 360, bounds.right - clientX)))
  }, [])

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    event.preventDefault()
    resizePointer.current = event.pointerId
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  function finishResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (resizePointer.current !== event.pointerId) return
    resizePointer.current = null
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    try {
      window.localStorage.setItem(`qunxue.research-workspace.agent-width.v1:${taskId}`, String(agentWidth))
    } catch {
      // The current layout remains usable when storage is unavailable.
    }
  }

  function moveResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (resizePointer.current === event.pointerId) resizeAgent(event.clientX)
  }

  function handleResizeKey(event: React.KeyboardEvent<HTMLDivElement>) {
    const next = event.key === 'ArrowLeft' ? agentWidth + 24
      : event.key === 'ArrowRight' ? agentWidth - 24
        : event.key === 'Home' ? MIN_AGENT_WIDTH
          : event.key === 'End' ? MAX_AGENT_WIDTH
            : null
    if (next == null) return
    event.preventDefault()
    const width = clampAgentWidth(next)
    setAgentWidth(width)
    try {
      window.localStorage.setItem(`qunxue.research-workspace.agent-width.v1:${taskId}`, String(width))
    } catch {
      // Keyboard resizing remains available for this session.
    }
  }

  const updateMaterialLocation = useCallback((next: {
    mode: 'source' | 'analysis'
    materialId: string | null
    parseId: string | null
    segmentId: string | null
  }) => {
    const destination = researchWorkspaceDestination(taskId, next.mode === 'analysis' ? 'analysis' : 'materials', next)
    if (`${location.pathname}${location.search}` !== destination) navigate(destination, { replace: true })
  }, [location.pathname, location.search, navigate, taskId])

  const updateDocumentLocation = useCallback((next: ResearchDocumentWorkspaceContext) => {
    setDocumentContext((current) => current
      && current.mode === next.mode
      && current.documentId === next.documentId
      && current.sectionId === next.sectionId
      && current.documentVersion === next.documentVersion
      && current.theoryPlanId === next.theoryPlanId
      ? current
      : next)
    const nextTool = next.mode === 'framework' ? 'writing' : tool === 'map' ? 'map' : 'theory'
    const destination = researchWorkspaceDestination(taskId, nextTool, {
      documentId: next.documentId,
      sectionId: next.sectionId,
      version: next.documentVersion,
    })
    if (`${location.pathname}${location.search}` !== destination) navigate(destination, { replace: true })
  }, [location.pathname, location.search, navigate, taskId, tool])

  if (!taskId) return <ErrorState detail="研究项目地址无效。" />
  if (task.isPending || navigation.isPending) return <LoadingState message="正在恢复研究项目" />
  if (task.isError || navigation.isError || !task.data || !navigation.data) {
    return <ErrorState
      title="研究项目暂时无法打开"
      detail="项目内容仍然保留，请稍后重试。"
      onRetry={() => { void Promise.all([task.refetch(), navigation.refetch()]) }}
    />
  }
  if (!tool) {
    const restored = readResearchWorkspaceResumePath(taskId)
    const destination = restored
      ?? researchWorkspaceDestination(
        taskId,
        researchWorkspaceToolFromProject(task.data.lastCentralTool),
      )
    return <Navigate replace to={destination} />
  }

  const taskData = task.data
  const navigationData = navigation.data
  const position: ResearchWorkspacePosition = {
    materialId: searchParams.get('material_id'),
    parseId: searchParams.get('parse_id'),
    segmentId: searchParams.get('segment_id'),
    documentId: searchParams.get('document_id'),
    sectionId: searchParams.get('section_id'),
    version: searchParams.get('version') !== null && Number.isFinite(Number(searchParams.get('version')))
      ? Number(searchParams.get('version'))
      : null,
  }

  const center = tool === 'materials' || tool === 'analysis'
    ? (
        <ResearchMaterialsPanel
          key={`${taskId}:${tool}`}
          taskId={taskId}
          presentation="workspace"
          initialDetailMode={tool === 'analysis' ? 'analysis' : 'source'}
          initialMaterialId={position.materialId ?? null}
          initialParseId={position.parseId ?? null}
          initialSegmentId={position.segmentId ?? null}
          analysisRefreshKey={centerRefreshKey}
          onWorkspaceLocationChange={updateMaterialLocation}
        />
      )
    : tool === 'method'
      ? <MethodPlanWorkspace taskId={taskId} />
      : (
          <ResearchDocumentWorkbench
            embedded
            userId={userId}
            workspaceMode={tool === 'writing' ? 'framework' : 'match'}
            focusDocument={tool !== 'map'}
            initialDocumentId={position.documentId ?? null}
            initialSectionId={position.sectionId ?? null}
            conversation={agentConversation}
            refreshKey={centerRefreshKey}
            onWorkspaceContextChange={updateDocumentLocation}
          />
        )

  return (
    <PageShell workspace wide>
      <PageContent>
        <main className="research-project-workspace" aria-label="研究项目工作区">
          <header className="research-project-workspace__header">
            <div className="research-project-workspace__identity">
              <Link to="/app?research=all">全部研究</Link>
              <div>
                <span>{taskData.entryMode === 'existing_research' ? '已有研究' : '研究项目'}</span>
                <h1>{projectTitle(taskData, navigationData)}</h1>
              </div>
              <p>{[taskData.projectStage, taskData.methodOrientation].filter(Boolean).join(' · ') || navigationData.stage_label}</p>
            </div>
            <nav className="research-project-workspace__tools" aria-label="研究中心工具">
              {tools.map(({ id, label, icon: Icon }) => (
                <Link
                  key={id}
                  to={researchWorkspaceDestination(taskId, id)}
                  aria-current={tool === id ? 'page' : undefined}
                >
                  <Icon size={16} aria-hidden="true" />
                  <span>{label}</span>
                </Link>
              ))}
            </nav>
          </header>

          <div
            ref={layoutRef}
            className="research-project-workspace__layout"
            style={{ '--research-agent-width': `${agentWidth}px` } as CSSProperties}
          >
            <section className="research-project-workspace__center" aria-label="中心工具区">
              {center}
            </section>
            <div
              className="research-project-workspace__separator"
              role="separator"
              tabIndex={0}
              aria-label="调整 Agent 对话栏宽度"
              aria-orientation="vertical"
              aria-valuemin={MIN_AGENT_WIDTH}
              aria-valuemax={MAX_AGENT_WIDTH}
              aria-valuenow={agentWidth}
              onKeyDown={handleResizeKey}
              onPointerDown={startResize}
              onPointerMove={moveResize}
              onPointerUp={finishResize}
              onPointerCancel={finishResize}
            />
            <div className="research-project-workspace__agent">
              <ResearchAgentConversationPage
                embedded
                userId={userId}
                conversationId={navigationData.conversation_id}
                knowledgeReleaseId={navigationData.knowledge_release_id}
                workspace="research"
                taskId={taskId}
                documentId={documentContext?.documentId ?? null}
                sectionId={documentContext?.sectionId ?? null}
                documentVersion={documentContext?.documentVersion ?? null}
                theoryPlanId={navigationData.current_theory_plan_id}
                onConversationChange={setAgentConversation}
                onTurnCompleted={() => setCenterRefreshKey((value) => value + 1)}
                composerAriaLabel={`和 Agent 讨论当前${tools.find((item) => item.id === tool)?.label ?? '研究'}`}
              />
            </div>
          </div>
        </main>
      </PageContent>
    </PageShell>
  )
}
