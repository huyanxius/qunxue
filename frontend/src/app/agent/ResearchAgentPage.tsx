import { ArrowSquareOutIcon, ArrowUpIcon, BookOpenTextIcon, CaretDownIcon, StopIcon, WarningCircleIcon } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { useNavigate } from 'react-router'

import { PageContent, PageShell } from '../ui/PageShell'
import {
  getAgentConversation,
  listAgentConversations,
  streamAgentTurn,
  type AgentCitation,
  type AgentConversation,
  type AgentConversationSummary,
  type AgentEvent,
  type AgentToolStep,
  type AgentToolTrace,
} from '../../modules/research-agent'
import './research-agent-page.css'

const starterQuestions = [
  '为什么同一社区里的互助正在减少？',
  '平台算法如何改变年轻人的职业选择？',
  '为什么越来越多人选择独居？',
]

type StreamingTurn = {
  question: string
  answer: string
  citations: AgentCitation[]
  toolSteps: AgentToolStep[]
  interrupted?: boolean
  failure?: string
}

type AgentToolEvent = Extract<AgentEvent, {
  type: 'tool_started' | 'tool_finished' | 'tool_failed'
}>

const toolLabels: Record<string, string> = {
  search_knowledge: '检索知识库',
  read_knowledge_entry: '读取知识条目',
  read_sources: '读取来源',
  browse_knowledge_directory: '浏览知识目录',
}

