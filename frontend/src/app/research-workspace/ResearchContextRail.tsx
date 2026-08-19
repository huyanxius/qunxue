import { CheckCircleIcon, CircleNotchIcon, FileTextIcon, MagnifyingGlassIcon, WarningCircleIcon, XIcon } from '@phosphor-icons/react'
import { useId, useRef, useState, type ReactNode, type KeyboardEvent } from 'react'

import type { AgentCitation, AgentToolStep } from '../../modules/research-agent'
import './research-context-rail.css'

export type ResearchActivityResult = {
  id: string
  title: string
  excerpt?: string | null
}

export type ResearchActivity = {
  id: string
  tool: string
  label: string
  status: AgentToolStep['status']
  interrupted?: boolean
  input?: unknown
  detail?: string | null
  resultItems?: ResearchActivityResult[]
}

export type ResearchCitation = {
  id: string
  title: string
  kind: string
  subtitle?: string | null
  excerpt?: string | null
  knowledgeId?: string | null
}

export type ResearchContextTab = 'agent' | 'activity' | 'sources' | 'basis'

type ResearchContextRailProps = {
  readonly activeTab?: ResearchContextTab
  readonly activities?: readonly ResearchActivity[]
  readonly citations?: readonly ResearchCitation[]
  readonly basisContent?: ReactNode
  readonly selectedCitationId?: string | null
  readonly onClose?: () => void
  readonly onPanelChange?: (tab: ResearchContextTab) => void
  readonly onActivitySelect?: (activity: ResearchActivity) => void
  readonly onCitationSelect?: (citation: ResearchCitation) => void
}

const tabs: readonly { id: ResearchContextTab; label: string }[] = [
  { id: 'agent', label: 'Agent' },
  { id: 'activity', label: 'Activity' },
  { id: 'sources', label: 'Sources' },
  { id: 'basis', label: 'Basis' },
]

const toolLabel = (tool: string) => tool.replaceAll('_', ' ')

const TOOL_DETAIL_PREVIEW_LIMIT = 180

export function summarizeToolDetail(detail: string | null | undefined) {
  const normalized = detail?.trim() ?? ''
  if (!normalized) return { preview: '', truncated: false }
  if (normalized.length <= TOOL_DETAIL_PREVIEW_LIMIT) return { preview: normalized, truncated: false }
  return {
    preview: `${normalized.slice(0, TOOL_DETAIL_PREVIEW_LIMIT).trimEnd()}…`,
    truncated: true,
  }
}

export function ToolDetailDisclosure({ detail, className = '', showPreview = true }: { detail: string; className?: string; showPreview?: boolean }) {
  const { preview, truncated } = summarizeToolDetail(detail)
  if (!preview || (!truncated && !showPreview)) return null
  return (
    <div className={`research-tool-detail ${className}`.trim()}>
      {showPreview ? <p className="research-tool-detail__preview">{preview}</p> : null}
      {truncated ? (
        <details>
          <summary role="button">查看完整工具返回</summary>
          <pre>{detail.trim()}</pre>
        </details>
      ) : null}
    </div>
  )
}

function payloadLabel(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(payloadLabel).filter(Boolean).join(' · ') || null
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const valueLabel = payloadLabel(item)
        return valueLabel ? `${key}: ${valueLabel}` : null
      })
      .filter(Boolean)
      .join(' · ') || null
  }
  return null
}

function ActivityStatus({ status, interrupted }: { status: ResearchActivity['status']; interrupted?: boolean }) {
  if (interrupted) return <WarningCircleIcon className="research-context-rail__status research-context-rail__status--interrupted" size={16} aria-label="已中断" />
  if (status === 'running') return <CircleNotchIcon className="research-context-rail__status research-context-rail__status--running" size={16} aria-label="进行中" />
  if (status === 'failed') return <span className="research-context-rail__status research-context-rail__status--failed" aria-label="失败">!</span>
  return <CheckCircleIcon className="research-context-rail__status research-context-rail__status--done" size={16} aria-label="已完成" />
}

