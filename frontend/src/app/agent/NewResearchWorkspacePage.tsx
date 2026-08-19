import {
  ArrowClockwiseIcon,
  ArrowUpIcon,
  BookOpenTextIcon,
  ChatCircleDotsIcon,
  CircleNotchIcon,
  ClockCounterClockwiseIcon,
  CopyIcon,
  FileTextIcon,
  ListIcon,
  MagnifyingGlassIcon,
  MapTrifoldIcon,
  PlusIcon,
  SidebarSimpleIcon,
  StopIcon,
  WarningCircleIcon,
  XCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useLocation, useSearchParams } from 'react-router'

import { PageContent, PageShell } from '../ui/PageShell'
import { ResearchContextRail, ToolDetailDisclosure, type ResearchActivity, type ResearchCitation } from '../research-workspace/ResearchContextRail'
import { ResearchMapCanvas } from '../research-workspace/ResearchMapCanvas'
import {
  getAgentConversation,
  listAgentConversations,
  streamAgentTurn,
  type AgentCitation,
  type AgentConversation,
  type AgentConversationSummary,
  type AgentEvent,
  type AgentRuntimeMode,
  type AgentToolStep,
  type AgentToolTrace,
} from '../../modules/research-agent'
import {
  projectResearchCanvas,
  type ResearchCanvasProjection,
  type ResearchCanvasStreamingTurn,
} from '../../modules/research-workspace'
import './new-research-workspace.css'

const starterQuestions = [
  '怎么解释年轻人越来越孤独？',
  '平台算法如何改变年轻人的职业选择？',
  '一个社会现象背后可能有哪些机制？',
]
const MAX_AGENT_MESSAGE_LENGTH = 12000

const toolLabels: Record<string, string> = {
  search_knowledge: '检索知识库',
  read_knowledge_entry: '读取知识条目',
  read_sources: '读取来源',
  browse_knowledge_directory: '浏览知识目录',
}

type AgentPageStatus = 'idle' | 'loading' | 'thinking' | 'retrieving' | 'answering' | 'error'
type AgentToolEvent = Extract<AgentEvent, { type: 'tool_started' | 'tool_finished' | 'tool_failed' }>
type ResearchToolStep = AgentToolStep & { interrupted?: boolean }

const KNOWLEDGE_RELEASE_STORAGE_KEY = 'qunxue.research.knowledge-releases.v1'
const AGENT_RUNTIME_STORAGE_KEY = 'qunxue.research.agent-runtime.v1'
const knowledgeTools = new Set(['search_knowledge', 'read_knowledge_entry', 'read_sources', 'browse_knowledge_directory'])

function readStoredKnowledgeReleases(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.sessionStorage.getItem(KNOWLEDGE_RELEASE_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const entries = Object.entries(parsed as Record<string, unknown>)
      .filter((entry): entry is [string, string] => Boolean(entry[0]) && typeof entry[1] === 'string' && Boolean(entry[1].trim()))
      .slice(-100)
    return Object.fromEntries(entries)
  } catch {
    return {}
  }
}

function persistKnowledgeReleases(releases: Record<string, string>) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(KNOWLEDGE_RELEASE_STORAGE_KEY, JSON.stringify(releases))
  } catch {
    // Storage can be disabled by the browser; the URL/query state remains authoritative for this view.
  }
}

function readStoredAgentRuntimeModes(): Record<string, AgentRuntimeMode> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.sessionStorage.getItem(AGENT_RUNTIME_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const entries = Object.entries(parsed as Record<string, unknown>)
      .filter((entry): entry is [string, AgentRuntimeMode] => Boolean(entry[0]) && (entry[1] === 'mock' || entry[1] === 'base' || entry[1] === 'sft'))
      .slice(-100)
    return Object.fromEntries(entries)
  } catch {
    return {}
  }
}

function persistAgentRuntimeModes(modes: Record<string, AgentRuntimeMode>) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(AGENT_RUNTIME_STORAGE_KEY, JSON.stringify(modes))
  } catch {
    // The visible badge can fall back to the current SSE event when storage is unavailable.
  }
}

function runtimePresentation(mode: AgentRuntimeMode | null) {
  if (!mode) {
    return { label: '运行模式待确认', detail: '完成一次 Agent 回合后显示实际运行能力', tone: 'checking' }
  }
  if (mode === 'mock') {
    return { label: '预览 Agent', detail: '当前为可重复的预览提供方，不代表外部模型输出', tone: 'preview' }
  }
  if (mode === 'sft') {
    return { label: 'SFT 模型运行', detail: '回答由已配置的 SFT 模型提供', tone: 'model' }
  }
  return { label: '基础模型运行', detail: '回答由已配置的基础模型提供', tone: 'model' }
}

function formatToolPayload(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(formatToolPayload).filter(Boolean).join(' · ') || null
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const label = formatToolPayload(item)
        return label ? `${key}: ${label}` : null
      })
      .filter(Boolean)
      .join(' · ') || null
  }
  return null
}