function AgentToolTrace({ live = false, steps }: { live?: boolean; steps: AgentToolStep[] }) {
  const hasRunningStep = steps.some((step) => step.status === 'running')
  const [expanded, setExpanded] = useState(live || hasRunningStep)

  useEffect(() => {
    if (hasRunningStep) setExpanded(true)
  }, [hasRunningStep])

  if (!steps.length) return null
  const failedCount = steps.filter((step) => step.status === 'failed').length
  const summary = hasRunningStep
    ? `正在使用 ${steps.length} 个工具`
    : failedCount > 0
      ? `有 ${failedCount} 个工具调用未完成`
      : `已使用 ${steps.length} 个工具`

  return (
    <section className="agent-tool-trace" aria-label="Agent 工作过程">
      <button
        aria-expanded={expanded}
        className="agent-tool-trace__summary"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        <span className={`agent-tool-trace__summary-dot${hasRunningStep ? ' agent-tool-trace__summary-dot--running' : ''}${failedCount ? ' agent-tool-trace__summary-dot--failed' : ''}`} aria-hidden="true" />
        <span>{summary}</span>
        <CaretDownIcon aria-hidden="true" className="agent-tool-trace__chevron" size={14} />
      </button>
      {expanded ? (
        <div aria-live={live ? 'polite' : 'off'} className="agent-tool-trace__steps">
          {steps.map((step) => {
            const input = formatToolPayload(step.input)
            return (
              <div className={`agent-tool-trace__step agent-tool-trace__step--${step.status}`} key={step.id}>
                <div className="agent-tool-trace__step-heading">
                  <span className={`agent-tool-trace__dot${step.status === 'running' ? ' agent-tool-trace__dot--running' : ''}`} aria-hidden="true" />
                  <span className="agent-tool-trace__label">{step.label}</span>
                  <span className="agent-tool-trace__detail">
                    {step.status === 'running' ? '进行中' : step.status === 'failed' ? '未完成' : '已完成'}
                  </span>
                </div>
                {input ? (
                  <div className="agent-tool-trace__payload">
                    <span>输入</span>
                    <code>{input}</code>
                  </div>
                ) : null}
                {step.detail ? (
                  <p className={step.status === 'failed' ? 'agent-tool-trace__result agent-tool-trace__result--failed' : 'agent-tool-trace__result'}>
                    {step.detail}
                  </p>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

function updateToolSteps(steps: AgentToolStep[], event: AgentToolEvent): AgentToolStep[] {
  if (event.type === 'tool_started') {
    const id = event.call_id || `${event.tool}:${steps.filter((step) => step.tool === event.tool).length + 1}`
    const nextStep: AgentToolStep = {
      id,
      tool: event.tool,
      label: toolLabels[event.tool] || '调用学科工具',
      status: 'running',
      input: event.input,
      detail: event.detail,
    }
    const existingIndex = steps.findIndex((step) => step.id === id)
    return existingIndex < 0
      ? [...steps, nextStep]
      : steps.map((step, index) => index === existingIndex ? nextStep : step)
  }

  const matchingIndex = event.call_id
    ? steps.findIndex((step) => step.id === event.call_id)
    : steps.findLastIndex((step) => step.tool === event.tool && step.status === 'running')
  const existing = matchingIndex >= 0 ? steps[matchingIndex] : null
  const nextStep: AgentToolStep = {
    id: existing?.id || event.call_id || `${event.tool}:${steps.length + 1}`,
    tool: event.tool,
    label: existing?.label || toolLabels[event.tool] || '调用学科工具',
    status: event.type === 'tool_failed' ? 'failed' : 'completed',
    input: existing?.input,
    detail: event.type === 'tool_failed'
      ? event.detail || event.message
      : event.detail || formatToolPayload(event.output),
  }
  return matchingIndex < 0
    ? [...steps, nextStep]
    : steps.map((step, index) => index === matchingIndex ? nextStep : step)
}

function persistedToolSteps(traces: AgentToolTrace[] | undefined): AgentToolStep[] {
  let steps: AgentToolStep[] = []
  for (const trace of traces ?? []) {
    const event = trace.phase === 'started'
      ? {
          type: 'tool_started' as const,
          tool: trace.tool,
          call_id: trace.call_id,
          input: trace.input ?? undefined,
          detail: trace.detail,
        }
      : trace.phase === 'failed'
        ? {
            type: 'tool_failed' as const,
            tool: trace.tool,
            call_id: trace.call_id,
            input: trace.input ?? undefined,
            message: trace.detail ?? '工具调用失败',
            error_code: trace.error ?? null,
            detail: trace.detail,
          }
        : {
            type: 'tool_finished' as const,
            tool: trace.tool,
            call_id: trace.call_id,
            output: trace.output,
            detail: trace.detail,
          }
    steps = updateToolSteps(steps, event)
  }
  return steps
}

function formatToolPayload(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    const items = value.map(formatToolPayload).filter((item): item is string => Boolean(item))
    return items.length ? items.join('、') : null
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value)
      .map(([key, item]) => [key, formatToolPayload(item)] as const)
      .filter((entry): entry is readonly [string, string] => Boolean(entry[1]))
    if (entries.length === 1) return entries[0][1]
    return entries.length ? entries.map(([key, item]) => `${key}: ${item}`).join(' · ') : null
  }
  return null
}

function interruptRunningToolSteps(steps: AgentToolStep[]): AgentToolStep[] {
  return steps.map((step) => step.status === 'running'
    ? { ...step, status: 'failed', detail: '已停止' }
    : step)
}

function AgentConversationHistory({
  activeConversationId,
  conversations,
  loading,
  onOpen,
}: {
  activeConversationId: string | null
  conversations: AgentConversationSummary[]
  loading: boolean
  onOpen: (conversation: AgentConversationSummary) => void
}) {
  return (
    <section className="agent-conversation-history" aria-label="Agent 对话记录">
      <h2>对话记录</h2>
      {loading ? (
        <p role="status">正在加载记录…</p>
      ) : conversations.length > 0 ? (
        <div className="agent-conversation-history__list">
          {conversations.map((conversation) => (
            <button
              aria-current={conversation.conversation_id === activeConversationId ? 'true' : undefined}
              key={conversation.conversation_id}
              onClick={() => onOpen(conversation)}
              title={conversation.title}
              type="button"
            >
              <span>{conversation.title}</span>
              <span aria-hidden="true">···</span>
            </button>
          ))}
        </div>
      ) : (
        <p>发送第一条消息后会保存在这里</p>
      )}
    </section>
  )
}

function CitationCard({ citation, onOpen }: { citation: AgentCitation; onOpen: () => void }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <article className={`agent-citation${expanded ? ' agent-citation--expanded' : ''}`}>
      <button
        aria-expanded={expanded}
        className="agent-citation__toggle"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        <BookOpenTextIcon aria-hidden="true" size={16} weight="regular" />
        <span>
          <strong>{citation.label}</strong>
          <small>
            {citation.kind === 'source'
              ? '来源'
              : citation.kind === 'preview'
                ? '知识库预览 · 未审核'
                : '知识条目'}
          </small>
        </span>
        <CaretDownIcon aria-hidden="true" className="agent-citation__chevron" size={16} weight="regular" />
      </button>
      {expanded ? (
        <div className="agent-citation__detail">
          {citation.excerpt ? <p>{displayAgentText(citation.excerpt)}</p> : <p>当前回答引用了这条证据。</p>}
          {citation.knowledge_id ? (
            <button className="agent-citation__open" onClick={onOpen} type="button">
              打开知识条目
              <ArrowSquareOutIcon aria-hidden="true" size={14} weight="regular" />
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

export function ResearchAgentPage() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [conversations, setConversations] = useState<AgentConversationSummary[]>([])
  const [activeConversation, setActiveConversation] = useState<AgentConversation | null>(null)
  const [streamingTurn, setStreamingTurn] = useState<StreamingTurn | null>(null)
  const [toolStepsByTurnId, setToolStepsByTurnId] = useState<Record<string, AgentToolStep[]>>({})
  const [status, setStatus] = useState<'idle' | 'loading' | 'thinking' | 'retrieving' | 'answering' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const streamAbortController = useRef<AbortController | null>(null)
  const pendingToolSteps = useRef<AgentToolStep[]>([])

  useEffect(() => {
    const controller = new AbortController()
    listAgentConversations(controller.signal)
      .then((items) => {
        setConversations(items)
        setError(null)
      })
      .catch(() => setError('对话记录暂时无法加载。'))
      .finally(() => setHistoryLoading(false))
    return () => controller.abort()
  }, [])

  const isBusy = status === 'loading' || status === 'thinking' || status === 'retrieving' || status === 'answering'
  const canSubmit = draft.trim().length > 0 && !isBusy
  const turns = useMemo(() => activeConversation?.turns ?? [], [activeConversation])

  async function openConversation(summary: AgentConversationSummary) {
    setError(null)
    setStatus('loading')
    try {
      setActiveConversation(await getAgentConversation(summary.conversation_id))
    } catch {
      setError('这段对话暂时无法打开。')
    } finally {
      setStatus('idle')
    }
  }

  async function submitDraft() {
    const question = draft.trim()
    if (!question || isBusy) return

    setDraft('')
    setError(null)
    setStatus('thinking')
    pendingToolSteps.current = []
    setStreamingTurn({ question, answer: '', citations: [], toolSteps: [] })
    const idempotencyKey = globalThis.crypto?.randomUUID?.() ?? `agent-${Date.now()}`
    const abortController = new AbortController()
    streamAbortController.current = abortController

    try {
      await streamAgentTurn(
        {
          conversation_id: activeConversation?.conversation_id ?? null,
          message: question,
          idempotencyKey,
        },
        (event: AgentEvent) => {
          if (event.type === 'turn_started') {
            setStatus('thinking')
          } else if (event.type === 'agent_status') {
            setStatus(event.status === 'answering' ? 'answering' : 'thinking')
          } else if (event.type === 'tool_started' || event.type === 'tool_finished' || event.type === 'tool_failed') {
            const nextSteps = updateToolSteps(pendingToolSteps.current, event)
            pendingToolSteps.current = nextSteps
            setStatus(event.type === 'tool_started' ? 'retrieving' : 'thinking')
            setStreamingTurn((current) => current ? { ...current, toolSteps: nextSteps } : current)
          } else if (event.type === 'assistant_delta') {
            setStatus('answering')
            setStreamingTurn((current) => current ? { ...current, answer: current.answer + event.delta } : current)
          } else if (event.type === 'citation_added') {
            setStreamingTurn((current) => current ? { ...current, citations: [...current.citations, event.citation] } : current)
          } else if (event.type === 'turn_completed') {
            const completedTurn = event.conversation.turns[event.conversation.turns.length - 1]
            if (completedTurn && pendingToolSteps.current.length) {
              const completedSteps = pendingToolSteps.current
              setToolStepsByTurnId((current) => ({
                ...current,
                [completedTurn.turn_id]: completedSteps,
              }))
            }
            pendingToolSteps.current = []
            setActiveConversation(event.conversation)
            setConversations((current) => [
              {
                conversation_id: event.conversation.conversation_id,
                title: event.conversation.title,
                updated_at: event.conversation.updated_at,
                turn_count: event.conversation.turn_count,
              },
              ...current.filter((item) => item.conversation_id !== event.conversation.conversation_id),
            ])
            setStreamingTurn(null)
            setStatus('idle')
          } else if (event.type === 'turn_interrupted') {
            settleInterruptedTurn()
            setError(event.message)
          } else if (event.type === 'turn_failed') {
            setStreamingTurn((current) => current ? { ...current, failure: event.message } : current)
            setError(event.message)
            setStatus('error')
          }
        },
        abortController.signal,
      )
    } catch {
      if (abortController.signal.aborted) {
        setStatus('idle')
        return
      }
      setError('Agent 暂时无法连接，请稍后重试。')
      setStatus('error')
    } finally {
      if (streamAbortController.current === abortController) streamAbortController.current = null
    }
  }

  function stopGeneration() {
    streamAbortController.current?.abort()
    settleInterruptedTurn()
  }

  function settleInterruptedTurn() {
    const interruptedSteps = interruptRunningToolSteps(pendingToolSteps.current)
    pendingToolSteps.current = interruptedSteps
    setStreamingTurn((current) => current ? {
      ...current,
      interrupted: true,
      toolSteps: interruptedSteps,
    } : current)
    setStatus('idle')
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void submitDraft()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    void submitDraft()
  }

  return (
    <PageShell
      railContent={(
        <AgentConversationHistory
          activeConversationId={activeConversation?.conversation_id ?? null}
          conversations={conversations}
          loading={historyLoading}
          onOpen={openConversation}
        />
      )}
      wide
    >
      <PageContent>
        <section className="research-agent-page" aria-label="社会学 Agent 对话">
          {turns.length || streamingTurn ? (
            <header className="research-agent-page__conversation-heading">
              <p className="research-agent-page__conversation-label">学科对话</p>
            </header>
          ) : <div aria-hidden="true" className="research-agent-page__heading-placeholder" />}

          <main aria-label="对话内容" className="research-agent-page__scroll-region" role="log">
            {turns.length || streamingTurn ? (
              <div className="research-agent-page__transcript">
                {turns.map((turn) => (
                  <div className="research-agent-page__turn-group" key={turn.turn_id}>
                    <div className="agent-user-turn"><span>{turn.user.content}</span></div>
                    <div className="agent-assistant-turn">
                      <AgentToolTrace steps={toolStepsByTurnId[turn.turn_id] ?? persistedToolSteps(turn.tool_traces)} />
                      <div className="agent-markdown"><ReactMarkdown>{displayAgentText(turn.assistant.content)}</ReactMarkdown></div>
                      {turn.assistant.citations.length > 0 ? (
                        <div className="agent-citations">
                          {turn.assistant.citations.map((citation) => <CitationCard citation={citation} key={citation.citation_id} onOpen={() => openCitation(citation, navigate)} />)}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                {streamingTurn ? (
                  <div className="research-agent-page__turn-group research-agent-page__turn-group--streaming">
                    <div className="agent-user-turn"><span>{streamingTurn.question}</span></div>
                    <div className="agent-assistant-turn">
                      <AgentToolTrace live steps={streamingTurn.toolSteps} />
                      {streamingTurn.answer ? (
                        <div className="agent-markdown"><ReactMarkdown>{displayAgentText(streamingTurn.answer)}</ReactMarkdown></div>
                      ) : !streamingTurn.interrupted && !streamingTurn.failure ? (
                        <p className="agent-response-status" role="status">
                          <span aria-hidden="true" />
                          Agent 正在思考…
                        </p>
                      ) : null}
                      {streamingTurn.interrupted ? <p className="agent-turn-state">已停止生成</p> : null}
                      {streamingTurn.failure ? <p className="agent-turn-state agent-turn-state--error">{streamingTurn.failure}</p> : null}
                      {streamingTurn.citations.length > 0 ? (
                        <div className="agent-citations">
                          {streamingTurn.citations.map((citation) => <CitationCard citation={citation} key={citation.citation_id} onOpen={() => openCitation(citation, navigate)} />)}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="research-agent-page__empty-state">
                <div className="research-agent-page__empty-copy">
                  <p className="research-agent-page__eyebrow">社会学 Agent</p>
                  <h1 id="research-agent-title">你想研究什么？</h1>
                  <p className="research-agent-page__lede">和社会学 Agent 一起解释现象、梳理概念、打开思路。</p>
                </div>
                <div className="research-agent-page__starters" aria-label="问题示例">
                  <span>可以从这里开始</span>
                  <div>
                    {starterQuestions.map((question) => (
                      <button key={question} type="button" onClick={() => setDraft(question)}>{question}</button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </main>

          <footer className="research-agent-page__composer-dock">
            {error ? (
              <div className="agent-inline-error" role="alert">
                <WarningCircleIcon aria-hidden="true" size={16} />
                <span>{error}</span>
                <button type="button" onClick={() => setError(null)}>知道了</button>
              </div>
            ) : null}
            <form className="research-agent-page__form" onSubmit={handleSubmit}>
              <div className="research-agent-page__composer">
                <textarea
                  aria-label="问社会学 Agent"
                  disabled={isBusy}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="问一个问题，或描述你正在理解的现象"
                  rows={2}
                  value={draft}
                />
                <footer>
                  <span>{status === 'retrieving' ? '正在使用学科工具…' : status === 'answering' ? '正在生成回答…' : status === 'thinking' || status === 'loading' ? '正在准备回答…' : 'Enter 发送 · Shift + Enter 换行'}</span>
                  <button
                    aria-label={isBusy ? '停止生成' : '发送给社会学 Agent'}
                    className={`research-agent-page__send${isBusy ? ' research-agent-page__send--stop' : ''}`}
                    disabled={!isBusy && !canSubmit}
                    onClick={isBusy ? stopGeneration : undefined}
                    type={isBusy ? 'button' : 'submit'}
                  >
                    {isBusy ? <StopIcon aria-hidden="true" size={15} weight="fill" /> : <ArrowUpIcon aria-hidden="true" size={20} weight="regular" />}
                  </button>
                </footer>
              </div>
            </form>
          </footer>
        </section>
      </PageContent>
    </PageShell>
  )
}

function openCitation(citation: AgentCitation, navigate: ReturnType<typeof useNavigate>) {
  if (!citation.knowledge_id) return
  navigate(`/knowledge/${encodeURIComponent(citation.knowledge_id)}?return_to=%2Fagent`)
}

function displayAgentText(value: string) {
  const withoutInternalCitations = value.replace(
    /\[(?:citation_id:)?(?:knowledge|source):[A-Za-z0-9_.:-]+\]/g,
    '',
  )
  if (!withoutInternalCitations.includes('####') && !withoutInternalCitations.includes('> **')) {
    return withoutInternalCitations
  }
  return withoutInternalCitations
    .replace(/^\s*#{2,6}\s*/gm, '')
    .replace(/^\s*>\s*/gm, '')
    .replace(/\*\*/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