function ActivityPanel({ activities, onSelect }: { activities: readonly ResearchActivity[]; onSelect?: (activity: ResearchActivity) => void }) {
  if (!activities.length) {
    return <div className="research-context-rail__empty"><MagnifyingGlassIcon size={20} /><strong>还没有活动</strong><p>当 Agent 需要检索或整理证据时，过程会显示在这里。</p></div>
  }
  return (
    <div className="research-context-rail__activity-list">
      {activities.map((activity) => (
        <article className={`research-context-rail__activity research-context-rail__activity--${activity.interrupted ? 'interrupted' : activity.status}`} key={activity.id}>
          <button type="button" className="research-context-rail__activity-button" onClick={() => onSelect?.(activity)} aria-label={activity.label}>
            <ActivityStatus status={activity.status} interrupted={activity.interrupted} />
            <span className="research-context-rail__activity-copy"><strong>{activity.label}</strong><small>{activity.detail ? summarizeToolDetail(activity.detail).preview : toolLabel(activity.tool)}</small></span>
            <span className="research-context-rail__activity-state">{activity.interrupted ? '已中断' : activity.status === 'running' ? '进行中' : activity.status === 'failed' ? '失败' : '完成'}</span>
          </button>
          {activity.detail ? <ToolDetailDisclosure detail={activity.detail} showPreview={false} /> : null}
          {activity.input ? <p className="research-context-rail__activity-input">{payloadLabel(activity.input)}</p> : null}
          {activity.resultItems?.length ? (
            <div className="research-context-rail__result-list">
              {activity.resultItems.map((item) => <button type="button" key={item.id} onClick={() => onSelect?.(activity)}><FileTextIcon size={14} /><span><strong>{item.title}</strong>{item.excerpt ? <small>{item.excerpt}</small> : null}</span></button>)}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  )
}

function SourcesPanel({ citations, selectedCitationId, onSelect }: { citations: readonly ResearchCitation[]; selectedCitationId?: string | null; onSelect?: (citation: ResearchCitation) => void }) {
  if (!citations.length) return <div className="research-context-rail__empty"><FileTextIcon size={20} /><strong>回答完成后，来源会出现在这里</strong><p>当本次回答绑定知识库来源时，来源会和回答保持对应。</p></div>
  return <div className="research-context-rail__source-list">{citations.map((citation) => <button type="button" className="research-context-rail__source" data-citation-id={citation.id} aria-current={citation.id === selectedCitationId ? 'true' : undefined} key={citation.id} onClick={() => onSelect?.(citation)}><span className="research-context-rail__source-index">{citations.indexOf(citation) + 1}</span><span><strong>{citation.title}</strong>{citation.subtitle ? <small>{citation.subtitle}</small> : null}{citation.excerpt ? <em>{citation.excerpt}</em> : null}</span></button>)}</div>
}

export function ResearchContextRail({ activeTab: controlledTab, activities = [], citations = [], basisContent, selectedCitationId, onClose, onPanelChange, onActivitySelect, onCitationSelect }: ResearchContextRailProps) {
  const [uncontrolledTab, setUncontrolledTab] = useState<ResearchContextTab>('agent')
  const tab = controlledTab ?? uncontrolledTab
  const tablistId = useId()
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])

  function selectTab(nextTab: ResearchContextTab) {
    if (!controlledTab) setUncontrolledTab(nextTab)
    onPanelChange?.(nextTab)
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!offset) return
    event.preventDefault()
    const nextIndex = (index + offset + tabs.length) % tabs.length
    const nextTab = tabs[nextIndex].id
    selectTab(nextTab)
    tabRefs.current[nextIndex]?.focus()
  }

  return (
    <aside className="research-context-rail" aria-label="研究上下文栏">
      <header className="research-context-rail__header"><div><span>研究上下文</span><strong>{tabs.find((item) => item.id === tab)?.label}</strong></div><button type="button" aria-label="关闭上下文栏" onClick={onClose}><XIcon size={17} /></button></header>
      <div className="research-context-rail__tabs" role="tablist" aria-label="研究上下文选项" id={tablistId}>
        {tabs.map((item, index) => <button key={item.id} ref={(element) => { tabRefs.current[index] = element }} className={item.id === tab ? 'is-active' : ''} role="tab" aria-selected={item.id === tab} aria-controls={`${tablistId}-${item.id}`} tabIndex={item.id === tab ? 0 : -1} type="button" onClick={() => selectTab(item.id)} onKeyDown={(event) => handleTabKeyDown(event, index)}>{item.label}{item.id === 'activity' && activities.some((activity) => activity.status === 'running') ? <span className="research-context-rail__tab-dot" aria-label="有活动进行中" /> : null}</button>)}
      </div>
      <div className="research-context-rail__body">
        <section className="research-context-rail__panel" role="tabpanel" id={`${tablistId}-${tab}`} aria-label={tabs.find((item) => item.id === tab)?.label} tabIndex={0}>
          {tab === 'agent' ? <div className="research-context-rail__agent-note"><span className="research-context-rail__agent-mark">Q</span><strong>群学 Agent</strong><p>自然语言是入口。需要证据时，我会把本次会话的检索过程和来源放在这里。</p></div> : null}
          {tab === 'activity' ? <ActivityPanel activities={activities} onSelect={onActivitySelect} /> : null}
          {tab === 'sources' ? <SourcesPanel citations={citations} selectedCitationId={selectedCitationId} onSelect={onCitationSelect} /> : null}
          {tab === 'basis' ? <div className="research-context-rail__basis">{basisContent ?? <div className="research-context-rail__empty"><FileTextIcon size={20} /><strong>选择一条来源</strong><p>选择一条来源后，这里会显示它的依据。</p></div>}</div> : null}
        </section>
      </div>
    </aside>
  )
}

export type { AgentCitation, AgentToolStep }
