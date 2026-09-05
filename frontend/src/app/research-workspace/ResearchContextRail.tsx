import { ArrowLeftIcon, CaretRightIcon, CheckCircleIcon, CircleNotchIcon, FileTextIcon, MagnifyingGlassIcon, WarningCircleIcon, XIcon } from '@phosphor-icons/react'
import { useId, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

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

/** 右栏分段的归属。知识库是本体条目，web 是抓回来的外部网页，material 是用户自己传的研究材料。 */
export type ResearchCitationGroup = 'knowledge' | 'web' | 'material'

export type ResearchCitation = {
  id: string
  title: string
  kind: string
  subtitle?: string | null
  excerpt?: string | null
  knowledgeId?: string | null
  group?: ResearchCitationGroup
  /** 知识库维度（D1—D7），决定条目在栏里用哪一种色标。 */
  dimension?: string | null
}

export type ResearchContextTab = 'agent' | 'activity' | 'sources' | 'basis'

type ResearchContextRailProps = {
  readonly activeTab?: ResearchContextTab
  readonly activities?: readonly ResearchActivity[]
  readonly citations?: readonly ResearchCitation[]
  readonly basisContent?: ReactNode
  readonly selectedCitationId?: string | null
  /**
   * tabs：一次只显示一个面板，由外部按钮切换，用于研究工作区里内嵌的窄栏。
   * sections：知识库 / 网页 / 工作流程同屏堆叠，用于独立 Agent 页右侧那一列。
   */
  readonly variant?: 'tabs' | 'sections'
  readonly elapsedSeconds?: number | null
  readonly onClose?: () => void
  readonly onBack?: () => void
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

// 吸顶标题的行高，和 research-context-rail.css 里 summary 的 min-height 保持一致。
const RAIL_STICKY_HEIGHT = 44

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

function SourcesPanel({ citations, selectedCitationId, onSelect, numberOf }: { citations: readonly ResearchCitation[]; selectedCitationId?: string | null; onSelect?: (citation: ResearchCitation) => void; numberOf?: (citation: ResearchCitation) => number }) {
  const { text } = useAppLocale()
  if (!citations.length) return <div className="research-context-rail__empty"><FileTextIcon size={20} /><strong>{text('回答完成后，来源会出现在这里', 'Sources will appear here when the answer is complete')}</strong><p>{text('当本次回答绑定知识库来源时，来源会和回答保持对应。', 'Knowledge sources stay linked to the answer that used them.')}</p></div>
  return <div className="research-context-rail__source-list">{citations.map((citation) => <button type="button" className="research-context-rail__source" data-citation-id={citation.id} data-dimension={citation.dimension ?? undefined} aria-current={citation.id === selectedCitationId ? 'true' : undefined} key={citation.id} onClick={() => onSelect?.(citation)}><span className="research-context-rail__source-index">{numberOf ? numberOf(citation) : citations.indexOf(citation) + 1}</span><span><strong>{citation.title}</strong>{citation.subtitle ? <small>{citation.subtitle}</small> : null}{citation.excerpt ? <em>{citation.excerpt}</em> : null}</span></button>)}</div>
}

type RailSectionProps = {
  readonly title: string
  readonly count: number
  readonly index: number
  readonly meta?: string | null
  readonly emptyHint: string
  readonly children: ReactNode
}

function RailSection({ title, count, index, meta, emptyHint, children }: RailSectionProps) {
  // 折叠状态留在段内自己管：流式回答期间上层每秒都在重渲染，放上层会被反复重置回默认值。
  const [open, setOpen] = useState(true)
  const bodyId = useId()
  // 标题和内容是兄弟节点，不是 details/summary：只有同属一个滚动容器的直接子元素，
  // 粘性标题才能一层层堆在卡片顶部，而不是滚过自己那段就被带走。
  return (
    <>
      <button
        type="button"
        className="research-context-rail__section-head"
        aria-controls={bodyId}
        aria-expanded={open}
        style={{ '--rail-sticky-top': `${index * RAIL_STICKY_HEIGHT}px`, '--rail-sticky-layer': String(9 - index) } as CSSProperties}
        onClick={() => setOpen((current) => !current)}
      >
        <CaretRightIcon className="research-context-rail__section-caret" size={12} weight="bold" aria-hidden="true" />
        <span>{title}</span>
        {meta ? <em>{meta}</em> : null}
        <b>{count}</b>
      </button>
      <div className="research-context-rail__section-body" id={bodyId} role="group" aria-label={title} hidden={!open}>
        {count ? children : <p className="research-context-rail__section-empty">{emptyHint}</p>}
      </div>
    </>
  )
}

function elapsedLabel(seconds: number, locale: 'zh-CN' | 'en-US') {
  if (seconds < 60) return locale === 'en-US' ? `${seconds}s` : `用时 ${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return locale === 'en-US' ? `${minutes}m ${rest}s` : `用时 ${minutes} 分 ${rest} 秒`
}

function SectionsRail({
  tab,
  activities,
  citations,
  basisContent,
  selectedCitationId,
  elapsedSeconds,
  onBack,
  onActivitySelect,
  onCitationSelect,
}: {
  tab: ResearchContextTab
  activities: readonly ResearchActivity[]
  citations: readonly ResearchCitation[]
  basisContent?: ReactNode
  selectedCitationId?: string | null
  elapsedSeconds?: number | null
  onBack?: () => void
  onActivitySelect?: (activity: ResearchActivity) => void
  onCitationSelect?: (citation: ResearchCitation) => void
}) {
  const { locale, text } = useAppLocale()
  const knowledge = citations.filter((citation) => (citation.group ?? 'knowledge') === 'knowledge')
  const web = citations.filter((citation) => citation.group === 'web')
  const materials = citations.filter((citation) => citation.group === 'material')
  const numberOf = (citation: ResearchCitation) => citations.findIndex((item) => item.id === citation.id) + 1
  const running = activities.some((activity) => activity.status === 'running' && !activity.interrupted)
  const workflowMeta = elapsedSeconds && elapsedSeconds > 0
    ? elapsedLabel(elapsedSeconds, locale)
    : running ? text('进行中', 'Running') : null
  const showBasis = tab === 'basis'
  return (
    <aside className="research-context-rail research-context-rail--sections" aria-label={text('研究面板', 'Research panel')}>
      {/* 总览不需要标题栏：栏是什么、怎么收起，右上角那个开关已经说清楚了。 */}
      {showBasis ? (
        <header className="research-context-rail__header">
          <button className="research-context-rail__back" type="button" onClick={onBack}>
            <ArrowLeftIcon size={15} aria-hidden="true" /><strong>{text('依据', 'Basis')}</strong>
          </button>
        </header>
      ) : null}
      <div className="research-context-rail__body">
        {showBasis ? (
          <section className="research-context-rail__panel" role="region" aria-label={text('依据', 'Basis')} tabIndex={0}>
            <div className="research-context-rail__basis">
              {basisContent ?? <div className="research-context-rail__empty"><FileTextIcon size={20} /><strong>{text('选择一条来源', 'Select a source')}</strong><p>{text('选择一条来源后，这里会显示它的依据。', 'Select a source to inspect its basis here.')}</p></div>}
            </div>
          </section>
        ) : (
          <section className="research-context-rail__sections" role="region" aria-label={text('研究面板', 'Research panel')} tabIndex={0}>
            <RailSection
              title={text('知识库', 'Knowledge base')}
              count={knowledge.length}
              index={0}
              emptyHint={text('这次回答还没有引用知识库条目。', 'No knowledge entries cited yet.')}
            >
              <SourcesPanel citations={knowledge} selectedCitationId={selectedCitationId} onSelect={onCitationSelect} numberOf={numberOf} />
            </RailSection>
            <RailSection
              title={text('网页', 'Web pages')}
              count={web.length}
              index={1}
              emptyHint={text('这次回答还没有读取网页。', 'No web pages read yet.')}
            >
              <SourcesPanel citations={web} selectedCitationId={selectedCitationId} onSelect={onCitationSelect} numberOf={numberOf} />
            </RailSection>
            {(
              <RailSection title={text('用户文件', 'Your files')} count={materials.length} index={2} emptyHint={text('这次回答还没有引用你选择的文件。', 'This answer has not cited your selected files yet.')}>
                <SourcesPanel citations={materials} selectedCitationId={selectedCitationId} onSelect={onCitationSelect} numberOf={numberOf} />
              </RailSection>
            )}
            <RailSection
              title={text('工作流程', 'Workflow')}
              count={activities.length}
              index={3}
              meta={workflowMeta}
              emptyHint={text('Agent 开始检索后，这里按步骤记录它做了什么。', 'Steps appear here once the Agent starts retrieving.')}
            >
              <ActivityPanel activities={activities} onSelect={onActivitySelect} />
            </RailSection>
          </section>
        )}
      </div>
    </aside>
  )
}

export function ResearchContextRail({
  activeTab: controlledTab,
  activities = [],
  citations = [],
  basisContent,
  selectedCitationId,
  variant = 'tabs',
  elapsedSeconds = null,
  onClose,
  onBack,
  onActivitySelect,
  onCitationSelect,
}: ResearchContextRailProps) {
  const { text } = useAppLocale()
  const tab = controlledTab ?? 'agent'
  if (variant === 'sections') {
    return (
      <SectionsRail
        tab={tab}
        activities={activities}
        citations={citations}
        basisContent={basisContent}
        selectedCitationId={selectedCitationId}
        elapsedSeconds={elapsedSeconds}
        onBack={onBack}
        onActivitySelect={onActivitySelect}
        onCitationSelect={onCitationSelect}
      />
    )
  }
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