function resultItemsFromOutput(output: unknown): ResearchActivity['resultItems'] {
  if (!output || typeof output !== 'object' || !Array.isArray((output as { items?: unknown }).items)) return []
  return ((output as { items: unknown[] }).items).flatMap((item, index) => {
    if (!item || typeof item !== 'object') return []
    const value = item as Record<string, unknown>
    const title = typeof value.title === 'string'
      ? value.title
      : typeof value.label === 'string'
        ? value.label
        : `结果 ${index + 1}`
    const excerpt = typeof value.excerpt === 'string'
      ? value.excerpt
      : typeof value.content === 'string'
        ? value.content
        : null
    const id = typeof value.knowledge_id === 'string'
      ? value.knowledge_id
      : typeof value.id === 'string'
        ? value.id
        : `${title}-${index}`
    return [{ id, title, excerpt }]
  })
}

function toActivity(step: ResearchToolStep): ResearchActivity {
  return {
    id: step.id,
    tool: step.tool,
    label: step.label,
    status: step.status,
    interrupted: step.interrupted,
    input: step.input,
    detail: step.detail,
    resultItems: resultItemsFromOutput(step.output),
  }
}

function updateToolSteps(steps: ResearchToolStep[], event: AgentToolEvent): ResearchToolStep[] {
  if (event.type === 'tool_started') {
    const id = event.call_id || `${event.tool}:${steps.filter((step) => step.tool === event.tool).length + 1}`
    const next: ResearchToolStep = {
      id,
      tool: event.tool,
      label: toolLabels[event.tool] || '调用学科工具',
      status: 'running',
      input: event.input,
      detail: event.detail,
    }
    const existing = steps.findIndex((step) => step.id === id)
    return existing < 0 ? [...steps, next] : steps.map((step, index) => index === existing ? next : step)
  }

  const index = event.call_id
    ? steps.findIndex((step) => step.id === event.call_id)
    : steps.findLastIndex((step) => step.tool === event.tool && step.status === 'running')
  const existing = index >= 0 ? steps[index] : undefined
  const next: ResearchToolStep = {
    id: existing?.id || event.call_id || `${event.tool}:${steps.length + 1}`,
    tool: event.tool,
    label: existing?.label || toolLabels[event.tool] || '调用学科工具',
    status: event.type === 'tool_failed' ? 'failed' : 'completed',
    input: existing?.input ?? (event.type === 'tool_failed' ? event.input : undefined),
    output: event.type === 'tool_finished' ? event.output : existing?.output,
    detail: event.type === 'tool_failed'
      ? event.detail || event.message
      : event.detail || formatToolPayload(event.output),
  }
  return index < 0 ? [...steps, next] : steps.map((step, stepIndex) => stepIndex === index ? next : step)
}

function persistedToolSteps(traces: AgentToolTrace[] | undefined): ResearchToolStep[] {
  let steps: ResearchToolStep[] = []
  for (const trace of traces ?? []) {
    const event: AgentToolEvent = trace.phase === 'started'
      ? { type: 'tool_started', tool: trace.tool, call_id: trace.call_id, input: trace.input ?? undefined, detail: trace.detail }
      : trace.phase === 'failed'
        ? {
            type: 'tool_failed',
            tool: trace.tool,
            call_id: trace.call_id,
            input: trace.input ?? undefined,
            message: trace.detail ?? '工具调用失败',
            error_code: trace.error ?? null,
            detail: trace.detail,
          }
        : { type: 'tool_finished', tool: trace.tool, call_id: trace.call_id, output: trace.output, detail: trace.detail }
    steps = updateToolSteps(steps, event)
  }
  return steps
}

function attachLocalToolSteps(conversation: AgentConversation, steps: ResearchToolStep[]): AgentConversation {
  if (!steps.length || !conversation.turns.length) return conversation
  const lastIndex = conversation.turns.length - 1
  const lastTurn = conversation.turns[lastIndex]
  const existingIds = new Set((lastTurn.tool_traces ?? []).map((trace) => trace.call_id))
  const localTraces: AgentToolTrace[] = steps
    .filter((step) => !existingIds.has(step.id))
    .map((step) => ({
      tool: step.tool,
      phase: step.status === 'failed' ? 'failed' : 'finished',
      call_id: step.id,
      input: step.input && typeof step.input === 'object' && !Array.isArray(step.input)
        ? step.input as Record<string, unknown>
        : null,
      output: step.output,
      detail: step.detail,
      error: step.status === 'failed' ? 'tool_failed' : null,
    }))
  if (!localTraces.length) return conversation
  return {
    ...conversation,
    turns: conversation.turns.map((turn, index) => index === lastIndex
      ? { ...turn, tool_traces: [...(turn.tool_traces ?? []), ...localTraces] }
      : turn),
  }
}

function statusLabel(status: AgentPageStatus, projection: ResearchCanvasProjection) {
  if (status === 'retrieving') return '正在整理知识库活动'
  if (status === 'answering') return 'Agent 正在生成'
  if (status === 'thinking') return 'Agent 正在理解问题'
  if (projection.status === 'ready') return '结构已更新'
  if (projection.status === 'failed') return '本轮需要重试'
  if (projection.status === 'interrupted') return '本轮已中断'
  return '知识库按需调用'
}

