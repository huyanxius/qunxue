import {
  ArrowUpIcon,
  CaretRightIcon,
  CheckIcon,
  CircleNotchIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import {
  confirmResearchStartProposal,
  getResearchStartJourney,
  type AgentConversation,
  type ResearchStartJourney,
  type ResearchStartProposal,
} from '../../modules/research-agent'
import {
  projectResearchCanvas,
  type ResearchCanvasProjection,
  type ResearchCanvasStreamingTurn,
} from '../../modules/research-workspace'
import { ResearchMapCanvas } from '../research-workspace/ResearchMapCanvas'
import { PageContent, PageShell } from '../ui/PageShell'
import { ResearchAgentConversationPage } from './ResearchAgentConversationPage'
import './new-research-workspace.css'

const AGENT_PANEL_WIDTH_STORAGE_KEY = 'qunxue.research.agent-panel-width'
const DEFAULT_AGENT_PANEL_WIDTH = 430
const MIN_AGENT_PANEL_WIDTH = 320
const MAX_AGENT_PANEL_WIDTH = 680
const MIN_RESEARCH_CANVAS_WIDTH = 360
const AGENT_PANEL_KEYBOARD_STEP = 24

function clampAgentPanelWidth(width: number, maxWidth = MAX_AGENT_PANEL_WIDTH) {
  return Math.round(Math.min(Math.max(width, MIN_AGENT_PANEL_WIDTH), Math.max(MIN_AGENT_PANEL_WIDTH, maxWidth)))
}

function readStoredAgentPanelWidth() {
  if (typeof window === 'undefined') return DEFAULT_AGENT_PANEL_WIDTH
  try {
    const width = Number(window.localStorage.getItem(AGENT_PANEL_WIDTH_STORAGE_KEY))
    return Number.isFinite(width) && width > 0 ? clampAgentPanelWidth(width) : DEFAULT_AGENT_PANEL_WIDTH
  } catch {
    return DEFAULT_AGENT_PANEL_WIDTH
  }
}

function persistAgentPanelWidth(width: number) {
  try {
    window.localStorage.setItem(AGENT_PANEL_WIDTH_STORAGE_KEY, String(Math.round(width)))
  } catch {
    // The resize remains available for this session when storage is disabled.
  }
}

function ResearchStartProposalCard({
  proposal,
  busy,
  error,
  onConfirm,
  onContinue,
}: {
  proposal: ResearchStartProposal
  busy: boolean
  error: string | null
  onConfirm: () => void
  onContinue: () => void
}) {
  return (
    <section className="new-research__start-proposal" aria-label="研究建立确认" aria-busy={busy}>
      <header><span>建立研究</span><strong>请确认 Agent 理解的研究起点</strong></header>
      <dl>
        <div><dt>现象</dt><dd>{proposal.phenomenon}</dd></div>
        <div><dt>意图</dt><dd>{proposal.researchIntent || '还需要通过对话补充研究意图'}</dd></div>
        <div><dt>情境</dt><dd>{proposal.context || '还需要通过对话补充具体情境'}</dd></div>
      </dl>
      {error ? <p className="new-research__start-error" role="alert"><WarningCircleIcon size={14} />{error}</p> : null}
      <div className="new-research__start-actions">
        <button type="button" className={`is-primary${busy ? ' is-loading' : ''}`} disabled={busy} onClick={onConfirm}>
          {busy ? <><CircleNotchIcon size={14} />正在建立研究…</> : <>{error ? '重试建立研究' : '确认研究起点'}<ArrowUpIcon size={14} /></>}
        </button>
        <button type="button" disabled={busy} onClick={onContinue}>{error ? '返回继续修改' : '继续修改'}</button>
      </div>
    </section>
  )
}

function ResearchStartReadyCard({ journey, onEnter }: { journey: ResearchStartJourney; onEnter: () => void }) {
  return (
    <section className="new-research__start-ready" aria-label="研究已建立">
      <span className="new-research__start-ready-mark"><CheckIcon size={15} weight="bold" /></span>
      <div>
        <small>研究已建立 · 画布梳理中</small>
        <strong>{journey.proposal?.phenomenon || '当前研究问题'}</strong>
        <p>继续在左侧整理问题、现象、理论与证据；确认结构清楚后，再展开文档节点。</p>
      </div>
      <button type="button" onClick={onEnter}>展开文档节点 <CaretRightIcon size={14} /></button>
    </section>
  )
}

function ResearchStartRecoveryError({ message, busy, onRetry, onContinue }: {
  message: string
  busy: boolean
  onRetry: () => void
  onContinue: () => void
}) {
  return (
    <section className="new-research__start-recovery" role="alert" aria-label="研究状态恢复失败">
      <div><WarningCircleIcon size={15} /><strong>研究状态暂时无法恢复</strong></div>
      <p><span>对话已保留</span>。{message}</p>
      <div className="new-research__start-actions">
        <button type="button" className={`is-primary${busy ? ' is-loading' : ''}`} disabled={busy} onClick={onRetry}>
          {busy ? <><CircleNotchIcon size={14} />正在恢复…</> : '重试恢复研究状态'}
        </button>
        <button type="button" disabled={busy} onClick={onContinue}>返回继续对话</button>
      </div>
    </section>
  )
}

export function NewResearchWorkspacePage({ userId }: { userId: string | null }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedConversationId = searchParams.get('conversation_id')
  const requestedKnowledgeReleaseId = searchParams.get('knowledge_release_id')
  const [conversation, setConversation] = useState<AgentConversation | null>(null)
  const [streamingTurn, setStreamingTurn] = useState<ResearchCanvasStreamingTurn | null>(null)
  const [journey, setJourney] = useState<ResearchStartJourney | null>(null)
  const [journeyLoading, setJourneyLoading] = useState(false)
  const [journeyError, setJourneyError] = useState<string | null>(null)
  const [journeyConfirming, setJourneyConfirming] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [suggestedPrompt, setSuggestedPrompt] = useState<string | null>(null)
  const [suggestedPromptKey, setSuggestedPromptKey] = useState(0)
  const [historyRailTarget, setHistoryRailTarget] = useState<HTMLDivElement | null>(null)
  const journeyAbortController = useRef<AbortController | null>(null)
  const workspaceRef = useRef<HTMLDivElement>(null)
  const activeResizePointer = useRef<number | null>(null)
  const mouseResizeCleanup = useRef<(() => void) | null>(null)
  const panelWidthRef = useRef(readStoredAgentPanelWidth())
  const [agentPanelWidth, setAgentPanelWidth] = useState(panelWidthRef.current)
  const [agentPanelMaxWidth, setAgentPanelMaxWidth] = useState(MAX_AGENT_PANEL_WIDTH)
  const [resizingAgentPanel, setResizingAgentPanel] = useState(false)

  const projection = useMemo<ResearchCanvasProjection>(() => {
    const projected = projectResearchCanvas({ conversation, streamingTurn })
    const phenomenon = journey?.proposal?.phenomenon
    if (!phenomenon || projected.nodes.some((node) => node.kind === 'phenomenon')) return projected
    const phenomenonId = `research-phenomenon:${journey?.taskId ?? journey?.proposal?.proposalId ?? 'draft'}`
    const question = projected.nodes.find((node) => node.kind === 'question')
    return {
      ...projected,
      nodes: [...projected.nodes, {
        id: phenomenonId,
        kind: 'phenomenon',
        title: phenomenon,
        summary: journey?.proposal?.researchIntent || '等待你确认的核心研究现象。',
        excerpt: journey?.proposal?.context || null,
        status: journey.taskId ? 'grounded' : 'developing',
        provenance: 'user',
        citationIds: [],
      }],
      edges: question ? [...projected.edges, { id: `research-phenomenon-edge:${question.id}`, source: question.id, target: phenomenonId, relation: 'refines', label: '聚焦现象' }] : projected.edges,
    }
  }, [conversation, journey, streamingTurn])

  const loadJourney = useCallback(async (conversationId: string) => {
    journeyAbortController.current?.abort()
    const controller = new AbortController()
    journeyAbortController.current = controller
    setJourneyLoading(true)
    setJourneyError(null)
    try {
      const nextJourney = await getResearchStartJourney(conversationId, controller.signal)
      if (!controller.signal.aborted) setJourney(nextJourney)
    } catch (cause: unknown) {
      if (!controller.signal.aborted && (cause as { name?: string } | null)?.name !== 'AbortError') {
        setJourneyError('研究建立状态暂时无法恢复。对话已保留，请稍后重试。')
      }
    } finally {
      if (!controller.signal.aborted) setJourneyLoading(false)
    }
  }, [])

  const syncConversation = useCallback((nextConversation: AgentConversation) => {
    setConversation(nextConversation)
    const releaseId = [...nextConversation.turns].reverse().map((turn) => turn.knowledge_release_id?.trim()).find(Boolean) ?? null
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('conversation_id', nextConversation.conversation_id)
      if (releaseId) next.set('knowledge_release_id', releaseId)
      return next
    }, { replace: true })
    void loadJourney(nextConversation.conversation_id)
  }, [loadJourney, setSearchParams])

  useEffect(() => () => journeyAbortController.current?.abort(), [])
  useEffect(() => () => mouseResizeCleanup.current?.(), [])

  async function confirmResearchStart() {
    const proposal = journey?.proposal
    if (!proposal || proposal.status !== 'pending_confirmation' || journeyConfirming) return
    setJourneyConfirming(true)
    setJourneyError(null)
    try {
      const confirmed = await confirmResearchStartProposal({
        proposalId: proposal.proposalId,
        expectedVersion: proposal.version,
        phenomenon: proposal.phenomenon,
        researchIntent: proposal.researchIntent,
        context: proposal.context,
        idempotencyKey: `research-start:${proposal.proposalId}`,
      })
      setJourney(confirmed)
    } catch (cause: unknown) {
      const detail = cause instanceof Error ? cause.message : ''
      setJourneyError(`研究暂时未能建立，你的内容已保留。${detail ? ` ${detail}` : ''}`)
    } finally {
      setJourneyConfirming(false)
    }
  }

  function enterDocumentResearch() {
    const resumePath = journey?.taskId ? journey.resumePath?.trim() : ''
    if (!resumePath) {
      setJourneyError('研究已建立，但下一阶段暂时无法打开。请稍后重试恢复研究状态。')
      return
    }
    navigate(resumePath)
  }

  function continueNode(node: ResearchCanvasProjection['nodes'][number]) {
    setSelectedNodeId(node.id)
    const subject = (node.excerpt || node.title).slice(0, 800)
    const prompt = node.kind === 'question'
      ? `请继续拆解这个研究问题：${node.title}`
      : node.kind === 'phenomenon'
        ? `请继续澄清这个核心现象的边界、对象和情境：${subject}`
        : node.kind === 'theory'
          ? `请检验这个理论视角如何解释当前问题，并指出它的边界：${subject}`
          : node.kind === 'claim'
            ? `请为这个主张补充真实证据，并检查可能的反例：${subject}`
            : node.kind === 'evidence'
              ? `请说明这条证据支持或质疑哪些主张，并更新研究结构：${subject}`
              : node.kind === 'gap'
                ? `请优先补齐这个证据缺口；需要时调用知识库工具：${subject}`
                : `请从这个节点中找出最脆弱的推理，并继续推进：${subject}`
    setSuggestedPrompt(prompt)
    setSuggestedPromptKey((current) => current + 1)
  }

  const availableAgentPanelWidth = useCallback(() => {
    const workspaceWidth = workspaceRef.current?.getBoundingClientRect().width || window.innerWidth
    return Math.max(MIN_AGENT_PANEL_WIDTH, Math.min(MAX_AGENT_PANEL_WIDTH, workspaceWidth - MIN_RESEARCH_CANVAS_WIDTH))
  }, [])

  const updateAgentPanelWidth = useCallback((width: number, persist = false) => {
    const nextWidth = clampAgentPanelWidth(width, availableAgentPanelWidth())
    panelWidthRef.current = nextWidth
    setAgentPanelWidth(nextWidth)
    if (persist) persistAgentPanelWidth(nextWidth)
  }, [availableAgentPanelWidth])

  const resizeFromClientX = useCallback((clientX: number) => {
    const workspace = workspaceRef.current?.getBoundingClientRect()
    if (workspace?.width) updateAgentPanelWidth(workspace.right - clientX)
  }, [updateAgentPanelWidth])

  useEffect(() => {
    const workspace = workspaceRef.current
    if (!workspace) return
    const syncBounds = () => {
      const maxWidth = availableAgentPanelWidth()
      setAgentPanelMaxWidth(maxWidth)
      updateAgentPanelWidth(panelWidthRef.current)
    }
    syncBounds()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', syncBounds)
      return () => window.removeEventListener('resize', syncBounds)
    }
    const observer = new ResizeObserver(syncBounds)
    observer.observe(workspace)
    return () => observer.disconnect()
  }, [availableAgentPanelWidth, updateAgentPanelWidth])

  function startPointerResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    activeResizePointer.current = event.pointerId
    event.currentTarget.setPointerCapture?.(event.pointerId)
    setResizingAgentPanel(true)
  }
  function movePointerResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (activeResizePointer.current === event.pointerId) resizeFromClientX(event.clientX)
  }
  function finishPointerResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (activeResizePointer.current !== event.pointerId) return
    activeResizePointer.current = null
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    setResizingAgentPanel(false)
    persistAgentPanelWidth(panelWidthRef.current)
  }
  function startMouseResize(event: ReactMouseEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    const targetWindow = event.currentTarget.ownerDocument.defaultView
    if (!targetWindow) return
    setResizingAgentPanel(true)
    const move = (moveEvent: MouseEvent) => resizeFromClientX(moveEvent.clientX)
    const finish = () => {
      setResizingAgentPanel(false)
      persistAgentPanelWidth(panelWidthRef.current)
      targetWindow.removeEventListener('mousemove', move)
      targetWindow.removeEventListener('mouseup', finish)
      mouseResizeCleanup.current = null
    }
    mouseResizeCleanup.current = finish
    targetWindow.addEventListener('mousemove', move)
    targetWindow.addEventListener('mouseup', finish)
  }
  function handleResizeKey(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? AGENT_PANEL_KEYBOARD_STEP * 2 : AGENT_PANEL_KEYBOARD_STEP
    const next = event.key === 'ArrowLeft' ? agentPanelWidth + step
      : event.key === 'ArrowRight' ? agentPanelWidth - step
        : event.key === 'Home' ? MIN_AGENT_PANEL_WIDTH
          : event.key === 'End' ? agentPanelMaxWidth
            : null
    if (next === null) return
    event.preventDefault()
    updateAgentPanelWidth(next, true)
  }

  const journeyTail = journey?.taskId ? (
    <ResearchStartReadyCard journey={journey} onEnter={enterDocumentResearch} />
  ) : journey?.proposal?.status === 'pending_confirmation' ? (
    <ResearchStartProposalCard
      proposal={journey.proposal}
      busy={journeyConfirming}
      error={journeyError}
      onConfirm={() => { void confirmResearchStart() }}
      onContinue={() => setJourneyError(null)}
    />
  ) : journeyError ? (
    <ResearchStartRecoveryError
      message={journeyError}
      busy={journeyLoading}
      onRetry={() => { if (conversation?.conversation_id) void loadJourney(conversation.conversation_id) }}
      onContinue={() => setJourneyError(null)}
    />
  ) : journeyLoading ? <p className="new-research__start-loading" role="status"><CircleNotchIcon size={14} />正在恢复研究建立状态…</p> : null

  return (
    <PageShell workspace wide railContentRef={setHistoryRailTarget}>
      <PageContent>
        <section className="new-research" aria-label="新建研究工作区">
          <div ref={workspaceRef} className="new-research__workspace" data-resizing={resizingAgentPanel} style={{ '--new-research-agent-width': `${agentPanelWidth}px` } as CSSProperties}>
            <div className="new-research__map-column">
              <ResearchMapCanvas
                projection={projection}
                selectedNodeId={selectedNodeId}
                onSelectNode={(node) => setSelectedNodeId(node.id)}
                onClearSelection={() => setSelectedNodeId(null)}
                onContinueNode={continueNode}
              />
            </div>
            <div
              className="new-research__resize-handle"
              role="separator"
              tabIndex={0}
              aria-label="调整对话栏宽度"
              aria-orientation="vertical"
              aria-controls="research-agent-panel"
              aria-valuemin={MIN_AGENT_PANEL_WIDTH}
              aria-valuemax={agentPanelMaxWidth}
              aria-valuenow={agentPanelWidth}
              aria-valuetext={`${agentPanelWidth} 像素`}
              onKeyDown={handleResizeKey}
              onMouseDown={startMouseResize}
              onPointerDown={startPointerResize}
              onPointerMove={movePointerResize}
              onPointerUp={finishPointerResize}
              onPointerCancel={finishPointerResize}
            />
            <ResearchAgentConversationPage
              embedded
              showConversationManagement
              historyRailTarget={historyRailTarget}
              userId={userId}
              conversationId={requestedConversationId}
              knowledgeReleaseId={requestedKnowledgeReleaseId}
              workspace="research"
              composerAriaLabel="和 Agent 讨论你的研究"
              suggestedPrompt={suggestedPrompt}
              suggestedPromptKey={suggestedPromptKey}
              onConversationChange={syncConversation}
              onStreamingTurnChange={setStreamingTurn}
              conversationTail={journeyTail}
            />
          </div>
        </section>
      </PageContent>
    </PageShell>
  )
}
