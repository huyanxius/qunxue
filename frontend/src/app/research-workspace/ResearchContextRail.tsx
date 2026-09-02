import { CheckCircleIcon, CircleNotchIcon, FileTextIcon, MagnifyingGlassIcon, WarningCircleIcon, XIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import type { AgentCitation, AgentToolStep } from '../../modules/research-agent'
import { useAppLocale } from '../../i18n/AppLocaleProvider'
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

const tabLabels: Record<ResearchContextTab, string> = {
  agent: 'Agent',
  activity: '活动',
  sources: '来源',
  basis: '依据',
}

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
  const { text } = useAppLocale()
  const { preview, truncated } = summarizeToolDetail(detail)
  if (!preview || (!truncated && !showPreview)) return null
  return (
    <div className={`research-tool-detail ${className}`.trim()}>
      {showPreview ? <p className="research-tool-detail__preview">{preview}</p> : null}
      {truncated ? (
        <details>
          <summary role="button">{text('查看完整工具返回', 'View full tool output')}</summary>
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
  const { text } = useAppLocale()
  if (interrupted) return <WarningCircleIcon className="research-context-rail__status research-context-rail__status--interrupted" size={16} aria-label={text('已中断', 'Interrupted')} />
  if (status === 'running') return <CircleNotchIcon className="research-context-rail__status research-context-rail__status--running" size={16} aria-label={text('进行中', 'In progress')} />
  if (status === 'failed') return <span className="research-context-rail__status research-context-rail__status--failed" aria-label={text('失败', 'Failed')}>!</span>
  return <CheckCircleIcon className="research-context-rail__status research-context-rail__status--done" size={16} aria-label={text('已完成', 'Completed')} />
}

function ActivityPanel({ activities, onSelect }: { activities: readonly ResearchActivity[]; onSelect?: (activity: ResearchActivity) => void }) {
  const { text } = useAppLocale()
  if (!activities.length) {
    return <div className="research-context-rail__empty"><MagnifyingGlassIcon size={20} /><strong>{text('还没有活动', 'No activity yet')}</strong><p>{text('当 Agent 需要检索或整理证据时，过程会显示在这里。', 'When the Agent retrieves or organizes evidence, the process will appear here.')}</p></div>
  }
  return (
    <div className="research-context-rail__activity-list">
      {activities.map((activity) => (
        <article className={`research-context-rail__activity research-context-rail__activity--${activity.interrupted ? 'interrupted' : activity.status}`} key={activity.id}>
          <button type="button" className="research-context-rail__activity-button" onClick={() => onSelect?.(activity)} aria-label={activity.label}>
            <ActivityStatus status={activity.status} interrupted={activity.interrupted} />
            <span className="research-context-rail__activity-copy"><strong>{activity.label}</strong><small>{activity.detail ? summarizeToolDetail(activity.detail).preview : toolLabel(activity.tool)}</small></span>
            <span className="research-context-rail__activity-state">{activity.interrupted ? text('已中断', 'Interrupted') : activity.status === 'running' ? text('进行中', 'In progress') : activity.status === 'failed' ? text('失败', 'Failed') : text('完成', 'Completed')}</span>
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
  const { text } = useAppLocale()
  if (!citations.length) return <div className="research-context-rail__empty"><FileTextIcon size={20} /><strong>{text('回答完成后，来源会出现在这里', 'Sources will appear here when the answer is complete')}</strong><p>{text('当本次回答绑定知识库来源时，来源会和回答保持对应。', 'Knowledge sources stay linked to the answer that used them.')}</p></div>
  return <div className="research-context-rail__source-list">{citations.map((citation) => <button type="button" className="research-context-rail__source" data-citation-id={citation.id} aria-current={citation.id === selectedCitationId ? 'true' : undefined} key={citation.id} onClick={() => onSelect?.(citation)}><span className="research-context-rail__source-index">{citations.indexOf(citation) + 1}</span><span><strong>{citation.title}</strong>{citation.subtitle ? <small>{citation.subtitle}</small> : null}{citation.excerpt ? <em>{citation.excerpt}</em> : null}</span></button>)}</div>
}

export function ResearchContextRail({ activeTab: controlledTab, activities = [], citations = [], basisContent, selectedCitationId, onClose, onActivitySelect, onCitationSelect }: ResearchContextRailProps) {
  const { text } = useAppLocale()
  const tab = controlledTab ?? 'agent'
  return (
    <aside className="research-context-rail" aria-label={text('研究上下文栏', 'Research context panel')}>
      <header className="research-context-rail__header"><div><strong>{tabLabels[tab]}</strong></div><button type="button" aria-label={text('关闭上下文栏', 'Close context panel')} onClick={onClose}><XIcon size={17} /></button></header>
      <div className="research-context-rail__body">
        <section className="research-context-rail__panel" role="region" aria-label={tabLabels[tab]} tabIndex={0}>
          {tab === 'agent' ? <div className="research-context-rail__agent-note"><span className="research-context-rail__agent-mark">Q</span><strong>{text('群学 Agent', 'Qunxue Agent')}</strong><p>{text('自然语言是入口。需要证据时，我会把本次会话的检索过程和来源放在这里。', 'Natural language is the starting point. When evidence is needed, retrieval activity and sources for this conversation appear here.')}</p></div> : null}
          {tab === 'activity' ? <ActivityPanel activities={activities} onSelect={onActivitySelect} /> : null}
          {tab === 'sources' ? <SourcesPanel citations={citations} selectedCitationId={selectedCitationId} onSelect={onCitationSelect} /> : null}
          {tab === 'basis' ? <div className="research-context-rail__basis">{basisContent ?? <div className="research-context-rail__empty"><FileTextIcon size={20} /><strong>{text('选择一条来源', 'Select a source')}</strong><p>{text('选择一条来源后，这里会显示它的依据。', 'Select a source to inspect its basis here.')}</p></div>}</div> : null}
        </section>
      </div>
    </aside>
  )
}

export type { AgentCitation, AgentToolStep }