function displayAgentText(value: string) {
  return value.replace(/\[(?:citation_id:)?(?:knowledge|source):[A-Za-z0-9_.:-]+\]/g, '')
}

function citationToRail(citation: AgentCitation): ResearchCitation {
  return {
    id: citation.citation_id,
    title: citation.label,
    kind: citation.kind,
    subtitle: `${citationKindLabel(citation.kind)}${citation.knowledge_id ? ` · ${citation.knowledge_id}` : ''}`,
    excerpt: citation.excerpt,
    knowledgeId: citation.knowledge_id,
  }
}

function citationKindLabel(kind: string) {
  if (kind === 'preview') return '未审核预览'
  if (kind === 'entry') return '已核验条目'
  if (kind === 'source') return '来源'
  if (kind === 'theory') return '理论线索'
  if (kind === 'directory') return '知识目录'
  return '证据'
}

function interruptedSteps(steps: ResearchToolStep[]) {
  return steps.map((step) => step.status === 'running'
    ? { ...step, status: 'failed' as const, interrupted: true, detail: '已停止' }
    : step)
}

function hasKnowledgeActivity(steps: ResearchToolStep[]) {
  return steps.some((step) => knowledgeTools.has(step.tool))
}

function ToolTraceTimeline({ steps, onOpenActivity }: { steps: ResearchToolStep[]; onOpenActivity: () => void }) {
  if (!steps.length) return null
  const running = steps.some((step) => step.status === 'running')
  const interrupted = steps.some((step) => step.interrupted)
  const failed = steps.some((step) => step.status === 'failed' && !step.interrupted)
  return (
    <section className={`new-research__trace${running ? ' is-running' : ''}${failed ? ' is-failed' : ''}${interrupted ? ' is-interrupted' : ''}`} aria-label="Agent 工作过程">
      <header className="new-research__trace-header">
        <span className="new-research__trace-mark" aria-hidden="true">{interrupted ? <WarningCircleIcon size={14} /> : <CircleNotchIcon size={14} />}</span>
        <div><strong>{running ? 'Agent 正在调用工具' : interrupted ? '工具调用已中断' : failed ? '工具调用未完成' : 'Agent 已完成工具调用'}</strong><small>{steps.length} 个实际步骤 · 按需使用知识库</small></div>
        <button type="button" onClick={onOpenActivity}>查看活动</button>
      </header>
      <ol className="new-research__trace-list">
        {steps.map((step) => (
          <li key={step.id} className={`new-research__trace-step is-${step.interrupted ? 'interrupted' : step.status}`}>
            <span className="new-research__trace-dot" aria-hidden="true" />
            <div>
              <strong>{step.label}</strong>
              <small>{step.interrupted ? '已中断' : step.status === 'running' ? '进行中' : step.status === 'failed' ? '失败' : '已完成'}</small>
              {step.input ? <p>{formatToolPayload(step.input)}</p> : null}
              {step.detail ? <ToolDetailDisclosure detail={step.detail} className="new-research__trace-detail" /> : null}
              {resultItemsFromOutput(step.output).map((item) => (
                <span className="new-research__trace-result" key={item.id}><FileTextIcon size={13} /><b>{item.title}</b></span>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

function SourcePills({ citations, onSelect }: { citations: AgentCitation[]; onSelect: (citation: AgentCitation) => void }) {
  if (!citations.length) return null
  return (
    <div className="new-research__sources" aria-label="回答证据">
      <span className="new-research__sources-label"><BookOpenTextIcon size={14} />依据</span>
      {citations.map((citation, index) => (
        <button type="button" key={citation.citation_id} onClick={() => onSelect(citation)} aria-label={`查看证据：${citation.label}`}>
          <b>{index + 1}</b><span>{citation.label}<small>{citationKindLabel(citation.kind)}</small></span>
        </button>
      ))}
    </div>
  )
}

function AssistantActions({ content, onRegenerate }: { content: string; onRegenerate: () => void }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  async function copyAnswer() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard_unavailable')
      await navigator.clipboard.writeText(content)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
    window.setTimeout(() => setCopyState('idle'), 1600)
  }
  return (
    <div className="new-research__assistant-actions">
      <button type="button" aria-label="复制回答" onClick={() => { void copyAnswer() }}><CopyIcon size={14} />{copyState === 'copied' ? '已复制' : copyState === 'failed' ? '复制失败' : '复制'}</button>
      <button type="button" aria-label="重新生成" onClick={onRegenerate}><ArrowClockwiseIcon size={14} />重新生成</button>
    </div>
  )
}

function ConversationHistory({
  conversations,
  activeConversationId,
  loading,
  onOpen,
  onClose,
}: {
  conversations: AgentConversationSummary[]
  activeConversationId: string | null
  loading: boolean
  onOpen: (conversation: AgentConversationSummary) => void
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const filtered = conversations.filter((conversation) => conversation.title.toLowerCase().includes(query.trim().toLowerCase()))
  useEffect(() => {
    closeButtonRef.current?.focus()
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])
  return (
    <div className="new-research__history" role="dialog" aria-modal="true" aria-label="研究记录">
      <header><div><span>研究记录</span><strong>继续一个已有问题</strong></div><button ref={closeButtonRef} type="button" aria-label="关闭研究记录" onClick={onClose}><XIcon size={16} /></button></header>
      <label className="new-research__history-search"><MagnifyingGlassIcon size={15} /><input aria-label="搜索研究记录" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索问题" /></label>
      <div className="new-research__history-list">
        {loading ? <p role="status">正在加载研究记录…</p> : filtered.length ? filtered.map((conversation) => (
          <button type="button" key={conversation.conversation_id} aria-current={conversation.conversation_id === activeConversationId ? 'true' : undefined} onClick={() => onOpen(conversation)}>
            <span><strong>{conversation.title}</strong><small>{conversation.turn_count} 轮对话</small></span>
            <ClockCounterClockwiseIcon size={15} />
          </button>
        )) : <p>还没有保存的研究对话。</p>}
      </div>
    </div>
  )
}

function EmptyConversation({ onStarter }: { onStarter: (question: string) => void }) {
  return (
    <div className="new-research__empty-conversation">
      <div className="new-research__empty-mark"><ChatCircleDotsIcon size={22} /></div>
      <p className="new-research__eyebrow">对话驱动研究</p>
      <h1>从一个社会学问题开始</h1>
      <p className="new-research__empty-lede">把你正在观察的现象说出来。Agent 会判断何时需要知识库，并把本次会话返回的过程整理成一张可以继续追问的研究地图。</p>
      <div className="new-research__starter-label">你可以这样开始</div>
      <div className="new-research__starter-list">
        {starterQuestions.map((question) => <button type="button" key={question} onClick={() => onStarter(question)}>{question}<ArrowUpIcon size={14} /></button>)}
      </div>
    </div>
  )
}

function AssistantTurn({
  question,
  answer,
  citations,
  toolSteps,
  interrupted,
  failure,
  streaming,
  onOpenActivity,
  onSelectCitation,
  onRegenerate,
}: {
  question: string
  answer: string
  citations: AgentCitation[]
  toolSteps: ResearchToolStep[]
  interrupted?: boolean
  failure?: string
  streaming?: boolean
  onOpenActivity: () => void
  onSelectCitation: (citation: AgentCitation) => void
  onRegenerate?: () => void
}) {
  return (
    <article className={`new-research__turn${streaming ? ' is-streaming' : ''}`}>
      <div className="new-research__user-message"><span>{question}</span></div>
      <div className="new-research__assistant-message">
        <div className="new-research__assistant-label"><span><MapTrifoldIcon size={14} />群学 Agent</span>{streaming ? <em>实时生成</em> : null}</div>
        <ToolTraceTimeline steps={toolSteps} onOpenActivity={onOpenActivity} />
        {answer ? <div className="new-research__markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{displayAgentText(answer)}</ReactMarkdown></div> : null}
        {!answer && !interrupted && !failure ? <p className="new-research__thinking" role="status"><CircleNotchIcon size={14} />Agent 正在组织问题与证据…</p> : null}
        {interrupted ? <p className="new-research__turn-note is-interrupted"><WarningCircleIcon size={14} />本轮已停止，未保存未完成的回答。</p> : null}
        {failure ? <p className="new-research__turn-note is-failed"><XCircleIcon size={14} />{failure}</p> : null}
        {!streaming && answer && !citations.length ? <p className="new-research__provenance-note"><WarningCircleIcon size={14} />{hasKnowledgeActivity(toolSteps) ? '本轮调用过知识库，但未返回可展示的来源，请谨慎使用。' : '未调用知识库：这是基于 Agent 推理的工作假设，请要求检索或补充材料后再核验。'}</p> : null}
        <SourcePills citations={citations} onSelect={onSelectCitation} />
        {!streaming && answer && onRegenerate ? <AssistantActions content={answer} onRegenerate={onRegenerate} /> : null}
      </div>
    </article>
  )
}

export function NewResearchWorkspacePage() {
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedConversationId = searchParams.get('conversation_id')
  const requestedKnowledgeReleaseId = searchParams.get('knowledge_release_id')
  const seedTheoryName = (
    location.state && typeof location.state === 'object' && 'seedTheoryName' in location.state
      && typeof (location.state as { seedTheoryName?: unknown }).seedTheoryName === 'string'
      ? (location.state as { seedTheoryName: string }).seedTheoryName
      : undefined
  )
  const [draft, setDraft] = useState('')
  const [conversations, setConversations] = useState<AgentConversationSummary[]>([])
  const [activeConversation, setActiveConversation] = useState<AgentConversation | null>(null)
  const [knowledgeReleaseByConversationId, setKnowledgeReleaseByConversationId] = useState<Record<string, string>>(() => (
    requestedConversationId && requestedKnowledgeReleaseId
      ? { ...readStoredKnowledgeReleases(), [requestedConversationId]: requestedKnowledgeReleaseId }
      : readStoredKnowledgeReleases()
  ))
  const [agentRuntimeModeByConversationId, setAgentRuntimeModeByConversationId] = useState<Record<string, AgentRuntimeMode>>(() => readStoredAgentRuntimeModes())
  const [agentRuntimeMode, setAgentRuntimeMode] = useState<AgentRuntimeMode | null>(() => (
    requestedConversationId ? readStoredAgentRuntimeModes()[requestedConversationId] ?? null : null
  ))
  const [streamingTurn, setStreamingTurn] = useState<ResearchCanvasStreamingTurn | null>(null)
  const [toolStepsByTurnId, setToolStepsByTurnId] = useState<Record<string, ResearchToolStep[]>>({})
  const [status, setStatus] = useState<AgentPageStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [contextOpen, setContextOpen] = useState(false)
  const [contextTab, setContextTab] = useState<'agent' | 'activity' | 'sources' | 'basis'>('agent')
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const streamAbortController = useRef<AbortController | null>(null)
  const streamGeneration = useRef(0)
  const conversationLoadAbortController = useRef<AbortController | null>(null)
  const conversationLoadGeneration = useRef(0)
  const pendingToolSteps = useRef<ResearchToolStep[]>([])
  const loadedConversationId = useRef<string | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const composerInputRef = useRef<HTMLTextAreaElement>(null)

  const closeHistory = useCallback(() => setHistoryOpen(false), [])

  const rememberKnowledgeRelease = useCallback((conversationId: string, releaseId: string) => {
    if (!conversationId || !releaseId) return
    setKnowledgeReleaseByConversationId((current) => {
      const next = { ...current, [conversationId]: releaseId }
      persistKnowledgeReleases(next)
      return next
    })
  }, [])

  const rememberAgentRuntimeMode = useCallback((conversationId: string, mode: AgentRuntimeMode) => {
    if (!conversationId) return
    setAgentRuntimeModeByConversationId((current) => {
      const next = { ...current, [conversationId]: mode }
      persistAgentRuntimeModes(next)
      return next
    })
  }, [])

  const turns = activeConversation?.turns ?? []
  const isBusy = status === 'loading' || status === 'thinking' || status === 'retrieving' || status === 'answering'
  const canSubmit = draft.trim().length > 0 && !isBusy
  const projection = useMemo(() => projectResearchCanvas({ conversation: activeConversation, streamingTurn }), [activeConversation, streamingTurn])

  const loadConversation = useCallback(async (conversationId: string) => {
    if (loadedConversationId.current === conversationId && activeConversation?.conversation_id === conversationId) return
    conversationLoadAbortController.current?.abort()
    const controller = new AbortController()
    conversationLoadAbortController.current = controller
    const requestGeneration = conversationLoadGeneration.current + 1
    conversationLoadGeneration.current = requestGeneration
    setError(null)
    setStatus('loading')
    try {
      const conversation = await getAgentConversation(conversationId, controller.signal)
      if (controller.signal.aborted || requestGeneration !== conversationLoadGeneration.current) return
      const persistedConversationReleaseId = [...conversation.turns]
        .reverse()
        .map((turn) => turn.knowledge_release_id?.trim() || null)
        .find((releaseId): releaseId is string => Boolean(releaseId)) || null
      const releaseId = knowledgeReleaseByConversationId[conversationId]
        || (conversationId === requestedConversationId ? requestedKnowledgeReleaseId : null)
        || persistedConversationReleaseId
      setActiveConversation(conversation)
      setAgentRuntimeMode(agentRuntimeModeByConversationId[conversationId] ?? null)
      loadedConversationId.current = conversationId
      if (releaseId) {
        rememberKnowledgeRelease(conversationId, releaseId)
      }
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.set('conversation_id', conversationId)
        if (releaseId) next.set('knowledge_release_id', releaseId)
        else next.delete('knowledge_release_id')
        return next
      }, { replace: true })
    } catch {
      if (controller.signal.aborted || requestGeneration !== conversationLoadGeneration.current) return
      setError('这段研究记录暂时无法打开。你可以从一个新问题继续。')
    } finally {
      if (requestGeneration === conversationLoadGeneration.current && !controller.signal.aborted) setStatus('idle')
      if (conversationLoadAbortController.current === controller) conversationLoadAbortController.current = null
    }
  }, [activeConversation?.conversation_id, agentRuntimeModeByConversationId, knowledgeReleaseByConversationId, rememberKnowledgeRelease, requestedConversationId, requestedKnowledgeReleaseId, setSearchParams])

  useEffect(() => {
    const controller = new AbortController()
    listAgentConversations(controller.signal)
      .then((items) => setConversations(items))
      .catch((cause: unknown) => {
        if ((cause as { name?: string } | null)?.name === 'AbortError') return
        if (!controller.signal.aborted) setError('研究记录暂时无法加载，但你仍然可以开始新研究。')
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (requestedConversationId) void loadConversation(requestedConversationId)
  }, [loadConversation, requestedConversationId])

  useEffect(() => {
    const endpoint = transcriptEndRef.current
    if (endpoint && typeof endpoint.scrollIntoView === 'function') {
      endpoint.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [streamingTurn?.answer, turns.length])

  function cancelActiveStream() {
    streamGeneration.current += 1
    streamAbortController.current?.abort()
    streamAbortController.current = null
    pendingToolSteps.current = []
    setStreamingTurn(null)
  }

  function prepareConversationSwitch() {
    cancelActiveStream()
    conversationLoadAbortController.current?.abort()
    conversationLoadGeneration.current += 1
    loadedConversationId.current = null
    setActiveConversation(null)
    setAgentRuntimeMode(null)
    setToolStepsByTurnId({})
    setSelectedCitationId(null)
    setSelectedNodeId(null)
    setContextOpen(false)
    setContextTab('agent')
  }

  function openConversation(summary: AgentConversationSummary) {
    prepareConversationSwitch()
    setHistoryOpen(false)
    void loadConversation(summary.conversation_id)
  }

  function newConversation() {
    prepareConversationSwitch()
    setDraft('')
    setError(null)
    setStatus('idle')
    setHistoryOpen(false)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('conversation_id')
      next.delete('knowledge_release_id')
      return next
    }, { replace: true })
  }

  async function submitQuestion(rawQuestion: string) {
    const question = rawQuestion.trim()
    if (!question || isBusy) return
    setDraft('')
    setError(null)
    setStatus('thinking')
    pendingToolSteps.current = []
    setStreamingTurn({ question, answer: '', citations: [], toolSteps: [] })
    const abortController = new AbortController()
    const runGeneration = streamGeneration.current + 1
    streamGeneration.current = runGeneration
    streamAbortController.current = abortController
    try {
      await streamAgentTurn(
        {
          conversation_id: activeConversation?.conversation_id ?? null,
          message: question,
          idempotencyKey: globalThis.crypto?.randomUUID?.() ?? `research-${Date.now()}`,
        },
        (event: AgentEvent) => {
          if (streamGeneration.current !== runGeneration) return
          if (event.type === 'turn_started') {
            if (event.runtime_mode) {
              setAgentRuntimeMode(event.runtime_mode)
              rememberAgentRuntimeMode(event.conversation_id, event.runtime_mode)
            }
            setStatus('thinking')
          } else if (event.type === 'agent_status') {
            setStatus(event.status === 'answering' ? 'answering' : 'thinking')
          } else if (event.type === 'tool_started' || event.type === 'tool_finished' || event.type === 'tool_failed') {
            const next = updateToolSteps(pendingToolSteps.current, event)
            pendingToolSteps.current = next
            setStatus(event.type === 'tool_started' ? 'retrieving' : 'thinking')
            setStreamingTurn((current) => current ? { ...current, toolSteps: next } : current)
          } else if (event.type === 'assistant_delta') {
            setStatus('answering')
            setStreamingTurn((current) => current ? { ...current, answer: current.answer + event.delta } : current)
          } else if (event.type === 'citation_added') {
            setStreamingTurn((current) => current ? { ...current, citations: [...current.citations, event.citation] } : current)
          } else if (event.type === 'turn_completed') {
            const localToolSteps = pendingToolSteps.current
            const completedConversation = attachLocalToolSteps(event.conversation, localToolSteps)
            const completedTurn = completedConversation.turns.at(-1)
            const releaseId = event.knowledge_release_id.trim()
            if (releaseId) {
              rememberKnowledgeRelease(completedConversation.conversation_id, releaseId)
            }
            if (completedTurn && localToolSteps.length) {
              setToolStepsByTurnId((current) => ({ ...current, [completedTurn.turn_id]: localToolSteps }))
            }
            pendingToolSteps.current = []
            setActiveConversation(completedConversation)
            loadedConversationId.current = completedConversation.conversation_id
            setConversations((current) => [
              { conversation_id: completedConversation.conversation_id, title: completedConversation.title, updated_at: completedConversation.updated_at, turn_count: completedConversation.turn_count },
              ...current.filter((item) => item.conversation_id !== completedConversation.conversation_id),
            ])
            setStreamingTurn(null)
            setStatus('idle')
            setSearchParams((current) => {
              const next = new URLSearchParams(current)
              next.set('conversation_id', completedConversation.conversation_id)
              if (releaseId) next.set('knowledge_release_id', releaseId)
              return next
            }, { replace: true })
          } else if (event.type === 'turn_interrupted') {
            settleInterruptedTurn()
          } else if (event.type === 'turn_failed') {
            setStreamingTurn((current) => current ? { ...current, failure: event.message } : current)
            setError(event.message)
            setStatus('error')
          }
        },
        abortController.signal,
      )
    } catch (cause: unknown) {
      if (!abortController.signal.aborted && streamGeneration.current === runGeneration) {
        const causeMessage = cause instanceof Error ? cause.message : ''
        const message = causeMessage.includes('完成前中断')
          ? '连接在回答完成前中断。请重试，这一轮不会伪造回答。'
          : causeMessage && causeMessage !== 'Agent 暂时无法连接'
            ? causeMessage
            : 'Agent 暂时无法连接。请检查模型服务后重试，这一轮不会伪造回答。'
        setStreamingTurn((current) => current ? { ...current, failure: message } : current)
        setError(message)
        setStatus('error')
      }
    } finally {
      if (streamAbortController.current === abortController) streamAbortController.current = null
    }
  }

  function submitDraft() {
    void submitQuestion(draft)
  }

  function settleInterruptedTurn() {
    const next = interruptedSteps(pendingToolSteps.current)
    pendingToolSteps.current = next
    setStreamingTurn((current) => current ? { ...current, interrupted: true, toolSteps: next, failure: undefined } : current)
    setStatus('idle')
  }

  function stopGeneration() {
    streamGeneration.current += 1
    streamAbortController.current?.abort()
    streamAbortController.current = null
    settleInterruptedTurn()
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void submitDraft()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submitDraft()
    }
  }

  const activities = useMemo(() => {
    const values = [
      ...turns.flatMap((turn) => toolStepsByTurnId[turn.turn_id] ?? persistedToolSteps(turn.tool_traces)),
      ...(streamingTurn?.toolSteps ?? []),
    ]
    return [...new Map(values.map((step) => [step.id, step])).values()].map(toActivity)
  }, [streamingTurn?.toolSteps, toolStepsByTurnId, turns])

  const citations = useMemo(() => {
    const values = [...turns.flatMap((turn) => turn.assistant.citations), ...(streamingTurn?.citations ?? [])]
    return [...new Map(values.map((citation) => [citation.citation_id, citation])).values()]
  }, [streamingTurn?.citations, turns])

  const releaseByCitationId = useMemo(() => {
    const releases: Record<string, string> = {}
    for (const turn of turns) {
      const releaseId = turn.knowledge_release_id?.trim()
      if (!releaseId) continue
      for (const citation of turn.assistant.citations) {
        releases[citation.citation_id] = releaseId
      }
    }
    return releases
  }, [turns])

  const citationsForRail = useMemo(() => citations.map(citationToRail), [citations])
  const selectedCitation = citations.find((citation) => citation.citation_id === selectedCitationId)
  const title = activeConversation?.title || (seedTheoryName ? `围绕「${seedTheoryName}」展开研究` : '新的研究')
  const runtime = runtimePresentation(agentRuntimeMode)

  function knowledgeReleaseForConversation(conversationId: string) {
    return knowledgeReleaseByConversationId[conversationId]
      || (conversationId === requestedConversationId ? requestedKnowledgeReleaseId : null)
  }

  function knowledgeEntryHref(knowledgeId: string, pinnedReleaseId?: string | null): string | null {
    const conversationId = activeConversation?.conversation_id ?? ''
    const releaseId = pinnedReleaseId?.trim() || knowledgeReleaseForConversation(conversationId)
    if (!releaseId) return null
    const returnParams = new URLSearchParams({ conversation_id: conversationId })
    returnParams.set('knowledge_release_id', releaseId)
    const query = new URLSearchParams()
    query.set('knowledge_release_id', releaseId)
    query.set('return_to', `${location.pathname}?${returnParams.toString()}`)
    return `/knowledge/${encodeURIComponent(knowledgeId)}?${query.toString()}`
  }

  function renderKnowledgeEntryLink(citation: AgentCitation) {
    if (!citation.knowledge_id) return null
    const href = knowledgeEntryHref(citation.knowledge_id, releaseByCitationId[citation.citation_id])
    if (!href) return <span className="new-research__basis-note">当前回合的知识版本尚未确认，暂不提供跳转。</span>
    return <a href={href}>打开知识条目 <ArrowUpIcon size={13} /></a>
  }

  function openCitation(citation: AgentCitation) {
    setSelectedCitationId(citation.citation_id)
    setContextTab('sources')
    setContextOpen(true)
  }

  function openNode(node: ResearchCanvasProjection['nodes'][number]) {
    setSelectedNodeId(node.id)
    if (node.citationId) {
      const citation = citations.find((item) => item.citation_id === node.citationId)
      if (citation) openCitation(citation)
      return
    }
    if (node.kind === 'tool') {
      setContextTab('activity')
      setContextOpen(true)
      return
    }
    const subject = node.kind === 'question' ? node.title : (node.excerpt || node.title).slice(0, 800)
    setDraft(`请继续拆解这个研究问题：${subject}`)
    globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
  }

  return (
    <PageShell workspace wide defaultRailCollapsed>
      <PageContent>
        <section className="new-research" aria-label="新建研究工作区">
          <div className="new-research__workspace">
            <div className="new-research__map-column">
              <header className="new-research__workspace-bar">
                <div className="new-research__workspace-title"><span>研究工作区</span><strong>{title}</strong></div>
                <div className="new-research__workspace-actions">
                  <span className="new-research__workspace-note"><SidebarSimpleIcon size={14} />对话驱动画布</span>
                  <button type="button" aria-label="打开研究记录" onClick={() => setHistoryOpen(true)}><ListIcon size={16} />记录</button>
                  <button type="button" aria-label="开始新研究" onClick={newConversation}><PlusIcon size={16} />新研究</button>
                </div>
              </header>
              <ResearchMapCanvas projection={projection} selectedNodeId={selectedNodeId} onSelectNode={openNode} />
            </div>

            <aside className="new-research__agent-panel" aria-label="研究 Agent 对话栏">
              <header className="new-research__agent-header">
                <div className="new-research__agent-heading"><span className="new-research__agent-icon"><MapTrifoldIcon size={17} /></span><div><span>群学 Agent</span><strong>{title}</strong></div></div>
                <div className="new-research__agent-actions">
                  <button type="button" aria-label="查看活动" onClick={() => { setContextTab('activity'); setContextOpen(true) }}><CircleNotchIcon size={16} />{activities.length ? <i>{activities.length}</i> : null}</button>
                  <button type="button" aria-label="查看来源" onClick={() => { setContextTab('sources'); setContextOpen(true) }}><BookOpenTextIcon size={16} />{citations.length ? <i>{citations.length}</i> : null}</button>
                  <button type="button" aria-label="打开研究记录" onClick={() => setHistoryOpen(true)}><ClockCounterClockwiseIcon size={16} /></button>
                </div>
              </header>
              <div className="new-research__agent-status"><span className={`new-research__agent-status-dot is-${projection.status}`} /><span>{statusLabel(status, projection)}</span><em className={`is-${runtime.tone}`} title={runtime.detail} aria-label={`运行模式：${runtime.label}。${runtime.detail}`}>{runtime.label}</em></div>

              <main className="new-research__conversation" aria-label="研究对话内容" role="log">
                {!turns.length && !streamingTurn ? <EmptyConversation onStarter={setDraft} /> : (
                  <div className="new-research__transcript">
                    {turns.map((turn) => (
                      <AssistantTurn
                        key={turn.turn_id}
                        question={turn.user.content}
                        answer={turn.assistant.content}
                        citations={turn.assistant.citations}
                        toolSteps={toolStepsByTurnId[turn.turn_id] ?? persistedToolSteps(turn.tool_traces)}
                        onOpenActivity={() => { setContextTab('activity'); setContextOpen(true) }}
                        onSelectCitation={openCitation}
                        onRegenerate={() => { void submitQuestion(turn.user.content) }}
                      />
                    ))}
                    {streamingTurn ? (
                      <AssistantTurn
                        question={streamingTurn.question}
                        answer={streamingTurn.answer}
                        citations={streamingTurn.citations}
                        toolSteps={streamingTurn.toolSteps}
                        interrupted={streamingTurn.interrupted}
                        failure={streamingTurn.failure}
                        streaming
                        onOpenActivity={() => { setContextTab('activity'); setContextOpen(true) }}
                        onSelectCitation={openCitation}
                      />
                    ) : null}
                    <div ref={transcriptEndRef} />
                  </div>
                )}
              </main>

              <footer className="new-research__composer-dock">
                {error ? <div className="new-research__error" role="alert"><WarningCircleIcon size={16} /><span>{error}</span><button type="button" aria-label="关闭错误提示" onClick={() => setError(null)}><XIcon size={14} /></button></div> : null}
                <form onSubmit={handleSubmit} className="new-research__composer-form">
                  <div className="new-research__composer">
                    <textarea ref={composerInputRef} aria-label="和 Agent 讨论你的研究" disabled={isBusy} maxLength={MAX_AGENT_MESSAGE_LENGTH} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleKeyDown} placeholder="描述一个现象，或告诉 Agent 你想理解什么" rows={3} />
                    <div className="new-research__composer-footer"><span><BookOpenTextIcon size={13} />知识库按需调用 · Enter 发送 · Shift + Enter 换行</span><small className="new-research__composer-count">{draft.length}/{MAX_AGENT_MESSAGE_LENGTH}</small><button type={isBusy ? 'button' : 'submit'} aria-label={isBusy ? '停止生成' : '发送给研究 Agent'} className={isBusy ? 'is-stop' : ''} disabled={!isBusy && !canSubmit} onClick={isBusy ? stopGeneration : undefined}>{isBusy ? <StopIcon size={15} weight="fill" /> : <ArrowUpIcon size={18} />}</button></div>
                  </div>
                </form>
              </footer>
              {historyOpen ? <ConversationHistory conversations={conversations} activeConversationId={activeConversation?.conversation_id ?? null} loading={historyLoading} onOpen={openConversation} onClose={closeHistory} /> : null}
            </aside>
          </div>
          {contextOpen ? (
            <ResearchContextRail
              activeTab={contextTab}
              activities={activities}
              citations={citationsForRail}
              selectedCitationId={selectedCitationId}
              onClose={() => setContextOpen(false)}
              onPanelChange={setContextTab}
              onCitationSelect={(citation) => {
                setSelectedCitationId(citation.id)
                setContextTab('basis')
                setContextOpen(true)
              }}
              basisContent={selectedCitation ? <div className="new-research__basis"><span>当前证据 · {citationKindLabel(selectedCitation.kind)}</span><strong>{selectedCitation.label}</strong><p>{selectedCitation.excerpt || '本轮 Agent 没有返回可展开的证据摘录。'}</p>{renderKnowledgeEntryLink(selectedCitation)}</div> : undefined}
            />
          ) : null}
        </section>
      </PageContent>
    </PageShell>
  )
}
