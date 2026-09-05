import {
  ArrowClockwiseIcon,
  ArticleIcon,
  ArrowUpIcon,
  CaretDownIcon,
  CaretRightIcon,
  CheckIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  CirclesThreeIcon,
  CompassIcon,
  CopyIcon,
  DotsThreeIcon,
  DownloadSimpleIcon,
  FilePdfIcon,
  FilePlusIcon,
  FileTextIcon,
  FolderOpenIcon,
  GlobeHemisphereWestIcon,
  GlobeSimpleIcon,
  LinkSimpleIcon,
  ListIcon,
  MagnifyingGlassIcon,
  TreeStructureIcon,
  PencilLineIcon,
  PlusIcon,
  SidebarSimpleIcon,
  StopIcon,
  TrashIcon,
  WarningCircleIcon,
  XCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { createPortal, flushSync } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { remarkProgressParagraphs } from './remarkProgressParagraphs'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'

import {
  ResearchContextRail,
  ToolDetailDisclosure,
  type ResearchActivity,
  type ResearchCitation,
  type ResearchContextTab,
} from '../research-workspace/ResearchContextRail'
import { PageContent, PageShell } from '../ui/PageShell'
import {
  deleteAgentConversation,
  getAgentConversation,
  getResearchStartJourney,
  listAgentConversations,
  renameAgentConversation,
  stopAgentRun,
  streamAgentTurn,
  type AgentCitation,
  type AgentConversation,
  type AgentConversationSummary,
  type AgentEvent,
  type AgentRuntimeMode,
  type AgentToolStep,
  type AgentToolTrace,
  type AgentTurn,
  buildResearchReport,
  collectReferences,
  conclusionDigest,
  createResearchReportDocx,
  displayAgentText,
  formatElapsed,
  openResearchReportPrintWindow,
  researchReportDocxFilename,
} from '../../modules/research-agent'
import type { ResearchCanvasStreamingTurn } from '../../modules/research-workspace'
import {
  addResearchLibraryMaterial,
  AgentMaterialAttachmentPicker,
  formatMaterialLocator,
  isSupportedResearchMaterialFile,
  listAgentMaterials,
  prepareAgentMaterialContext,
  getAgentAttachmentMaterial,
  normalizeMaterialLocator,
  RESEARCH_MATERIAL_ACCEPT,
  ResearchMaterialsPanel,
  type ResearchMaterial,
  type ResearchMaterialLocator,
} from '../../modules/research-materials'
import { ProjectCreatePopover } from './ProjectCreatePopover'
import { ProjectScopeMenu } from './ProjectScopeMenu'
import { ProjectConversationList } from './ProjectConversationList'
import { deleteResearchProject, listResearchProjects, type ResearchProject } from '../../modules/research-projects'
import { createMaterialFirstResearchProject } from '../../modules/socio-match-workspace'
import { ResearchAgentBot } from './ResearchAgentBot'
import { ResearchAgentShader } from './ResearchAgentShader'
import { ResearchPromptCarousel } from './ResearchPromptCarousel'
import deepResearchGuidance from '../../assets/agent/new-research-guidance.webp'
import { useAppLocale, type AppLocale } from '../i18n/AppLocaleProvider'
import './research-agent-page.css'
import './new-research-workspace.css'

// The conversation controller is shared by the standalone Agent and embedded
// research workspaces. Embedded callers provide the research context explicitly;
// the standalone route remains isolated in the read-only Agent workspace.
const MAX_AGENT_MESSAGE_LENGTH = 12_000
const DRAFT_STORAGE_KEY = 'qunxue.agent.composer-draft.v1'
const PENDING_TURN_STORAGE_KEY = 'qunxue.agent.pending-turn.v1'
const INTERRUPTED_TURN_STORAGE_KEY = 'qunxue.agent.interrupted-turn.v1'
const KNOWLEDGE_RELEASE_STORAGE_KEY = 'qunxue.agent.knowledge-releases.v1'
const AGENT_RUNTIME_STORAGE_KEY = 'qunxue.agent.runtime-modes.v1'
const DEEP_RESEARCH_INTRO_SESSION_KEY = 'qunxue.agent.deep-research-intro-session.v1'
const DEEP_RESEARCH_INTRO_TIMEOUT_MS = 10_000
// 退场动画时长，和 research-agent-conversation.css 里 agent-rail-leave 保持一致。
const RAIL_EXIT_MS = 220

const DELETED_MATERIAL_ANSWER = '该回答引用的个人研究材料已删除，原回答内容已隐藏。'
type AgentComposerMode = 'standard' | 'deep-research'
type DeepResearchMockStage = 'idle' | 'clarifying' | 'planning' | 'researching' | 'completed'
type DeepResearchExportState = 'idle' | 'docx' | 'pdf'

function attachmentStatusLabel(material: ResearchMaterial, locale: 'zh-CN' | 'en-US') {
  if (material.unavailableReason === 'ocr_required') return locale === 'en-US' ? 'OCR required' : '需要 OCR'
  if (material.unavailableReason === 'transcription_unavailable') return locale === 'en-US' ? 'Transcription unavailable' : '未配置转写'
  if (material.unavailableReason === 'transcription_required') return locale === 'en-US' ? 'Transcription required' : '等待转写'
  if (material.ingestionStatus === 'queued') return locale === 'en-US' ? 'Queued' : '等待解析'
  if (material.ingestionStatus === 'failed' || material.status === 'failed') return locale === 'en-US' ? 'Failed' : '解析失败'
  return locale === 'en-US' ? 'Processing' : '处理中'
}

const DEEP_RESEARCH_MOCK_STEPS = [
  '拆解研究问题',
  '检索知识库与个人材料',
  '补充并阅读公开网页',
  '核对来源，整理研究结论',
]

function DeepResearchMockFlow({
  stage,
  question,
  stepIndex,
  options = ['概念与理论背景', '现实案例与最新资料', '不同观点之间的争议', '研究方法与数据'],
  onChooseIntent,
  onSkip,
  onConfirmPlan,
  onEdit,
  knowledgeCount,
  webCount,
  toolSteps = [],
  elapsedSeconds = 0,
  conclusion,
  exportState = 'idle',
  onExport,
  onContinueResearch,
  researchEntryBusy = false,
}: {
  stage: DeepResearchMockStage
  question: string
  stepIndex: number
  options?: string[]
  onChooseIntent: (intent: string) => void
  onSkip: () => void
  onConfirmPlan: () => void
  onEdit: () => void
  knowledgeCount?: number
  webCount?: number
  toolSteps?: AgentToolStep[]
  elapsedSeconds?: number
  conclusion?: string
  exportState?: DeepResearchExportState
  onExport?: (kind: 'docx' | 'pdf') => void
  onContinueResearch?: () => void
  researchEntryBusy?: boolean
}) {
  const [customIntent, setCustomIntent] = useState('')
  const [detailsOpen, setDetailsOpen] = useState(false)
  // 选完到计划卡出现之间要等一次往返，中间没有反馈就像点空了。
  const [chosenIntent, setChosenIntent] = useState<string | null>(null)
  if (stage === 'idle') return null

  if (stage === 'clarifying') {
    return (
      <section
        className={`deep-research-mock-card deep-research-mock-card--question${chosenIntent ? ' is-answered' : ''}`}
        aria-label="确认研究意图"
      >
        <h2>{question}</h2>
        <div className="deep-research-mock-card__options" role="radiogroup" aria-label="研究角度">
          {options.filter((option) => option !== '更多自定义').map((option, index) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={chosenIntent === option}
              disabled={chosenIntent !== null}
              className={chosenIntent === option ? 'is-chosen' : undefined}
              onClick={() => { setChosenIntent(option); onChooseIntent(option) }}
            >
              <b>{chosenIntent === option ? <CheckIcon size={14} weight="bold" /> : String.fromCharCode(65 + index)}</b>
              {option}
              {chosenIntent === option ? <em>已选择</em> : null}
            </button>
          ))}
        </div>
        <div className="deep-research-mock-card__options deep-research-mock-card__options--custom">
          <button
            type="button"
            role="radio"
            aria-checked={chosenIntent === customIntent.trim() && customIntent.trim() !== ''}
            disabled={chosenIntent !== null}
            onClick={() => setCustomIntent((current) => current || ' ')}
          >
            <b>E</b>更多自定义
          </button>
          <button type="button" disabled={chosenIntent !== null} onClick={() => { setChosenIntent('跳过'); onSkip() }}>跳过</button>
        </div>
        {customIntent !== '' && chosenIntent === null ? (
          <label className="deep-research-mock-card__other">
            <span>补充方向</span>
            <input autoFocus value={customIntent.trim()} onChange={(event) => setCustomIntent(event.target.value)} placeholder="写下你想研究的方向" />
            <button type="button" disabled={!customIntent.trim()} onClick={() => { setChosenIntent(customIntent.trim()); onChooseIntent(customIntent.trim()) }}>继续</button>
          </label>
        ) : null}
        {chosenIntent ? (
          <p className="deep-research-mock-card__answered" aria-live="polite">
            已按<strong>{chosenIntent}</strong>这个角度整理研究计划，稍等一下。
          </p>
        ) : null}
      </section>
    )
  }

  if (stage === 'planning') {
    return (
      <section className="deep-research-mock-card" aria-label="研究计划">
        <h2>研究：{question}</h2>
        <div className="deep-research-mock-card__plan">
          {options.map((step, index) => <div key={`${step}-${index}`}><strong>{index + 1}</strong><span>{step}</span></div>)}
        </div>
        <div className="deep-research-mock-card__actions">
          <button type="button" className="is-primary" onClick={onConfirmPlan}>开始深入研究</button>
          <button type="button" onClick={onEdit}>返回修改</button>
        </div>
      </section>
    )
  }

  // 完成后以结论和后续操作替代过程清单，详细过程仍可展开工具调用查看。
  const done = stage === 'completed'
  const percent = done
    ? 100
    : Math.round(((Math.min(stepIndex, DEEP_RESEARCH_MOCK_STEPS.length - 1) + 0.5) / DEEP_RESEARCH_MOCK_STEPS.length) * 100)
  const reachedIndex = done ? DEEP_RESEARCH_MOCK_STEPS.length : stepIndex
  const toolCalls = toolSteps.length
    ? toolSteps.map((step) => ({ tool: step.tool, label: step.label, detail: step.detail || '' }))
    : [{ tool: 'research', label: done ? '工具调用已完成' : '等待工具调用', detail: done ? '' : '研究即将开始' }]
  return (
    <section
      className={`deep-research-mock-card deep-research-mock-card--progress${done ? ' deep-research-mock-card--done' : ''}`}
      aria-label={done ? '研究结论' : '研究进度'}
      aria-live="polite"
    >
      <div className="deep-research-mock-card__eyebrow">{done ? '研究完成' : '正在深入研究'}</div>
      <h2>{done ? '已经整理好一份带证据的结论' : '我正在逐步核对证据'}</h2>
      <div className="deep-research-mock-card__progress-meta">
        <span>{elapsedSeconds > 0 ? `${done ? '用时' : '已运行'} ${formatElapsed(elapsedSeconds)}` : done ? '研究已完成' : '正在开始'}</span>
        <span>{percent}%</span>
      </div>
      <div className="deep-research-mock-card__progress-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <span style={{ width: `${percent}%` }} />
      </div>
      {!done ? <div className="deep-research-mock-card__steps">
        {DEEP_RESEARCH_MOCK_STEPS.map((step, index) => (
          <div key={step} className={index < reachedIndex ? 'is-complete' : index === reachedIndex ? 'is-active' : ''}>
            <span aria-hidden="true">{index < reachedIndex ? '✓' : index === reachedIndex ? '•' : '○'}</span>{step}
          </div>
        ))}
      </div> : null}
      {done ? (
        <div className="deep-research-mock-card__conclusion">
          <div className="deep-research-mock-card__eyebrow">研究结论</div>
          <p>{conclusion || '这一轮没有产生可摘录的结论，完整回答见上方正文。'}</p>
          <div className="deep-research-mock-card__result-meta">
            <span>知识库 {knowledgeCount ?? 0} 条</span>
            <span>网页资料 {webCount ?? 0} 条</span>
          </div>
        </div>
      ) : null}
      <button type="button" className="deep-research-mock-card__details-toggle" onClick={() => setDetailsOpen((open) => !open)} aria-expanded={detailsOpen}>
        {detailsOpen ? '收起工具调用' : '查看工具调用'}<CaretDownIcon size={13} weight="bold" className={detailsOpen ? 'is-open' : ''} />
      </button>
      {detailsOpen ? (
        <div className="deep-research-mock-card__tool-calls">
          {toolCalls.map((call, index) => (
            <div key={`${call.tool}-${index}`} className={toolSteps[index]?.status === 'completed' || index < reachedIndex ? 'is-complete' : index === reachedIndex ? 'is-active' : ''}>
              <span>{toolSteps[index]?.status === 'completed' || index < reachedIndex ? '✓' : index === reachedIndex ? '•' : '○'}</span>
              <strong>{call.label}</strong>
              <small>{call.detail}</small>
            </div>
          ))}
        </div>
      ) : null}
      {done ? (
        <div className="deep-research-mock-card__export">
          <p>这一轮的问答连同全部引用，可以直接导出成一份带来源的研究报告。</p>
          <div className="deep-research-mock-card__export-actions">
            {onExport ? <>
              <button type="button" disabled={exportState !== 'idle'} onClick={() => onExport('docx')}>
                <DownloadSimpleIcon size={14} weight="bold" />{exportState === 'docx' ? '正在生成 Word…' : '下载 Word'}
              </button>
              <button type="button" disabled={exportState !== 'idle'} onClick={() => onExport('pdf')}>
                <FilePdfIcon size={14} />{exportState === 'pdf' ? '正在生成 PDF…' : '下载 PDF'}
              </button>
            </> : null}
            <button type="button" className="deep-research-mock-card__continue"
              disabled={researchEntryBusy} onClick={onContinueResearch}>
              {researchEntryBusy ? '正在整理研究起点…' : '继续形成研究'}<CaretRightIcon size={14} />
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}

const knowledgeTools = new Set([
  'search_knowledge',
  'read_knowledge_entry',
  'read_sources',
  'browse_knowledge_directory',
])

const researchMaterialTools = new Set([
  'search_research_materials',
  'read_research_material_context',
])

// Labels also cover historical traces created before workspace tool scopes were
// narrowed; displaying them does not make those tools callable from /agent.
const toolLabels: Record<string, string> = {
  search_knowledge: '检索知识库',
  read_knowledge_entry: '读取知识条目',
  read_sources: '读取来源',
  browse_knowledge_directory: '浏览知识目录',
  search_research_materials: '检索研究材料',
  read_research_material_context: '读取研究材料原文',
  search_web: '搜索公开网页',
  read_web_page: '读取网页正文',
  update_research_map: '更新研究地图',
  propose_start_research: '整理研究起点',
  get_research_workflow_state: '读取研究进度',
  start_theory_matching: '启动理论匹配',
  save_confirmed_theory_plan: '保存已确认理论方案',
  read_research_document: '读取研究文档',
  propose_document_revision: '整理文档修订提议',
  propose_document_creation: '整理文档创建提议',
}

const englishToolLabels: Record<string, string> = {
  search_knowledge: 'Search knowledge base',
  read_knowledge_entry: 'Read knowledge entry',
  read_sources: 'Read sources',
  browse_knowledge_directory: 'Browse knowledge directory',
  search_research_materials: 'Search research materials',
  read_research_material_context: 'Read research material context',
  search_web: 'Search the web',
  read_web_page: 'Read web page',
  update_research_map: 'Update research map',
  propose_start_research: 'Prepare research starting point',
  get_research_workflow_state: 'Read research progress',
  start_theory_matching: 'Start theory matching',
  save_confirmed_theory_plan: 'Save confirmed theory plan',
  read_research_document: 'Read research document',
  propose_document_revision: 'Prepare document revision',
  propose_document_creation: 'Prepare document creation',
}

const toolPurposes: Record<string, string> = {
  search_knowledge: '根据当前研究问题寻找相关概念、理论与已有研究参照',
  read_knowledge_entry: '根据当前问题核对知识条目的主张、适用前提与证据边界',
  read_sources: '补充作者、年份、研究对象与原始来源信息',
  browse_knowledge_directory: '查看当前知识版本中可用于研究的内容范围',
  search_research_materials: '从当前研究任务的个人材料中寻找相关原文片段',
  read_research_material_context: '沿精确位置读取片段前后文，避免脱离整份材料解释',
  search_web: '查找当前政策、新闻、报告与其他公开网页来源',
  read_web_page: '读取网页正文，避免只根据搜索摘要形成结论',
  update_research_map: '把已确认的问题、理论与证据关系写入研究画布',
  propose_start_research: '把现象、研究意图与情境整理成待确认的研究起点',
  get_research_workflow_state: '读取当前研究任务的阶段与可继续操作',
  start_theory_matching: '基于已确认现象和证据生成可比较的理论候选',
  save_confirmed_theory_plan: '保存你已经确认的理论取舍与使用方式',
  read_research_document: '读取当前正式研究文档及其版本',
  propose_document_revision: '把修改整理成待你接受或拒绝的文档建议',
  propose_document_creation: '把已确认理论方案整理成 12 节研究框架草稿',
}

const englishToolPurposes: Record<string, string> = {
  search_knowledge: 'Find concepts, theories, and prior research relevant to the question',
  read_knowledge_entry: 'Check an entry\'s claims, assumptions, and evidence limits',
  read_sources: 'Add author, year, research subject, and original source details',
  browse_knowledge_directory: 'Review the research material available in this knowledge release',
  search_research_materials: 'Find relevant passages in the personal materials bound to this research task',
  read_research_material_context: 'Read the surrounding context at the exact source position',
  search_web: 'Find current policies, news, reports, and other public web sources',
  read_web_page: 'Read the page text instead of relying on a search snippet',
  update_research_map: 'Record confirmed questions, theories, and evidence relationships',
  propose_start_research: 'Prepare the phenomenon and research intent for confirmation',
  get_research_workflow_state: 'Read the current research phase and available next actions',
  start_theory_matching: 'Compare theory candidates against the confirmed phenomenon and evidence',
  save_confirmed_theory_plan: 'Save the theory choices and use confirmed by you',
  read_research_document: 'Read the current formal research document and version',
  propose_document_revision: 'Prepare document changes for your acceptance or rejection',
  propose_document_creation: 'Turn the confirmed theory plan into a 12-section framework draft',
}

function localizedToolLabel(tool: string, locale: AppLocale, fallback?: string) {
  if (locale === 'en-US') return englishToolLabels[tool] ?? tool.replaceAll('_', ' ')
  return toolLabels[tool] ?? fallback ?? tool
}

function localizedToolPurpose(tool: string, locale: AppLocale) {
  if (locale === 'en-US') return englishToolPurposes[tool] ?? 'Use this step to advance the current research task'
  return toolPurposes[tool] ?? '根据当前问题推进研究任务'
}

function localizedToolDetail(detail: string, locale: AppLocale) {
  const publicDetail = detail
    .replaceAll('知识库预览内容（未审核）', '知识条目')
    .replaceAll('知识库预览条目（未审核）', '知识条目')
    .replaceAll('未审核预览', '知识条目')
    .replaceAll('待审核发现关系', '候选关系')
    .replaceAll('已审核知识关系', '知识关系')
  if (locale !== 'en-US') return publicDetail
  if (publicDetail === '工具调用失败') return 'Tool call failed'
  if (publicDetail === '已停止') return 'Stopped'
  return publicDetail
}

function localizedTurnFailure(code: string, message: string, locale: AppLocale) {
  if (locale !== 'en-US') return message
  if (code === 'not_found') return 'This conversation does not exist or you do not have access.'
  if (code === 'run_in_progress') return 'A response is already being generated. Please wait.'
  if (code === 'credits_depleted') return 'You do not have enough credits. Review your usage in Account settings.'
  return 'The Agent cannot complete this answer right now. Please try again later.'
}

type AgentPageStatus = 'idle' | 'loading' | 'thinking' | 'retrieving' | 'answering' | 'error'
type AgentToolEvent = Extract<AgentEvent, { type: 'tool_started' | 'tool_finished' | 'tool_failed' }>
type ResearchToolStep = AgentToolStep & { interrupted?: boolean }
type StreamingTurn = {
  progressEnd?: number
  question: string
  answer: string
  citations: AgentCitation[]
  toolSteps: ResearchToolStep[]
  canvasPatches: ResearchCanvasStreamingTurn['canvasPatches']
  startedAt: number
  interrupted?: boolean
  failure?: string
}
type PendingTurnAttempt = {
  question: string
  idempotencyKey: string
  conversationId: string | null
  runId?: string | null
  materialIds: string[]
}

type ResearchStartHandoff = {
  proposalId: string
  conversationId: string
  knowledgeReleaseId: string
  phenomenon: string
  researchIntent: string | null
}

type SelectedCitationContext = {
  citation: AgentCitation
  knowledgeReleaseId: string | null
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function researchStartHandoffFromSteps(steps: ResearchToolStep[]): ResearchStartHandoff | null {
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index]
    if (step.tool !== 'propose_start_research' || step.status !== 'completed') continue
    const output = objectRecord(step.output)
    if (!output || output.requires_user_confirmation !== true || output.status !== 'pending_confirmation') continue
    const proposalId = nonEmptyString(output.proposal_id)
    const conversationId = nonEmptyString(output.conversation_id)
    const knowledgeReleaseId = nonEmptyString(output.knowledge_release_id)
    const phenomenon = nonEmptyString(output.phenomenon)
    if (!proposalId || !conversationId || !knowledgeReleaseId || !phenomenon) continue
    return {
      proposalId,
      conversationId,
      knowledgeReleaseId,
      phenomenon,
      researchIntent: nonEmptyString(output.research_intent),
    }
  }
  return null
}

function ResearchStartHandoffCard({ handoff, onContinueResearch, busy }: { handoff: ResearchStartHandoff; onContinueResearch?: () => void; busy?: boolean }) {
  const { text } = useAppLocale()
  return (
    <section className="deep-research-mock-card research-flow-card" aria-label={text('研究建议', 'Research suggestion')} data-proposal-id={handoff.proposalId}>
      <header className="research-flow-card__heading"><CompassIcon size={22} weight="regular" aria-hidden="true" /><h2>{handoff.phenomenon}</h2></header>
      {handoff.researchIntent ? <div className="deep-research-mock-card__conclusion"><p>{handoff.researchIntent}</p></div> : null}
      <div className="deep-research-mock-card__actions deep-research-mock-card__export-actions">
        <button type="button" className="deep-research-mock-card__continue" disabled={busy} onClick={onContinueResearch}>
          {busy ? text('正在整理研究起点…', 'Preparing research…') : text('去新建研究', 'Open new research')} <CaretRightIcon size={14} aria-hidden="true" />
        </button>
      </div>
    </section>
  )
}

function KnowledgeHandoffCards({
  citation,
  conversationId,
  knowledgeReleaseId,
}: {
  citation: AgentCitation
  conversationId: string
  knowledgeReleaseId: string
}) {
  const { text } = useAppLocale()
  if (!citation.knowledge_id) return null
  const returnParams = new URLSearchParams({
    conversation_id: conversationId,
    knowledge_release_id: knowledgeReleaseId,
  })
  const entryParams = new URLSearchParams({
    knowledge_release_id: knowledgeReleaseId,
    return_to: `/agent?${returnParams.toString()}`,
  })
  const graphParams = new URLSearchParams({
    knowledge_release_id: knowledgeReleaseId,
    center: citation.knowledge_id,
    query: citation.label,
  })
  const entryHref = `/knowledge/${encodeURIComponent(citation.knowledge_id)}?${entryParams.toString()}`
  const graphHref = `/knowledge/graph?${graphParams.toString()}`

  return (
    <div className="research-agent-knowledge-handoffs">
      <section className="research-agent-handoff research-agent-handoff--compact" aria-label={text('知识库建议', 'Knowledge base suggestion')}>
        <span className="research-agent-handoff__mark" aria-hidden="true"><ArticleIcon size={23} weight="duotone" /></span>
        <div className="research-agent-handoff__copy">
          <small>{text('去知识库阅读', 'Read in the knowledge base')}</small>
          <strong>{citation.label}</strong>
          <p>{text('查看完整条目、来源与当前发布版本', 'View the full entry, its sources, and the current release')}</p>
        </div>
        <Link className="research-agent-handoff__link" to={entryHref}>{text('打开知识条目', 'Open knowledge entry')} <CaretRightIcon size={14} aria-hidden="true" /></Link>
      </section>
      <section className="research-agent-handoff research-agent-handoff--compact" aria-label={text('知识图谱建议', 'Knowledge graph suggestion')}>
        <span className="research-agent-handoff__mark" aria-hidden="true"><TreeStructureIcon size={23} weight="duotone" /></span>
        <div className="research-agent-handoff__copy">
          <small>{text('沿知识关系探索', 'Explore related knowledge')}</small>
          <strong>{citation.label}</strong>
          <p>{text('从这个节点继续查看关联概念与理论', 'Continue from this node to related concepts and theories')}</p>
        </div>
        <Link className="research-agent-handoff__link" to={graphHref}>{text('查看知识节点', 'View knowledge node')} <CaretRightIcon size={14} aria-hidden="true" /></Link>
      </section>
    </div>
  )
}

function scopedSessionKey(base: string, userId: string | null) {
  return userId ? `${base}.${userId}` : null
}

function readStoredDraft(userId: string | null) {
  if (typeof window === 'undefined') return ''
  try {
    const storageKey = scopedSessionKey(DRAFT_STORAGE_KEY, userId)
    return storageKey
      ? window.sessionStorage.getItem(storageKey)?.slice(0, MAX_AGENT_MESSAGE_LENGTH) ?? ''
      : ''
  } catch {
    return ''
  }
}

function persistDraft(userId: string | null, value: string) {
  if (typeof window === 'undefined') return
  try {
    const storageKey = scopedSessionKey(DRAFT_STORAGE_KEY, userId)
    if (!storageKey) return
    if (value) window.sessionStorage.setItem(storageKey, value)
    else window.sessionStorage.removeItem(storageKey)
  } catch {
    // Storage recovery is optional; the controlled composer remains usable.
  }
}

function readPendingTurnAttempt(userId: string | null): PendingTurnAttempt | null {
  if (typeof window === 'undefined') return null
  try {
    const storageKey = scopedSessionKey(PENDING_TURN_STORAGE_KEY, userId)
    if (!storageKey) return null
    const raw = window.sessionStorage.getItem(storageKey)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<PendingTurnAttempt>
    if (
      typeof value.question !== 'string'
      || !value.question.trim()
      || value.question.length > MAX_AGENT_MESSAGE_LENGTH
      || typeof value.idempotencyKey !== 'string'
      || !value.idempotencyKey
      || (value.conversationId !== null && typeof value.conversationId !== 'string')
    ) return null
    return {
      question: value.question,
      idempotencyKey: value.idempotencyKey,
      conversationId: value.conversationId ?? null,
      runId: typeof value.runId === 'string' && value.runId ? value.runId : null,
      materialIds: Array.isArray(value.materialIds)
        ? value.materialIds.filter((item): item is string => typeof item === 'string').slice(0, 20)
        : [],
    }
  } catch {
    return null
  }
}

function persistPendingTurnAttempt(userId: string | null, value: PendingTurnAttempt | null) {
  if (typeof window === 'undefined') return
  try {
    const storageKey = scopedSessionKey(PENDING_TURN_STORAGE_KEY, userId)
    if (!storageKey) return
    if (value) window.sessionStorage.setItem(storageKey, JSON.stringify(value))
    else window.sessionStorage.removeItem(storageKey)
  } catch {
    // The in-memory idempotency key still protects the active retry.
  }
}

function readInterruptedTurn(userId: string | null): StreamingTurn | null {
  if (typeof window === 'undefined') return null
  try {
    const storageKey = scopedSessionKey(INTERRUPTED_TURN_STORAGE_KEY, userId)
    if (!storageKey) return null
    const raw = window.sessionStorage.getItem(storageKey)
    if (!raw) return null
    const value = objectRecord(JSON.parse(raw))
    if (
      !value
      || typeof value.question !== 'string'
      || !value.question.trim()
      || value.question.length > MAX_AGENT_MESSAGE_LENGTH
      || typeof value.answer !== 'string'
      || value.interrupted !== true
      || !Array.isArray(value.citations)
      || !Array.isArray(value.toolSteps)
      || !Array.isArray(value.canvasPatches)
    ) return null
    const toolSteps = value.toolSteps.filter((item): item is ResearchToolStep => {
      const step = objectRecord(item)
      return Boolean(
        step
        && typeof step.id === 'string'
        && typeof step.tool === 'string'
        && typeof step.label === 'string'
        && (step.status === 'running' || step.status === 'completed' || step.status === 'failed'),
      )
    })
    return {
      question: value.question,
      answer: value.answer,
      citations: value.citations as AgentCitation[],
      toolSteps,
      canvasPatches: value.canvasPatches as ResearchCanvasStreamingTurn['canvasPatches'],
      startedAt: typeof value.startedAt === 'number' && Number.isFinite(value.startedAt) ? value.startedAt : Date.now(),
      interrupted: true,
      failure: typeof value.failure === 'string' && value.failure ? value.failure : undefined,
    }
  } catch {
    return null
  }
}

function persistInterruptedTurn(userId: string | null, value: StreamingTurn | null) {
  if (typeof window === 'undefined') return
  try {
    const storageKey = scopedSessionKey(INTERRUPTED_TURN_STORAGE_KEY, userId)
    if (!storageKey) return
    if (value) window.sessionStorage.setItem(storageKey, JSON.stringify(value))
    else window.sessionStorage.removeItem(storageKey)
  } catch {
    // The stopped turn remains visible in memory when storage is unavailable.
  }
}

function readStringMap(userId: string | null, base: string): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const storageKey = scopedSessionKey(base, userId)
    if (!storageKey) return {}
    const raw = window.sessionStorage.getItem(storageKey)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>)
        .filter((entry): entry is [string, string] => (
          Boolean(entry[0]) && typeof entry[1] === 'string' && Boolean(entry[1].trim())
        ))
        .slice(-100),
    )
  } catch {
    return {}
  }
}

function persistStringMap(userId: string | null, base: string, values: Record<string, string>) {
  if (typeof window === 'undefined') return
  try {
    const storageKey = scopedSessionKey(base, userId)
    if (storageKey) window.sessionStorage.setItem(storageKey, JSON.stringify(values))
  } catch {
    // URL state and persisted turns remain authoritative when storage is disabled.
  }
}

function readStoredRuntimeModes(userId: string | null): Record<string, AgentRuntimeMode> {
  const stored = readStringMap(userId, AGENT_RUNTIME_STORAGE_KEY)
  return Object.fromEntries(
    Object.entries(stored).filter((entry): entry is [string, AgentRuntimeMode] => (
      entry[1] === 'mock' || entry[1] === 'base' || entry[1] === 'sft'
    )),
  )
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

function outputCandidates(output: unknown): unknown[] {
  if (Array.isArray(output)) return output
  if (!output || typeof output !== 'object') return []
  const value = output as Record<string, unknown>
  for (const key of ['items', 'results', 'entries', 'sources']) {
    if (Array.isArray(value[key])) return value[key] as unknown[]
  }
  return []
}

function resultItemsFromOutput(output: unknown): NonNullable<ResearchActivity['resultItems']> {
  return outputCandidates(output).flatMap((item, index) => {
    if (!item || typeof item !== 'object') return []
    const value = item as Record<string, unknown>
    const title = typeof value.title === 'string'
      ? value.title
      : typeof value.label === 'string'
        ? value.label
        : typeof value.name === 'string'
          ? value.name
          : `结果 ${index + 1}`
    const excerpt = typeof value.excerpt === 'string'
      ? value.excerpt
      : typeof value.summary === 'string'
        ? value.summary
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

function citationKindLabel(kind: string, locale: AppLocale) {
  if (kind === 'preview' || kind === 'entry') return locale === 'en-US' ? 'Knowledge entry' : '知识条目'
  if (kind === 'source') return locale === 'en-US' ? 'Source' : '来源'
  if (kind === 'material' || kind === 'research_material') return locale === 'en-US' ? 'Research material' : '研究材料'
  if (kind === 'theory') return locale === 'en-US' ? 'Theory lead' : '理论线索'
  if (kind === 'directory') return locale === 'en-US' ? 'Knowledge directory' : '知识目录'
  return locale === 'en-US' ? 'Evidence' : '证据'
}

type MaterialCitationFields = {
  material_id?: unknown
  materialId?: unknown
  parse_id?: unknown
  parseId?: unknown
  segment_id?: unknown
  segmentId?: unknown
  locator?: unknown
}

function materialCitationFields(citation: AgentCitation | null): {
  materialId: string | null
  parseId: string | null
  segmentId: string | null
  locator: ResearchMaterialLocator | null
} {
  if (!citation || (citation.kind !== 'material' && citation.kind !== 'research_material')) {
    return { materialId: null, parseId: null, segmentId: null, locator: null }
  }
  const fields = citation as AgentCitation & MaterialCitationFields
  const materialId = typeof fields.material_id === 'string'
    ? fields.material_id
    : typeof fields.materialId === 'string' ? fields.materialId : null
  const segmentId = typeof fields.segment_id === 'string'
    ? fields.segment_id
    : typeof fields.segmentId === 'string' ? fields.segmentId : null
  const parseId = typeof fields.parse_id === 'string'
    ? fields.parse_id
    : typeof fields.parseId === 'string' ? fields.parseId : null
  return {
    materialId,
    parseId,
    segmentId,
    locator: fields.locator ? normalizeMaterialLocator(fields.locator) : null,
  }
}

function tombstoneMaterialCitation(citation: AgentCitation, materialId: string): AgentCitation {
  if (materialCitationFields(citation).materialId !== materialId) return citation
  return { ...citation, deleted: true, excerpt: null }
}

function tombstoneConversationMaterial(conversation: AgentConversation, materialId: string): AgentConversation {
  let changed = false
  const turns = conversation.turns.map((turn) => {
    const citations = turn.assistant.citations.map((citation) => {
      return tombstoneMaterialCitation(citation, materialId)
    })
    const affected = citations.some((citation, index) => citation !== turn.assistant.citations[index])
    if (!affected) return turn
    changed = true
    return {
      ...turn,
      assistant: { ...turn.assistant, content: DELETED_MATERIAL_ANSWER, citations },
    }
  })
  return changed ? { ...conversation, turns } : conversation
}


// 维度既可能来自条目号（D1:C213），也可能只出现在来源路径里（价值论/02-02-1...md）。
const dimensionByName: Array<[string, string]> = [
  ['本体论', 'D1'], ['实践论', 'D2'], ['方法论', 'D3'], ['价值论', 'D4'],
  ['认识论', 'D5'], ['传统', 'D6'], ['学科史', 'D7'],
]

function citationDimension(citation: AgentCitation): string | null {
  const fromId = citation.knowledge_id?.match(/\b(D[1-7])\b/)?.[1]
  if (fromId) return fromId
  if (citation.source_kind === 'web') return null
  const label = citation.label ?? ''
  return dimensionByName.find(([name]) => label.includes(name))?.[1] ?? null
}

// 网页来源的副标题给域名，比统一写"来源"更能让人判断这条证据可不可信。
function citationHost(citation: AgentCitation) {
  if (citation.source_kind !== 'web' || !citation.source_id) return null
  try {
    return new URL(citation.source_id).host.replace(/^www\./, '')
  } catch {
    return null
  }
}

function citationToRail(citation: AgentCitation, locale: AppLocale): ResearchCitation {
  const material = materialCitationFields(citation)
  const materialLocator = material.locator ? formatMaterialLocator(material.locator) : null
  const host = citationHost(citation)
  // 知识条目号形如 D1:C213，前缀就是知识库的维度，用它取和知识库页面同一套色。
  const dimension = citationDimension(citation)
  return {
    id: citation.citation_id,
    title: citation.label,
    kind: citation.kind,
    subtitle: host ?? `${citationKindLabel(citation.kind, locale)}${materialLocator ? ` · ${materialLocator}` : citation.knowledge_id ? ` · ${citation.knowledge_id}` : ''}`,
    excerpt: citation.excerpt,
    knowledgeId: citation.knowledge_id,
    group: citation.source_kind === 'web'
      ? 'web'
      : citation.kind === 'material' || citation.kind === 'research_material' ? 'material' : 'knowledge',
    dimension,
  }
}

function toActivity(step: ResearchToolStep, locale: AppLocale): ResearchActivity {
  return {
    id: step.id,
    tool: step.tool,
    label: localizedToolLabel(step.tool, locale, step.label),
    status: step.status,
    interrupted: step.interrupted,
    input: step.input,
    detail: step.detail ? localizedToolDetail(step.detail, locale) : step.detail,
    resultItems: resultItemsFromOutput(step.output),
  }
}

function updateToolSteps(steps: ResearchToolStep[], event: AgentToolEvent): ResearchToolStep[] {
  if (event.type === 'tool_started') {
    const id = event.call_id || `${event.tool}:${steps.filter((step) => step.tool === event.tool).length + 1}`
    const next: ResearchToolStep = {
      id,
      tool: event.tool,
      label: toolLabels[event.tool] || event.tool,
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
    label: existing?.label || toolLabels[event.tool] || event.tool,
    status: event.type === 'tool_failed' ? 'failed' : 'completed',
    input: existing?.input ?? (event.type === 'tool_failed' ? event.input : undefined),
    output: event.type === 'tool_finished' ? event.output : existing?.output,
    detail: event.type === 'tool_failed'
      ? event.detail || event.message
      : event.detail || formatToolPayload(event.output),
  }
  return index < 0 ? [...steps, next] : steps.map((step, stepIndex) => stepIndex === index ? next : step)
}

function researchStepForTools(steps: ResearchToolStep[]): number {
  const active = [...steps].reverse().find((step) => step.status === 'running')
  const tool = active?.tool || steps[steps.length - 1]?.tool
  if (!tool) return 0
  if (['search_knowledge', 'browse_knowledge_directory', 'search_research_materials'].includes(tool)) return 1
  if (['search_web', 'read_web_page'].includes(tool)) return 2
  if (['read_knowledge_entry', 'read_sources', 'read_research_material_context'].includes(tool)) return 2
  return 3
}

const DEEP_RESEARCH_TRACE = 'deep_research'

type DeepResearchRecord = { elapsedSeconds: number; knowledgeCount: number; webCount: number }

/** 深入研究完成时后端留在工具轨迹里的一条记录，重开对话靠它还原那张卡片。 */
function deepResearchRecord(turn: AgentTurn | undefined): DeepResearchRecord | null {
  const trace = turn?.tool_traces?.find((item) => item.tool === DEEP_RESEARCH_TRACE)
  const output = trace?.output
  if (!output || typeof output !== 'object') return null
  const value = output as Record<string, unknown>
  if (value.schema_version !== 1) return null
  return {
    elapsedSeconds: typeof value.elapsed_seconds === 'number' ? value.elapsed_seconds : 0,
    knowledgeCount: typeof value.knowledge_count === 'number' ? value.knowledge_count : 0,
    webCount: typeof value.web_count === 'number' ? value.web_count : 0,
  }
}

function persistedToolSteps(traces: AgentToolTrace[] | undefined): ResearchToolStep[] {
  let steps: ResearchToolStep[] = []
  for (const trace of traces ?? []) {
    if (trace.tool === DEEP_RESEARCH_TRACE) continue
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
            detail: trace.detail ?? null,
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

function interruptedSteps(steps: ResearchToolStep[], locale: AppLocale) {
  return steps.map((step) => step.status === 'running'
    ? { ...step, status: 'failed' as const, interrupted: true, detail: locale === 'en-US' ? 'Stopped' : '已停止' }
    : step)
}

function hasKnowledgeActivity(steps: ResearchToolStep[]) {
  return steps.some((step) => knowledgeTools.has(step.tool))
}

function hasCompletedKnowledgeActivity(steps: ResearchToolStep[]) {
  return steps.some((step) => knowledgeTools.has(step.tool) && step.status === 'completed')
}

function hasResearchMaterialActivity(steps: ResearchToolStep[]) {
  return steps.some((step) => researchMaterialTools.has(step.tool))
}

function AgentConversationHistoryRail({
  projects,
  setProjects,
  projectListError = null,
  selectedTaskId = null,
  activeConversationId,
  conversations,
  loading,
  onDelete,
  onDeleteProject,
  onNewConversation,
  onOpen,
  onRename,
}: {
  projects: ResearchProject[]
  setProjects: (projects: ResearchProject[]) => void
  projectListError?: string | null

  selectedTaskId?: string | null
  activeConversationId: string | null
  conversations: AgentConversationSummary[]
  loading: boolean
  onDelete: (conversation: AgentConversationSummary) => Promise<void>
  onDeleteProject: (taskId: string) => Promise<void>
  onNewConversation: (taskId?: string) => void
  onOpen: (conversation: AgentConversationSummary) => void
  onRename: (conversation: AgentConversationSummary, title: string) => Promise<void>
}) {
  const { text } = useAppLocale()
  const safeConversations = Array.isArray(conversations) ? conversations : []
  const [projectError, setProjectError] = useState<string | null>(null)
  const [projectCreateAnchor, setProjectCreateAnchor] = useState<HTMLElement | null>(null)
  const [projectTitle, setProjectTitle] = useState('')
  const [savingProject, setSavingProject] = useState(false)
  async function createProject(event: FormEvent) {
    event.preventDefault()
    if (!projectTitle.trim() || savingProject) return
    setSavingProject(true)
    try {
      const project = await createMaterialFirstResearchProject(crypto.randomUUID(), projectTitle.trim())
      setProjects([{ task_id: project.taskId, project_title: projectTitle.trim(), status: project.status }, ...projects])
      setProjectCreateAnchor(null)
      setProjectTitle('')
      onNewConversation(project.taskId)
    } catch (cause) {
      setProjectError(cause instanceof Error ? cause.message : text('项目创建失败', 'Project could not be created'))
    } finally { setSavingProject(false) }
  }
  const railRef = useRef<HTMLElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const [actionView, setActionView] = useState<{
    conversationId: string
    left: number
    top: number
    mode: 'menu' | 'rename' | 'delete'
  } | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const actionConversation = actionView
    ? safeConversations.find((conversation) => conversation.conversation_id === actionView.conversationId) ?? null
    : null

  useEffect(() => {
    if (!actionView) return undefined
    const closePopover = (event: globalThis.PointerEvent) => {
      const target = event.target as Node
      if (!railRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
        setActionView(null)
      }
    }
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setActionView(null)
    }
    const closeOnViewportChange = () => setActionView(null)
    document.addEventListener('pointerdown', closePopover)
    document.addEventListener('keydown', closeOnEscape)
    window.addEventListener('resize', closeOnViewportChange)
    window.addEventListener('scroll', closeOnViewportChange, true)
    globalThis.requestAnimationFrame?.(() => {
      popoverRef.current?.querySelector<HTMLElement>('button, input')?.focus()
    })
    return () => {
      document.removeEventListener('pointerdown', closePopover)
      document.removeEventListener('keydown', closeOnEscape)
      window.removeEventListener('resize', closeOnViewportChange)
      window.removeEventListener('scroll', closeOnViewportChange, true)
    }
  }, [actionView])

  function switchActionMode(mode: 'rename' | 'delete') {
    setActionView((current) => current ? { ...current, mode } : null)
    setDraftTitle(actionConversation?.title ?? '')
    setActionError(null)
  }

  async function submitRename(conversation: AgentConversationSummary) {
    const title = draftTitle.trim()
    if (!title || title === conversation.title) {
      setActionView(null)
      return
    }
    setBusyId(conversation.conversation_id)
    setActionError(null)
    try {
      await onRename(conversation, title)
      setActionView(null)
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : text('对话名称修改失败', 'Conversation could not be renamed'))
    } finally {
      setBusyId(null)
    }
  }

  async function confirmDelete(conversation: AgentConversationSummary) {
    setBusyId(conversation.conversation_id)
    setActionError(null)
    try {
      await onDelete(conversation)
      setActionView(null)
    } catch (cause: unknown) {
      setActionError(cause instanceof Error ? cause.message : text('对话删除失败', 'Conversation could not be deleted'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <section ref={railRef} className="agent-conversation-history" aria-label={text('Agent 对话记录', 'Agent conversation history')}>
      <div className="agent-conversation-history__heading">
        <h2>{text('项目', 'Projects')}</h2>
        <button type="button" className="agent-conversation-history__new" aria-label={text('新建项目', 'New project')} title={text('新建项目', 'New project')} aria-expanded={Boolean(projectCreateAnchor)} onClick={(event) => { setProjectError(null); setActionView(null); setProjectCreateAnchor(projectCreateAnchor ? null : event.currentTarget) }}><PlusIcon size={16} /></button>
      </div>
      {projectCreateAnchor ? <ProjectCreatePopover anchor={projectCreateAnchor} title={projectTitle} saving={savingProject} error={projectError}
        onTitleChange={setProjectTitle} onCancel={() => setProjectCreateAnchor(null)} onSubmit={(event) => { void createProject(event) }} /> : null}
      {projectListError ? <p role="alert">{projectListError}</p> : null}
      {loading ? <p role="status">{text('正在加载记录…', 'Loading history…')}</p> : (
        <ProjectConversationList projects={projects} conversations={safeConversations} onDeleteProject={onDeleteProject}
          activeTaskId={safeConversations.find((item) => item.conversation_id === activeConversationId)?.task_id ?? selectedTaskId}
          onStart={onNewConversation} onStartIndependent={() => onNewConversation()} renderConversation={(conversation) => {
            const conversationId = conversation.conversation_id
            return (
              <div className="agent-conversation-history__item" key={conversationId}>
                <div className="agent-conversation-history__row" data-current={conversationId === activeConversationId ? 'true' : undefined}>
                  <button
                    className="agent-conversation-history__open"
                    type="button"
                    aria-current={conversationId === activeConversationId ? 'true' : undefined}
                    onClick={() => onOpen(conversation)}
                    title={conversation.title}
                  >
                    <span>{conversation.title}</span>
                  </button>
                  <button
                    className="agent-conversation-history__actions"
                    type="button"
                    aria-label={text('打开对话操作', 'Open conversation actions')}
                    aria-haspopup="menu"
                    aria-expanded={actionView?.conversationId === conversationId}
                    onClick={(event) => {
                      if (actionView?.conversationId === conversationId) {
                        setActionView(null)
                        return
                      }
                      const rect = event.currentTarget.getBoundingClientRect()
                      setActionError(null)
                      setActionView({
                        conversationId,
                        left: Math.min(rect.right + 8, window.innerWidth - 260),
                        top: Math.min(rect.top - 4, window.innerHeight - 160),
                        mode: 'menu',
                      })
                    }}
                  >
                    <DotsThreeIcon size={18} weight="bold" aria-hidden="true" />
                  </button>
                </div>
              </div>
            )
          }} />
      )}
      </section>
      {actionView && actionConversation ? createPortal(
        <div
          ref={popoverRef}
          className={`agent-conversation-history__popover is-${actionView.mode}`}
          style={{ left: actionView.left, top: actionView.top }}
        >
          {actionView.mode === 'menu' ? (
            <div role="menu">
              <button type="button" role="menuitem" onClick={() => switchActionMode('rename')}>
                <PencilLineIcon size={14} aria-hidden="true" />{text('修改名称', 'Rename')}
              </button>
              <button className="is-danger" type="button" role="menuitem" onClick={() => switchActionMode('delete')}>
                <TrashIcon size={14} aria-hidden="true" />{text('删除对话', 'Delete conversation')}
              </button>
            </div>
          ) : actionView.mode === 'rename' ? (
            <form aria-label={text('修改对话名称', 'Rename conversation')} onSubmit={(event) => { event.preventDefault(); void submitRename(actionConversation) }}>
              <input
                aria-label={text('修改对话名称', 'Rename conversation')}
                disabled={busyId === actionConversation.conversation_id}
                maxLength={120}
                value={draftTitle}
                onChange={(event) => setDraftTitle(event.target.value)}
              />
              <div>
                <button type="button" disabled={busyId === actionConversation.conversation_id} onClick={() => setActionView(null)}>{text('取消', 'Cancel')}</button>
                <button className="is-primary" type="submit" aria-label={text('保存对话名称', 'Save conversation name')} disabled={busyId === actionConversation.conversation_id || !draftTitle.trim()}>{text('保存', 'Save')}</button>
              </div>
            </form>
          ) : (
            <div role="dialog" aria-label={text('删除对话', 'Delete conversation')}>
              <strong>{text('删除这段对话？', 'Delete this conversation?')}</strong>
              <div>
                <button type="button" disabled={busyId === actionConversation.conversation_id} onClick={() => setActionView(null)}>{text('取消', 'Cancel')}</button>
                <button className="is-danger" type="button" disabled={busyId === actionConversation.conversation_id} aria-label={text('确认删除对话', 'Confirm delete conversation')} onClick={() => { void confirmDelete(actionConversation) }}>{text('删除', 'Delete')}</button>
              </div>
            </div>
          )}
          {actionError ? <p role="alert">{actionError}</p> : null}
        </div>,
        railRef.current?.closest('.app-frame') ?? document.body,
      ) : null}
    </>
  )
}

function ConversationHistory({
  projects,
  setProjects,
  onNewConversation,
  onRename,
  onDelete,
  onDeleteProject,
  selectedTaskId,
  conversations,
  activeConversationId,
  loading,
  onOpen,
  onClose,
}: {
  projects: ResearchProject[]
  setProjects: (projects: ResearchProject[]) => void

  onNewConversation: (taskId?: string) => void
  onRename: (conversation: AgentConversationSummary, title: string) => Promise<void>
  onDelete: (conversation: AgentConversationSummary) => Promise<void>
  onDeleteProject: (taskId: string) => Promise<void>
  selectedTaskId: string | null

  conversations: AgentConversationSummary[]
  activeConversationId: string | null
  loading: boolean
  onOpen: (conversation: AgentConversationSummary) => void
  onClose: () => void
}) {
  const { text } = useAppLocale()
  const [query, setQuery] = useState('')
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const filtered = conversations.filter((conversation) => (
    conversation.title.toLowerCase().includes(query.trim().toLowerCase())
  ))

  useEffect(() => {
    closeButtonRef.current?.focus()
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  return (
    <div className="new-research__history" role="dialog" aria-modal="true" aria-label={text('研究记录', 'Research history')}>
      <header>
        <div><span>{text('对话记录', 'Conversation history')}</span><strong>{text('继续一个已有问题', 'Continue an existing question')}</strong></div>
        <button ref={closeButtonRef} type="button" aria-label={text('关闭研究记录', 'Close research history')} onClick={onClose}><XIcon size={16} /></button>
      </header>
      <label className="new-research__history-search">
        <MagnifyingGlassIcon size={15} />
        <input aria-label={text('搜索研究记录', 'Search research history')} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={text('搜索问题', 'Search questions')} />
      </label>
      <div className="new-research__history-list">
        <AgentConversationHistoryRail projects={projects} setProjects={setProjects} conversations={filtered} activeConversationId={activeConversationId}
          selectedTaskId={selectedTaskId} loading={loading} onOpen={onOpen}
          onNewConversation={onNewConversation} onRename={onRename} onDelete={onDelete} onDeleteProject={onDeleteProject} />
      </div>
    </div>
  )
}

// 每个工具保留自己的图标，但换掉过于具象的那几个（扳手、地图、书本），
// 统一 light 权重的线条，状态只用颜色区分，和右侧研究面板一个语言。
const toolIcons: Record<string, typeof ArticleIcon> = {
  search_knowledge: MagnifyingGlassIcon,
  read_knowledge_entry: ArticleIcon,
  read_sources: LinkSimpleIcon,
  browse_knowledge_directory: FolderOpenIcon,
  search_research_materials: MagnifyingGlassIcon,
  read_research_material_context: FileTextIcon,
  search_web: GlobeSimpleIcon,
  read_web_page: GlobeSimpleIcon,
  update_research_map: TreeStructureIcon,
  propose_start_research: CompassIcon,
  get_research_workflow_state: CompassIcon,
  start_theory_matching: CirclesThreeIcon,
  save_confirmed_theory_plan: CheckCircleIcon,
  read_research_document: FileTextIcon,
  propose_document_revision: PencilLineIcon,
  propose_document_creation: FilePlusIcon,
}

function ToolLogo({ tool, state }: { tool: string; state?: string }) {
  const ToolIcon = toolIcons[tool] ?? ArticleIcon
  return (
    <span className={`research-agent-tool-logo${state ? ` is-${state}` : ''}`} aria-hidden="true">
      <ToolIcon size={16} weight="light" />
    </span>
  )
}

function StreamingRunStatus({ status, steps }: { status: AgentPageStatus; steps: ResearchToolStep[] }) {
  const { text } = useAppLocale()
  const runningTool = [...steps].reverse().find((step) => step.status === 'running')?.tool
  const phase = runningTool && ['read_knowledge_entry', 'read_sources', 'read_research_document', 'read_research_material_context'].includes(runningTool)
    ? text('正在阅读研究材料', 'Reading research materials')
    : runningTool === 'search_research_materials'
      ? text('正在检索个人材料', 'Searching personal research materials')
      : runningTool && ['search_knowledge', 'browse_knowledge_directory'].includes(runningTool)
      ? text('正在检索知识库', 'Searching the knowledge base')
      : runningTool === 'start_theory_matching'
        ? text('正在比较理论视角', 'Comparing theoretical perspectives')
        : runningTool && ['propose_document_creation', 'propose_document_revision'].includes(runningTool)
          ? text('正在整理研究框架', 'Preparing the research framework')
          : runningTool
            ? text('正在更新研究进度', 'Updating research progress')
            : status === 'answering'
              ? text('正在生成回答', 'Writing the answer')
              : text('正在理解并整理研究问题', 'Understanding and structuring the research question')
  return (
    <p className="new-research__run-status" role="status">
      <strong>{phase}</strong>
    </p>
  )
}

function ToolTraceTimeline({ steps, onOpenActivity }: { steps: ResearchToolStep[]; onOpenActivity: () => void }) {
  const { locale, text } = useAppLocale()
  const running = steps.some((step) => step.status === 'running')
  const interrupted = steps.some((step) => step.interrupted)
  const failed = steps.some((step) => step.status === 'failed' && !step.interrupted)
  const [expanded, setExpanded] = useState(false)

  if (!steps.length) return null
  const statusLabel = running
    ? text('Agent 正在调用工具', 'Agent is using tools')
    : interrupted
      ? text('工具调用已中断', 'Tool activity was interrupted')
      : failed
        ? text('工具调用未完成', 'Tool activity did not complete')
        : text('Agent 已完成工具调用', 'Agent completed its tool activity')

  return (
    <section className={`new-research__trace${expanded ? ' is-expanded' : ''}${running ? ' is-running' : ''}${failed ? ' is-failed' : ''}${interrupted ? ' is-interrupted' : ''}`} aria-label={text('Agent 工作过程', 'Agent activity')}>
      <header className="new-research__trace-header">
        <button
          type="button"
          className="research-agent-tool-summary"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <span className="research-agent-tool-logo-stack" aria-hidden="true">
            {steps.slice(0, 3).map((step) => (
              <ToolLogo key={step.id} tool={step.tool} state={step.interrupted ? 'interrupted' : step.status} />
            ))}
          </span>
          <span className="research-agent-tool-summary__copy">
            <strong>{statusLabel}</strong>
            <small>{text(`${steps.length} 个实际步骤 · 按需使用知识库`, `${steps.length} actual steps · knowledge used as needed`)}</small>
          </span>
          <CaretRightIcon className="research-agent-tool-summary__caret" size={15} aria-hidden="true" />
        </button>
        <button className="research-agent-tool-activity" type="button" onClick={onOpenActivity}>{text('查看活动', 'View activity')}</button>
      </header>
      <ol className="new-research__trace-list" hidden={!expanded}>
        {steps.map((step) => (
          <li key={step.id} className={`new-research__trace-step is-${step.interrupted ? 'interrupted' : step.status}`}>
            <ToolLogo tool={step.tool} state={step.interrupted ? 'interrupted' : step.status} />
            <div>
              <strong>{localizedToolLabel(step.tool, locale, step.label)}</strong>
              <small>{step.interrupted ? text('已中断', 'Interrupted') : step.status === 'running' ? text('进行中', 'In progress') : step.status === 'failed' ? text('失败', 'Failed') : text('已完成', 'Completed')}</small>
              <p className="new-research__trace-purpose">{localizedToolPurpose(step.tool, locale)}</p>
              {step.input ? <p className="new-research__trace-input">{formatToolPayload(step.input)}</p> : null}
              {step.detail ? <ToolDetailDisclosure detail={localizedToolDetail(step.detail, locale)} className="new-research__trace-detail" /> : null}
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
  const { locale, text } = useAppLocale()
  if (!citations.length) return null
  return (
    <div className="new-research__sources" aria-label={text('回答证据', 'Answer evidence')}>
      <span className="new-research__sources-label">{text('依据', 'Evidence')}</span>
      {citations.map((citation, index) => (
        <button type="button" key={citation.citation_id} data-dimension={citationDimension(citation) ?? undefined} onClick={() => onSelect(citation)} aria-label={text(`查看证据：${citation.label}`, `View evidence: ${citation.label}`)}>
          <b>{index + 1}</b><span>{citation.label}<small>{citationKindLabel(citation.kind, locale)}</small></span>
        </button>
      ))}
    </div>
  )
}

function EvidenceOriginSummary({ citations }: { citations: AgentCitation[] }) {
  const { text } = useAppLocale()
  const materialCount = citations.filter((citation) => (
    citation.kind === 'material' || citation.kind === 'research_material'
  )).length
  const knowledgeCount = citations.filter((citation) => (
    Boolean(citation.knowledge_id)
      && citation.kind !== 'material'
      && citation.kind !== 'research_material'
  )).length
  const webCount = citations.filter((citation) => citation.source_kind === 'web').length
  if (!materialCount && !knowledgeCount && !webCount) return null
  // 下面紧跟着的就是逐条依据，这里只需要一句话交代来源构成，不必再占一张卡片。
  const parts = [
    knowledgeCount ? `${text('群学知识库', 'Qunxue knowledge')} ${knowledgeCount}` : null,
    materialCount ? `${text('你的研究材料', 'Your materials')} ${materialCount}` : null,
    webCount ? `${text('公开网页', 'Public web')} ${webCount}` : null,
  ].filter(Boolean)
  return (
    <p
      className="new-research__evidence-origin"
      role="status"
      aria-label={text('本轮证据来源', 'Evidence sources for this answer')}
    >
      {text('本轮引用', 'Cited this turn')} · {parts.join(' · ')}
    </p>
  )
}

function AssistantActions({ content, onRegenerate }: { content: string; onRegenerate: () => void }) {
  const { text } = useAppLocale()
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  async function copyAnswer() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard_unavailable')
      await navigator.clipboard.writeText(displayAgentText(content))
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
    window.setTimeout(() => setCopyState('idle'), 1_600)
  }

  return (
    <div className="new-research__assistant-actions">
      <button
        type="button"
        aria-label={copyState === 'copied' ? text('已复制', 'Copied') : copyState === 'failed' ? text('复制失败', 'Copy failed') : text('复制回答', 'Copy answer')}
        title={copyState === 'copied' ? text('已复制', 'Copied') : copyState === 'failed' ? text('复制失败', 'Copy failed') : text('复制', 'Copy')}
        onClick={() => { void copyAnswer() }}
      >
        {copyState === 'copied' ? <CheckIcon size={16} /> : copyState === 'failed' ? <XCircleIcon size={16} /> : <CopyIcon size={16} />}
      </button>
      <button type="button" aria-label={text('重新生成', 'Regenerate')} title={text('重新生成', 'Regenerate')} onClick={onRegenerate}><ArrowClockwiseIcon size={16} /></button>
    </div>
  )
}

function AssistantTurn({
  question,
  answer,
  citations,
  toolSteps,
  conversationId,
  interrupted,
  failure,
  streaming,
  streamingStatus,
  progressEnd = 0,
  embedded,
  showResearchHandoff,
  knowledgeReleaseId,
  onOpenActivity,
  onSelectCitation,
  onRegenerate,
  onContinueResearch,
  researchEntryBusy,
}: {
  question: string
  answer: string
  citations: AgentCitation[]
  toolSteps: ResearchToolStep[]
  conversationId: string | null
  interrupted?: boolean
  failure?: string
  streaming?: boolean
  streamingStatus?: AgentPageStatus
  progressEnd?: number
  embedded?: boolean
  showResearchHandoff?: boolean
  knowledgeReleaseId: string | null
  onOpenActivity: () => void
  onSelectCitation: (citation: AgentCitation, knowledgeReleaseId: string | null) => void
  onRegenerate?: () => void
  onContinueResearch?: () => void
  researchEntryBusy?: boolean
}) {
  const { text } = useAppLocale()
  const researchHandoff = researchStartHandoffFromSteps(toolSteps)
  const knowledgeHandoffCitation = showResearchHandoff && conversationId && knowledgeReleaseId
    && hasCompletedKnowledgeActivity(toolSteps)
    ? citations.find((citation) => Boolean(citation.knowledge_id)) ?? null
    : null
  const completedStepCount = toolSteps.filter((step) => step.status === 'completed').length
  return (
    <article className={`new-research__turn${streaming ? ' is-streaming' : ''}`}>
      <div className="new-research__user-message" data-role="user-message"><span>{question}</span></div>
      <div className="new-research__assistant-message" data-role="assistant-response">
        <div className="new-research__assistant-label" aria-label={text('群学 Agent', 'Qunxue Agent')}>
          <ResearchAgentBot />
        </div>
        {streaming && streamingStatus ? <StreamingRunStatus status={streamingStatus} steps={toolSteps} /> : null}
        <ToolTraceTimeline steps={toolSteps} onOpenActivity={onOpenActivity} />
        {answer ? <div className="new-research__markdown">
          {progressEnd > 0 ? <ReactMarkdown remarkPlugins={[remarkGfm, remarkProgressParagraphs]}>{displayAgentText(answer.slice(0, progressEnd))}</ReactMarkdown> : null}
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayAgentText(answer.slice(progressEnd))}</ReactMarkdown>
        </div> : null}
        {!streaming && !answer && !interrupted && !failure ? <p className="new-research__thinking" role="status"><CircleNotchIcon size={14} />{text('Agent 正在组织问题与证据…', 'Agent is organizing the question and evidence…')}</p> : null}
        {interrupted ? (
          <p className="qx-notice-surface new-research__turn-note is-interrupted">
            <WarningCircleIcon size={14} />
            {answer.trim() || embedded
              ? text(`本轮已停止，已保留生成内容和 ${completedStepCount} 个已完成步骤。`, `This turn was stopped. Its generated content and ${completedStepCount} completed steps were retained.`)
              : text('本轮已停止，未保存未完成的回答。', 'This turn was stopped before an unfinished answer was saved.')}
          </p>
        ) : null}
        {failure ? <p className="qx-notice-surface new-research__turn-note is-failed"><XCircleIcon size={14} />{failure}</p> : null}
        {(failure || interrupted) && onRegenerate ? (
          <div className="new-research__assistant-actions">
            <button
              type="button"
              aria-label={interrupted ? text('继续研究', 'Continue research') : text('重试本轮', 'Retry this turn')}
              onClick={onRegenerate}
            >
              {interrupted ? <CaretRightIcon size={14} /> : <ArrowClockwiseIcon size={14} />}
              {interrupted ? text('继续研究', 'Continue research') : text('从本轮问题重试', 'Retry this question')}
            </button>
          </div>
        ) : null}
        {!streaming && answer && !citations.length ? (
          <p className="new-research__provenance-note">
            <WarningCircleIcon size={14} />
            {hasKnowledgeActivity(toolSteps)
              ? text('已检索知识库，但没有可展示的来源，请谨慎引用。', 'The knowledge base was searched, but no displayable source was returned. Cite with care.')
              : hasResearchMaterialActivity(toolSteps)
                ? text('已检索个人材料，但没有可展示的原文位置，请谨慎引用。', 'Personal materials were searched, but no displayable source position was returned. Cite with care.')
              : text('未调用知识库 · 以下内容仅作工作假设，请结合材料核验。', 'Knowledge base not searched · treat this as a working hypothesis and verify it against your materials.')}
          </p>
        ) : null}
        <EvidenceOriginSummary citations={citations} />
        <SourcePills citations={citations} onSelect={(citation) => onSelectCitation(citation, knowledgeReleaseId)} />
        {knowledgeHandoffCitation && conversationId && knowledgeReleaseId
          ? <KnowledgeHandoffCards citation={knowledgeHandoffCitation} conversationId={conversationId} knowledgeReleaseId={knowledgeReleaseId} />
          : null}
        {showResearchHandoff && researchHandoff ? <ResearchStartHandoffCard handoff={researchHandoff} onContinueResearch={onContinueResearch} busy={researchEntryBusy} /> : null}
        {!streaming && answer && onRegenerate ? <AssistantActions content={answer} onRegenerate={onRegenerate} /> : null}
      </div>
    </article>
  )
}

type ResearchAgentConversationPageProps = {
  userId: string | null
  embedded?: boolean
  conversationId?: string | null
  knowledgeReleaseId?: string | null
  workspace?: 'agent' | 'research'
  taskId?: string | null
  documentId?: string | null
  sectionId?: string | null
  documentVersion?: number | null
  theoryPlanId?: string | null
  onTurnCompleted?: () => void
  onConversationChange?: (conversation: AgentConversation) => void
  onStreamingTurnChange?: (turn: ResearchCanvasStreamingTurn | null) => void
  conversationTail?: ReactNode
  composerPrefix?: ReactNode
  showConversationManagement?: boolean
  historyRailTarget?: HTMLElement | null
  composerAriaLabel?: string
  suggestedPrompt?: string | null
  suggestedPromptKey?: number
  introSessionId?: string | null
}

export function ResearchAgentConversationPage({
  userId,
  embedded = false,
  conversationId: boundConversationId = null,
  knowledgeReleaseId: boundKnowledgeReleaseId = null,
  workspace: boundWorkspace = 'agent',
  taskId: boundTaskId = null,
  documentId = null,
  sectionId = null,
  documentVersion = null,
  theoryPlanId = null,
  onTurnCompleted,
  onConversationChange,
  onStreamingTurnChange,
  conversationTail,
  composerPrefix,
  showConversationManagement = !embedded,
  historyRailTarget = null,
  composerAriaLabel,
  suggestedPrompt = null,
  suggestedPromptKey = 0,
  introSessionId = null,
}: ResearchAgentConversationPageProps) {
  const { locale, text } = useAppLocale()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedConversationId = embedded ? boundConversationId : searchParams.get('conversation_id')
  const requestedKnowledgeReleaseId = embedded ? boundKnowledgeReleaseId : searchParams.get('knowledge_release_id')
  const restoredPendingTurn = useRef<PendingTurnAttempt | null>(readPendingTurnAttempt(userId))
  const restoredInterruptedTurn = useRef<StreamingTurn | null>(readInterruptedTurn(userId))
  const [draft, setDraft] = useState(() => readStoredDraft(userId) || restoredPendingTurn.current?.question || '')
  const [conversations, setConversations] = useState<AgentConversationSummary[]>([])
  const [activeConversation, setActiveConversation] = useState<AgentConversation | null>(null)
  const taskId = embedded ? boundTaskId : (
    activeConversation?.conversation_id === requestedConversationId && activeConversation.task_id !== undefined
      ? activeConversation.task_id : searchParams.get('task_id')
  )
  const workspace = embedded ? boundWorkspace : taskId ? 'research' : 'agent'
  const [projects, setProjects] = useState<ResearchProject[]>([])
  const [projectListError, setProjectListError] = useState<string | null>(null)
  const projectScopeKey = conversations.map((item) => item.task_id ?? '').join(',')
  useEffect(() => {
    const controller = new AbortController()
    void listResearchProjects(controller.signal).then((items) => {
      if (!controller.signal.aborted) { setProjects(items); setProjectListError(null) }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted && (cause as { name?: string })?.name !== 'AbortError') setProjectListError(text('项目列表暂时无法加载', 'Projects are unavailable'))
    })
    return () => controller.abort()
  }, [projectScopeKey, text])

  const [streamingTurn, setStreamingTurn] = useState<StreamingTurn | null>(restoredInterruptedTurn.current)
  const [toolStepsByTurnId, setToolStepsByTurnId] = useState<Record<string, ResearchToolStep[]>>({})
  const [knowledgeReleaseByConversationId, setKnowledgeReleaseByConversationId] = useState<Record<string, string>>(() => {
    const stored = readStringMap(userId, KNOWLEDGE_RELEASE_STORAGE_KEY)
    return requestedConversationId && requestedKnowledgeReleaseId
      ? { ...stored, [requestedConversationId]: requestedKnowledgeReleaseId }
      : stored
  })
  const [runtimeModeByConversationId, setRuntimeModeByConversationId] = useState<Record<string, AgentRuntimeMode>>(() => readStoredRuntimeModes(userId))
  const [runtimeMode, setRuntimeMode] = useState<AgentRuntimeMode | null>(() => (
    requestedConversationId ? readStoredRuntimeModes(userId)[requestedConversationId] ?? null : null
  ))
  const [status, setStatus] = useState<AgentPageStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(!embedded)
  const [contextOpen, setContextOpen] = useState(false)
  // 研究工作区里内嵌的面板仍然保留这个浮层入口，独立 Agent 页已经由左侧对话记录栏取代它。
  const [historyOpen, setHistoryOpen] = useState(false)
  const closeHistory = useCallback(() => setHistoryOpen(false), [])
  // 用户手动收起研究面板后就不再自动弹出，直到换一段对话。
  const researchPanelDismissed = useRef(false)
  // 收起时先播完退场动画再卸载，所以挂载状态比 contextOpen 多活一小会儿。
  const [railMounted, setRailMounted] = useState(false)
  const [contextTab, setContextTab] = useState<ResearchContextTab>('agent')
  const [materialsOpen, setMaterialsOpen] = useState(false)
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false)
  const [materialPickerLoading, setMaterialPickerLoading] = useState(false)
  const [availableMaterials, setAvailableMaterials] = useState<ResearchMaterial[]>([])
  const materialContextKey = useRef<string | null>(null)
  const uploadTaskId = useRef<string | null>(null)
  const [attachedMaterials, setAttachedMaterials] = useState<ResearchMaterial[]>([])
  const [materialUploading, setMaterialUploading] = useState(false)
  const [materialMenuOpen, setMaterialMenuOpen] = useState(false)
  const [modeMenuOpen, setModeMenuOpen] = useState(false)
  const [composerMode, setComposerMode] = useState<AgentComposerMode>(() => restoredPendingTurn.current?.runId ? 'deep-research' : 'standard')
  const [deepResearchIntroVisible, setDeepResearchIntroVisible] = useState(false)
  const deepResearchIntroShown = useRef(false)
  const [deepResearchMockStage, setDeepResearchMockStage] = useState<DeepResearchMockStage>('idle')
  const [deepResearchMockQuestion, setDeepResearchMockQuestion] = useState('')
  const [deepResearchMockOptions, setDeepResearchMockOptions] = useState<string[]>([])
  const [deepResearchMockStep, setDeepResearchMockStep] = useState(0)
  const [deepResearchElapsedSeconds, setDeepResearchElapsedSeconds] = useState(0)
  const deepResearchStartedAt = useRef<number | null>(null)
  const [deepResearchResult, setDeepResearchResult] = useState<{ summary?: string; knowledgeCount?: number; webCount?: number }>({})
  const deepResearchLifecycleStarted = useRef(false)
  const [reportExportState, setReportExportState] = useState<DeepResearchExportState>('idle')
  const [researchEntryBusy, setResearchEntryBusy] = useState(false)
  const researchEntryAbortController = useRef<AbortController | null>(null)
  const hasDeepResearchMockConversation = deepResearchMockStage !== 'idle'
  const [webSearchEnabled, setWebSearchEnabled] = useState(true)
  const [materialLocatorTarget, setMaterialLocatorTarget] = useState<{ taskId?: string; materialId: string; parseId: string | null; segmentId: string | null } | null>(null)
  const [selectedCitationContext, setSelectedCitationContext] = useState<SelectedCitationContext | null>(null)
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null)
  const [landingBackdropPhase, setLandingBackdropPhase] = useState<'visible' | 'leaving' | 'hidden'>('visible')
  const streamAbortController = useRef<AbortController | null>(null)
  const activeRunId = useRef<string | null>(null)
  const pendingResumeStarted = useRef(false)
  const streamGeneration = useRef(0)
  const conversationLoadAbortController = useRef<AbortController | null>(null)
  const conversationLoadGeneration = useRef(0)
  const pendingToolSteps = useRef<ResearchToolStep[]>([])
  const failedTurnAttempt = useRef<PendingTurnAttempt | null>(restoredPendingTurn.current)
  const activeTurnAttempt = useRef<PendingTurnAttempt | null>(null)
  const materialsOpenRef = useRef(false)
  const locallyDeletedMaterialIds = useRef(new Set<string>())
  const redactedStreamingMaterialIds = useRef(new Set<string>())
  const pendingConversationId = useRef<string | null>(requestedConversationId ?? restoredPendingTurn.current?.conversationId ?? null)
  const loadedConversationId = useRef<string | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const composerInputRef = useRef<HTMLTextAreaElement>(null)
  const materialMenuRef = useRef<HTMLDivElement>(null)
  const materialMenuButtonRef = useRef<HTMLButtonElement>(null)
  const materialFileInputRef = useRef<HTMLInputElement>(null)
  const modeMenuRef = useRef<HTMLDivElement>(null)
  const modeMenuButtonRef = useRef<HTMLButtonElement>(null)

  useLayoutEffect(() => {
    const input = composerInputRef.current
    if (!input) return
    const resize = () => {
      input.style.height = 'auto'
      input.style.height = `${input.scrollHeight}px`
    }
    resize()
    let width = input.clientWidth
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
      if (input.clientWidth === width) return
      width = input.clientWidth
      resize()
    })
    observer?.observe(input)
    return () => observer?.disconnect()
  }, [draft])


  function openMaterials() {
    materialsOpenRef.current = true
    setMaterialsOpen(true)
  }

  function closeMaterials() {
    materialsOpenRef.current = false
    setMaterialsOpen(false)
  }

  useEffect(() => {
    if (!materialMenuOpen) return undefined

    function closeMaterialMenu(event: globalThis.KeyboardEvent | PointerEvent) {
      if (event instanceof globalThis.KeyboardEvent) {
        if (event.key !== 'Escape') return
        setMaterialMenuOpen(false)
        materialMenuButtonRef.current?.focus()
        return
      }
      if (!materialMenuRef.current?.contains(event.target as Node)) setMaterialMenuOpen(false)
    }

    document.addEventListener('keydown', closeMaterialMenu)
    document.addEventListener('pointerdown', closeMaterialMenu)
    return () => {
      document.removeEventListener('keydown', closeMaterialMenu)
      document.removeEventListener('pointerdown', closeMaterialMenu)
    }
  }, [materialMenuOpen])

  useEffect(() => {
    if (!modeMenuOpen) return undefined

    function closeModeMenu(event: globalThis.KeyboardEvent | PointerEvent) {
      if (event instanceof globalThis.KeyboardEvent) {
        if (event.key !== 'Escape') return
        setModeMenuOpen(false)
        modeMenuButtonRef.current?.focus()
        return
      }
      if (!modeMenuRef.current?.contains(event.target as Node)) setModeMenuOpen(false)
    }

    document.addEventListener('keydown', closeModeMenu)
    document.addEventListener('pointerdown', closeModeMenu)
    return () => {
      document.removeEventListener('keydown', closeModeMenu)
      document.removeEventListener('pointerdown', closeModeMenu)
    }
  }, [modeMenuOpen])

  function openResearchMaterials() {
    setMaterialMenuOpen(false)
    if (workspace === 'research' && taskId) {
      setMaterialLocatorTarget(null)
      openMaterials()
      return
    }
    navigate('/research/materials')
  }

  async function openMaterialAttachmentPicker() {
    setMaterialMenuOpen(false)
    setMaterialPickerOpen(true)
    setMaterialPickerLoading(true)
    try {
      setAvailableMaterials(await listAgentMaterials())
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : text('研究材料暂时无法加载。', 'Research materials are unavailable.'))
      setMaterialPickerOpen(false)
    } finally {
      setMaterialPickerLoading(false)
    }
  }

  function toggleAttachedMaterial(material: ResearchMaterial) {
    if (material.status !== 'ready') return
    setAttachedMaterials((current) => {
      if (current.some((item) => item.materialId === material.materialId)) {
        return current.filter((item) => item.materialId !== material.materialId)
      }
      if (current.length >= 20) {
        setError(text('每轮最多附加 20 份研究材料。', 'You can attach up to 20 research materials per turn.'))
        return current
      }
      return [...current, material]
    })
  }

  async function uploadComposerMaterials(files: File[]) {
    if (!files.length || materialUploading) return
    const generation = conversationLoadGeneration.current
    const unsupported = files.find((file) => !isSupportedResearchMaterialFile(file))
    if (unsupported) {
      setError(text(`不支持“${unsupported.name}”的文件格式。`, `The file type for “${unsupported.name}” is not supported.`))
      return
    }
    const remaining = Math.max(0, 20 - attachedMaterials.length)
    if (files.length > remaining) {
      setError(text('每轮最多附加 20 份研究材料。', 'You can attach up to 20 research materials per turn.'))
      return
    }
    setMaterialUploading(true)
    setError(null)
    try {
      let destinationTaskId = taskId ?? uploadTaskId.current
      if (!destinationTaskId) {
        const context = await prepareAgentMaterialContext(
          activeConversation?.conversation_id ?? pendingConversationId.current, materialContextKey.current ??= crypto.randomUUID(),
        )
        if (generation !== conversationLoadGeneration.current) return
        pendingConversationId.current = context.conversation_id
        uploadTaskId.current = context.task_id
        destinationTaskId = context.task_id
      }
      for (const file of files) {
        const material = await addResearchLibraryMaterial(destinationTaskId, file)
        if (generation !== conversationLoadGeneration.current) return
        setAttachedMaterials((current) => [...current.filter((item) => item.materialId !== material.materialId), material])
        setAvailableMaterials((current) => [material, ...current.filter((item) => item.materialId !== material.materialId)])
      }
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : text('研究材料上传失败。', 'Research material upload failed.'))
    } finally {
      setMaterialUploading(false)
      if (materialFileInputRef.current) materialFileInputRef.current.value = ''
    }
  }
  const pendingAttachedMaterials = attachedMaterials
    .filter((material) => material.ingestionStatus === 'queued' || material.ingestionStatus === 'processing')
    .map((material) => `${material.taskId}/${material.materialId}`).join(',')

  useEffect(() => {
    if (!pendingAttachedMaterials) return undefined
    let active = true
    let running = false
    const refresh = async () => {
      if (running) return
      running = true
      const results = await Promise.allSettled(pendingAttachedMaterials.split(',').map((key) => {
        const [sourceTaskId, materialId] = key.split('/')
        return getAgentAttachmentMaterial(sourceTaskId, materialId)
      }))
      running = false
      if (!active) return
      const byId = new Map(results.flatMap((result) => result.status === 'fulfilled' ? [[result.value.materialId, result.value] as const] : []))
      setAttachedMaterials((current) => current.map((item) => byId.get(item.materialId) ?? item))
    }
    const timer = window.setInterval(() => { void refresh() }, 1000)
    return () => { active = false; window.clearInterval(timer) }
  }, [pendingAttachedMaterials])

  const turns = useMemo(() => activeConversation?.turns ?? [], [activeConversation])
  const canStopGeneration = status === 'thinking' || status === 'retrieving' || status === 'answering'
  const isBusy = status === 'loading' || canStopGeneration
  const canSubmit = draft.trim().length > 0
    && !isBusy
    && !researchEntryBusy
    && !materialUploading
    && attachedMaterials.every((material) => material.status === 'ready')
  const isEmpty = !turns.length && !streamingTurn && !hasDeepResearchMockConversation

  useEffect(() => {
    if (embedded || !isEmpty || composerMode !== 'standard' || deepResearchIntroShown.current) return undefined
    if (introSessionId && window.localStorage.getItem(DEEP_RESEARCH_INTRO_SESSION_KEY) === introSessionId) return undefined
    deepResearchIntroShown.current = true
    if (introSessionId) window.localStorage.setItem(DEEP_RESEARCH_INTRO_SESSION_KEY, introSessionId)
    setDeepResearchIntroVisible(true)
    const timeout = window.setTimeout(
      () => setDeepResearchIntroVisible(false),
      introSessionId ? DEEP_RESEARCH_INTRO_TIMEOUT_MS : 5000,
    )
    return () => window.clearTimeout(timeout)
  }, [composerMode, embedded, introSessionId, isEmpty])

  useEffect(() => {
    onStreamingTurnChange?.(streamingTurn)
  }, [onStreamingTurnChange, streamingTurn])

  useEffect(() => {
    if (!suggestedPrompt) return
    updateDraft(suggestedPrompt)
    globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
  }, [suggestedPrompt, suggestedPromptKey])

  useEffect(() => {
    if (isEmpty) {
      setLandingBackdropPhase('visible')
      return
    }
    setLandingBackdropPhase((current) => current === 'hidden' ? 'hidden' : 'leaving')
    const timeout = window.setTimeout(() => setLandingBackdropPhase('hidden'), 680)
    return () => window.clearTimeout(timeout)
  }, [isEmpty])

  function updateDraft(value: string) {
    setDraft(value)
    persistDraft(userId, value)
  }

  async function revealFirstStreamingTurn(turn: StreamingTurn) {
    const transitionDocument = document as Document & {
      startViewTransition?: (update: () => void) => { ready: Promise<void> }
    }
    const reducedMotion = typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const homeBot = document.querySelector(
      '.research-agent-conversation.is-empty .research-agent-page__empty-copy [data-research-agent-bot]',
    )
    if (!homeBot || reducedMotion || !transitionDocument.startViewTransition) {
      setStreamingTurn(turn)
      return
    }

    let updated = false
    try {
      const transition = transitionDocument.startViewTransition(() => {
        updated = true
        flushSync(() => setStreamingTurn(turn))
      })
      await transition.ready
    } catch {
      if (!updated) setStreamingTurn(turn)
    }
  }

  const rememberKnowledgeRelease = useCallback((conversationId: string, releaseId: string) => {
    if (!conversationId || !releaseId) return
    setKnowledgeReleaseByConversationId((current) => {
      const next = { ...current, [conversationId]: releaseId }
      persistStringMap(userId, KNOWLEDGE_RELEASE_STORAGE_KEY, next)
      return next
    })
  }, [userId])

  const rememberRuntimeMode = useCallback((conversationId: string, mode: AgentRuntimeMode) => {
    if (!conversationId) return
    setRuntimeModeByConversationId((current) => {
      const next = { ...current, [conversationId]: mode }
      persistStringMap(userId, AGENT_RUNTIME_STORAGE_KEY, next)
      return next
    })
  }, [userId])

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
      const persistedReleaseId = [...conversation.turns]
        .reverse()
        .map((turn) => turn.knowledge_release_id?.trim() || null)
        .find((releaseId): releaseId is string => Boolean(releaseId)) || null
      const releaseId = knowledgeReleaseByConversationId[conversationId]
        || (conversationId === requestedConversationId ? requestedKnowledgeReleaseId : null)
        || persistedReleaseId
      setActiveConversation(conversation)
      onConversationChange?.(conversation)
      setRuntimeMode(runtimeModeByConversationId[conversationId] ?? null)
      loadedConversationId.current = conversationId
      pendingConversationId.current = conversationId
      if (releaseId) rememberKnowledgeRelease(conversationId, releaseId)
      if (!embedded) {
        setSearchParams((current) => {
          const next = new URLSearchParams(current)
          next.set('conversation_id', conversationId)
          if (releaseId) next.set('knowledge_release_id', releaseId)
          else next.delete('knowledge_release_id')
          return next
        }, { replace: true })
      }
    } catch (cause: unknown) {
      if (controller.signal.aborted || requestGeneration !== conversationLoadGeneration.current) return
      if ((cause as { name?: string } | null)?.name !== 'AbortError') {
        setError(text('这段对话暂时无法打开。你可以从一个新问题继续。', 'This conversation cannot be opened right now. You can continue with a new question.'))
      }
    } finally {
      if (!controller.signal.aborted && requestGeneration === conversationLoadGeneration.current) setStatus('idle')
      if (conversationLoadAbortController.current === controller) conversationLoadAbortController.current = null
    }
  }, [activeConversation?.conversation_id, embedded, knowledgeReleaseByConversationId, onConversationChange, rememberKnowledgeRelease, requestedConversationId, requestedKnowledgeReleaseId, runtimeModeByConversationId, setSearchParams])

  useEffect(() => {
    if (!showConversationManagement) {
      setHistoryLoading(false)
      return undefined
    }
    const controller = new AbortController()
    listAgentConversations(controller.signal)
      .then((items) => setConversations(items))
      .catch((cause: unknown) => {
        if ((cause as { name?: string } | null)?.name !== 'AbortError' && !controller.signal.aborted) {
          setError(text('对话记录暂时无法加载，但你仍然可以开始新对话。', 'Conversation history is unavailable, but you can still start a new conversation.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false)
      })
    return () => controller.abort()
  }, [showConversationManagement, text])

  useEffect(() => {
    if (requestedConversationId) void loadConversation(requestedConversationId)
    else {
      conversationLoadAbortController.current?.abort()
      conversationLoadGeneration.current += 1
      setStatus((current) => current === 'loading' ? 'idle' : current)
    }
  }, [loadConversation, requestedConversationId])

  useEffect(() => {
    const endpoint = transcriptEndRef.current
    if (endpoint && typeof endpoint.scrollIntoView === 'function') {
      endpoint.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [streamingTurn?.answer, streamingTurn?.toolSteps.length, turns.length])

  useEffect(() => () => {
    researchEntryAbortController.current?.abort()
    const runId = activeRunId.current
    if (runId) void stopAgentRun(runId).catch(() => undefined)
    streamGeneration.current += 1
    streamAbortController.current?.abort()
    conversationLoadGeneration.current += 1
    conversationLoadAbortController.current?.abort()
  }, [])

  function cancelActiveStream() {
    researchEntryAbortController.current?.abort()
    researchEntryAbortController.current = null
    setResearchEntryBusy(false)
    const runId = activeRunId.current
    if (runId) {
      void stopAgentRun(runId).catch(() => undefined)
      settleInterruptedTurn()
    }
    activeRunId.current = null
    streamGeneration.current += 1
    streamAbortController.current?.abort()
    streamAbortController.current = null
    pendingToolSteps.current = []
    failedTurnAttempt.current = null
    activeTurnAttempt.current = null
    if (!runId) {
      persistPendingTurnAttempt(userId, null)
      persistInterruptedTurn(userId, null)
    }
    setStreamingTurn(null)
  }

  function prepareConversationSwitch() {
    setAttachedMaterials([])
    setAvailableMaterials([])
    setMaterialPickerOpen(false)
    uploadTaskId.current = null
    materialContextKey.current = null
    cancelActiveStream()
    resetDeepResearchMock()
    conversationLoadAbortController.current?.abort()
    conversationLoadGeneration.current += 1
    loadedConversationId.current = null
    pendingConversationId.current = null
    setActiveConversation(null)
    setRuntimeMode(null)
    setToolStepsByTurnId({})
    setAttachedMaterials([])
    setAvailableMaterials([])
    setMaterialPickerOpen(false)
    setSelectedCitationContext(null)
    setSelectedActivityId(null)
    setContextOpen(false)
    setContextTab('agent')
    researchPanelDismissed.current = false
    closeMaterials()
    setMaterialLocatorTarget(null)
  }

  function openConversation(summary: AgentConversationSummary) {
    if (location.pathname !== '/research/new' && embedded) {
      const next = new URLSearchParams({ conversation_id: summary.conversation_id })
      if (summary.task_id) next.set('task_id', summary.task_id)
      navigate(`/research/new?${next}`)
      return
    }
    prepareConversationSwitch()
    setHistoryOpen(false)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('conversation_id', summary.conversation_id)
      if (summary.task_id) next.set('task_id', summary.task_id)
      else next.delete('task_id')
      next.delete('knowledge_release_id')
      return next
    }, { replace: true })
  }

  async function renameSavedConversation(
    summary: AgentConversationSummary,
    title: string,
  ) {
    const updated = await renameAgentConversation(summary.conversation_id, title)
    setConversations((current) => current.map((conversation) => (
      conversation.conversation_id === updated.conversation_id ? updated : conversation
    )))
    setActiveConversation((current) => current?.conversation_id === updated.conversation_id
      ? { ...current, title: updated.title, updated_at: updated.updated_at }
      : current)
  }

  async function deleteSavedConversation(summary: AgentConversationSummary) {
    await deleteAgentConversation(summary.conversation_id)
    setConversations((current) => current.filter((conversation) => (
      conversation.conversation_id !== summary.conversation_id
    )))
    if (
      activeConversation?.conversation_id === summary.conversation_id
      || requestedConversationId === summary.conversation_id
    ) {
      newConversation()
    }
  }

  async function deleteSavedProject(projectId: string) {
    if (taskId === projectId && (isBusy || materialUploading)) throw new Error(text('请先结束当前回答或材料上传，再删除项目', 'Finish the current answer or upload before deleting this project'))
    await deleteResearchProject(projectId)
    setProjects((current) => current.filter((project) => project.task_id !== projectId))
    setConversations((current) => current.map((conversation) => conversation.task_id === projectId
      ? { ...conversation, task_id: null } : conversation))
    setActiveConversation((current) => current?.task_id === projectId ? { ...current, task_id: null } : current)
    if (taskId === projectId) {
      setAttachedMaterials([])
      if (embedded) {
        navigate(requestedConversationId ? `/agent?conversation_id=${encodeURIComponent(requestedConversationId)}` : '/agent')
      } else {
        setSearchParams((current) => {
          const next = new URLSearchParams(current)
          next.delete('task_id')
          return next
        }, { replace: true })
      }
    }
  }

  function newConversation(projectId?: string) {
    if (location.pathname !== '/research/new' && embedded) {
      navigate(projectId ? `/research/new?task_id=${encodeURIComponent(projectId)}` : '/research/new')
      return
    }
    prepareConversationSwitch()
    updateDraft('')
    setError(null)
    setStatus('idle')
    setHistoryOpen(false)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('conversation_id')
      next.delete('knowledge_release_id')
      if (projectId) next.set('task_id', projectId)
      else next.delete('task_id')
      return next
    }, { replace: true })
    globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
  }

  function switchComposerProject(projectId: string) {
    const pendingDraft = !activeConversation?.turn_count ? draft : ''
    newConversation(projectId || undefined)
    if (pendingDraft) updateDraft(pendingDraft)
  }

  async function continueResearch() {
    const conversation = activeConversation
    if (!conversation || isBusy || materialUploading || attachedMaterials.some((material) => material.status !== 'ready') || researchEntryAbortController.current) return
    const controller = new AbortController()
    researchEntryAbortController.current = controller
    setResearchEntryBusy(true)
    setError(null)
    try {
      let journey = await getResearchStartJourney(conversation.conversation_id, controller.signal)
      if (controller.signal.aborted) return
      let completed = conversation
      if (!journey.proposal && !journey.phenomenonConfirmed) {
        // 两个入口都走普通 Agent 的同一工具，深入研究仅在已有对话中多一份调研参照。
        const hasResearchReference = conversation.turns.some((turn) => deepResearchRecord(turn))
        const prompt = '请基于这段对话整理待确认的研究起点，包括现象、研究意图与情境，等待我确认。不要重新运行深入研究，不要替我确认或开展理论匹配。'
          + (hasResearchReference ? '前面已完成的调研报告及其引用是参考资料，请沿用已有成果和来源，不要从零追问，也不要把初步结论当作我已确认的研究判断。' : '')
        setComposerMode('standard')
        const retryKey = failedTurnAttempt.current?.question === prompt ? failedTurnAttempt.current.idempotencyKey : undefined
        const result = await submitQuestion(prompt, retryKey, undefined, true)
        if (!result || controller.signal.aborted) return
        completed = result
        journey = await getResearchStartJourney(conversation.conversation_id, controller.signal)
      }
      if (controller.signal.aborted) return
      if (!journey.proposal && !journey.phenomenonConfirmed) {
        setError('尚未形成待确认的研究起点，请根据 Agent 的回复补充信息后再继续。')
        return
      }
      const releaseId = journey.knowledgeReleaseId || completed.turns.at(-1)?.knowledge_release_id
        || knowledgeReleaseByConversationId[conversation.conversation_id] || requestedKnowledgeReleaseId
      const query = new URLSearchParams({ conversation_id: conversation.conversation_id })
      if (releaseId) query.set('knowledge_release_id', releaseId)
      if (journey.taskId) query.set('task_id', journey.taskId)
      navigate(`/research/new?${query.toString()}`)
    } catch (cause: unknown) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '研究起点暂时无法恢复，请重试。')
    } finally {
      if (researchEntryAbortController.current === controller) {
        researchEntryAbortController.current = null
        setResearchEntryBusy(false)
      }
    }
  }

  async function submitQuestion(rawQuestion: string, retryIdempotencyKey?: string, deepAction?: { action: 'clarify' | 'confirm' | 'skip'; selection?: string }, researchEntry = false): Promise<AgentConversation | null> {
    const question = rawQuestion.trim()
    if (!question || isBusy || (!researchEntry && researchEntryAbortController.current)) return null
    const turnMode = researchEntry ? 'standard' : composerMode
    let resultConversation: AgentConversation | null = null
    const idempotencyKey = retryIdempotencyKey
      ?? globalThis.crypto?.randomUUID?.()
      ?? `agent-${Date.now()}`
    const resumableAttempt = failedTurnAttempt.current?.idempotencyKey === idempotencyKey
      ? failedTurnAttempt.current
      : activeTurnAttempt.current?.idempotencyKey === idempotencyKey
        ? activeTurnAttempt.current
        : null
    const attempt: PendingTurnAttempt = {
      question,
      idempotencyKey,
      conversationId: activeConversation?.conversation_id ?? pendingConversationId.current,
      runId: resumableAttempt?.runId ?? null,
      materialIds: resumableAttempt?.materialIds ?? attachedMaterials.map((item) => item.materialId),
    }
    activeTurnAttempt.current = attempt
    failedTurnAttempt.current = null
    persistInterruptedTurn(userId, null)
    persistPendingTurnAttempt(userId, attempt)
    updateDraft('')
    setError(null)
    setStatus('thinking')
    pendingToolSteps.current = []
    redactedStreamingMaterialIds.current.clear()
    const firstStreamingTurn: StreamingTurn = { question, answer: '', citations: [], toolSteps: [], canvasPatches: [], startedAt: Date.now() }
    if (isEmpty) await revealFirstStreamingTurn(firstStreamingTurn)
    else setStreamingTurn(firstStreamingTurn)
    const controller = new AbortController()
    const runGeneration = streamGeneration.current + 1
    streamGeneration.current = runGeneration
    streamAbortController.current = controller

    try {
      await streamAgentTurn(
        {
          conversation_id: activeConversation?.conversation_id ?? pendingConversationId.current,
          message: question,
          mode: turnMode === 'deep-research' ? 'deep_research' : 'standard',
          idempotencyKey,
          workspace,
          web_search: webSearchEnabled,
          task_id: workspace === 'research' ? taskId : null,
          document_id: workspace === 'research' ? documentId : null,
          section_id: workspace === 'research' ? sectionId : null,
          document_version: workspace === 'research' ? documentVersion : null,
          theory_plan_id: workspace === 'research' ? theoryPlanId : null,
          material_ids: attempt.materialIds,
          deep_research_run_id: deepAction ? (activeTurnAttempt.current?.runId ?? null) : null,
          deep_research_action: deepAction?.action ?? null,
          deep_research_selection: deepAction?.selection ?? null,
        },
        (event: AgentEvent) => {
          if (streamGeneration.current !== runGeneration) return
          if (event.type === 'turn_started') {
            activeRunId.current = event.run_id
            pendingConversationId.current = event.conversation_id
            const startedAttempt = {
              ...attempt,
              conversationId: event.conversation_id,
              runId: event.run_id,
            }
            activeTurnAttempt.current = startedAttempt
            persistPendingTurnAttempt(userId, startedAttempt)
            if (event.runtime_mode) {
              setRuntimeMode(event.runtime_mode)
              rememberRuntimeMode(event.conversation_id, event.runtime_mode)
            }
            if (event.replayed) {
              pendingToolSteps.current = []
              setStreamingTurn((current) => current ? {
                ...current,
                answer: '',
                citations: [],
                toolSteps: [],
                canvasPatches: [],
              } : current)
            }
            setStatus('thinking')
          } else if (event.type === 'agent_status') {
            setStatus(event.status === 'answering' ? 'answering' : 'thinking')
          } else if (event.type === 'research_ask') {
            deepResearchLifecycleStarted.current = true
            setDeepResearchMockQuestion(event.question)
            setDeepResearchMockOptions(event.options)
            setDeepResearchMockStep(0)
            setDeepResearchMockStage('clarifying')
          } else if (event.type === 'research_plan') {
            deepResearchLifecycleStarted.current = true
            setDeepResearchMockQuestion(event.title)
            setDeepResearchMockOptions(event.steps)
            setDeepResearchMockStep(0)
            setDeepResearchMockStage('planning')
          } else if (event.type === 'research_step') {
            deepResearchLifecycleStarted.current = true
            setDeepResearchMockStage('researching')
            setDeepResearchMockStep(Math.min(Math.max(0, DEEP_RESEARCH_MOCK_STEPS.indexOf(event.step)), DEEP_RESEARCH_MOCK_STEPS.length - 1))
          } else if (event.type === 'research_result') {
            deepResearchLifecycleStarted.current = true
            setDeepResearchResult({ summary: event.summary, knowledgeCount: event.knowledge_count, webCount: event.web_count })
            settleDeepResearchElapsed()
            setDeepResearchMockStage('completed')
          } else if (event.type === 'tool_started' || event.type === 'tool_finished' || event.type === 'tool_failed') {
            const next = updateToolSteps(pendingToolSteps.current, event)
            pendingToolSteps.current = next
            if (turnMode === 'deep-research' && event.type === 'tool_started') {
              if (deepResearchStartedAt.current === null) deepResearchStartedAt.current = Date.now()
              setDeepResearchMockStage('researching')
              setDeepResearchMockStep(researchStepForTools(next))
            }
            setStatus(event.type === 'tool_started' ? 'retrieving' : 'thinking')
            // 工具开始前的文字是阶段说明；之后的最终回答仍保留原段落。
            setStreamingTurn((current) => current ? {
              ...current,
              toolSteps: next,
              progressEnd: event.type === 'tool_started' ? current.answer.length : current.progressEnd,
            } : current)
          } else if (event.type === 'assistant_delta') {
            setStatus('answering')
            if (!redactedStreamingMaterialIds.current.size) {
              setStreamingTurn((current) => current ? { ...current, answer: current.answer + event.delta } : current)
            }
          } else if (event.type === 'citation_added') {
            const materialId = materialCitationFields(event.citation).materialId
            const citation = materialId && locallyDeletedMaterialIds.current.has(materialId)
              ? tombstoneMaterialCitation(event.citation, materialId)
              : event.citation
            if (materialId && citation.deleted) redactedStreamingMaterialIds.current.add(materialId)
            setStreamingTurn((current) => current ? {
              ...current,
              answer: citation.deleted ? DELETED_MATERIAL_ANSWER : current.answer,
              citations: [...current.citations, citation],
            } : current)
          } else if (event.type === 'research_waiting') {
            deepResearchLifecycleStarted.current = true
            activeRunId.current = event.run_id
            const waitingAttempt = { ...(activeTurnAttempt.current ?? attempt), runId: event.run_id }
            activeTurnAttempt.current = waitingAttempt
            persistPendingTurnAttempt(userId, waitingAttempt)
            setDeepResearchMockQuestion(event.question ?? event.title ?? question)
            setDeepResearchMockOptions(event.options ?? event.steps ?? [])
            setDeepResearchMockStep(0)
            setDeepResearchMockStage(event.state === 'awaiting_clarification' ? 'clarifying' : 'planning')
            // Keep the question card in the transcript while waiting for the
            // user's answer; it is part of the conversation history.
            setStatus('idle')
          } else if (event.type === 'canvas_patch') {
            setStreamingTurn((current) => current ? { ...current, canvasPatches: [...current.canvasPatches, event.patch] } : current)
          } else if (event.type === 'turn_completed') {
            if (turnMode === 'deep-research' && deepResearchLifecycleStarted.current) {
              settleDeepResearchElapsed()
              setDeepResearchMockStage('completed')
            }
            else if (turnMode === 'deep-research') resetDeepResearchMock()
            activeRunId.current = null
            failedTurnAttempt.current = null
            activeTurnAttempt.current = null
            persistPendingTurnAttempt(userId, null)
            persistInterruptedTurn(userId, null)
            persistDraft(userId, '')
            const localToolSteps = pendingToolSteps.current
            const completedConversation = [...locallyDeletedMaterialIds.current].reduce(
              (conversation, materialId) => tombstoneConversationMaterial(conversation, materialId),
              attachLocalToolSteps(event.conversation, localToolSteps),
            )
            resultConversation = completedConversation
            const completedTurn = completedConversation.turns.at(-1)
            const releaseId = event.knowledge_release_id.trim()
            if (releaseId) rememberKnowledgeRelease(completedConversation.conversation_id, releaseId)
            if (completedTurn && localToolSteps.length) {
              setToolStepsByTurnId((current) => ({ ...current, [completedTurn.turn_id]: localToolSteps }))
            }
            pendingToolSteps.current = []
            redactedStreamingMaterialIds.current.clear()
            setActiveConversation(completedConversation)
            onConversationChange?.(completedConversation)
            loadedConversationId.current = completedConversation.conversation_id
            pendingConversationId.current = completedConversation.conversation_id
            setConversations((current) => [
              {
                task_id: completedConversation.task_id ?? null,
                conversation_id: completedConversation.conversation_id,
                title: completedConversation.title,
                updated_at: completedConversation.updated_at,
                turn_count: completedConversation.turn_count,
              },
              ...current.filter((item) => item.conversation_id !== completedConversation.conversation_id),
            ])
            setStreamingTurn(null)
            setAttachedMaterials([])
            setStatus('idle')
            if (!embedded) {
              setSearchParams((current) => {
                const next = new URLSearchParams(current)
                next.set('conversation_id', completedConversation.conversation_id)
                if (releaseId) next.set('knowledge_release_id', releaseId)
                else next.delete('knowledge_release_id')
                return next
              }, { replace: true })
            }
            onTurnCompleted?.()
          } else if (event.type === 'turn_interrupted') {
            activeRunId.current = null
            settleInterruptedTurn()
          } else if (event.type === 'turn_failed') {
            activeRunId.current = null
            const failedAttempt = { ...(activeTurnAttempt.current ?? attempt), runId: null }
            failedTurnAttempt.current = failedAttempt
            activeTurnAttempt.current = null
            persistPendingTurnAttempt(userId, failedAttempt)
            updateDraft(question)
            const failureMessage = localizedTurnFailure(event.code, event.message, locale)
            setStreamingTurn((current) => {
              if (!current) return current
              const failedTurn = { ...current, interrupted: true, failure: failureMessage }
              persistInterruptedTurn(userId, failedTurn)
              return failedTurn
            })
            setError(failureMessage)
            setStatus('error')
          }
        },
        controller.signal,
      )
    } catch (cause: unknown) {
      if (!controller.signal.aborted && streamGeneration.current === runGeneration) {
        const causeMessage = cause instanceof Error ? cause.message : ''
        const message = locale === 'en-US'
          ? (causeMessage.includes('完成前中断')
              ? 'The connection ended before the answer completed. Retry this turn; no answer has been fabricated.'
              : 'The Agent is unavailable. Check the model service and retry; no answer has been fabricated.')
          : causeMessage.includes('完成前中断')
            ? '连接在回答完成前中断。请重试，这一轮不会伪造回答。'
            : causeMessage && causeMessage !== 'Agent 暂时无法连接'
              ? causeMessage
              : 'Agent 暂时无法连接。请检查模型服务后重试，这一轮不会伪造回答。'
        const failedAttempt = { ...(activeTurnAttempt.current ?? attempt), runId: null }
        failedTurnAttempt.current = failedAttempt
        activeTurnAttempt.current = null
        persistPendingTurnAttempt(userId, failedAttempt)
        updateDraft(question)
        setStreamingTurn((current) => current ? { ...current, failure: message } : current)
        setError(message)
        setStatus('error')
      }
    } finally {
      if (streamAbortController.current === controller) streamAbortController.current = null
    }
    return controller.signal.aborted || streamGeneration.current !== runGeneration ? null : resultConversation
  }

  useEffect(() => {
    if (pendingResumeStarted.current) return
    if (restoredInterruptedTurn.current) return
    const pending = restoredPendingTurn.current
    if (!pending?.runId) return
    pendingResumeStarted.current = true
    void submitQuestion(pending.question, pending.idempotencyKey)
    // A persisted run is resumed only on mount; conversation state changes must not resubmit it.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (deepResearchMockStage !== 'researching' || deepResearchStartedAt.current === null) return undefined
    const updateElapsed = () => setDeepResearchElapsedSeconds(Math.max(0, Math.floor((Date.now() - (deepResearchStartedAt.current ?? Date.now())) / 1000)))
    updateElapsed()
    const timer = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(timer)
  }, [deepResearchMockStage])

  function submitDraft() {
    const normalized = draft.trim()
    const attempt = failedTurnAttempt.current
    void submitQuestion(normalized, attempt?.question === normalized ? attempt.idempotencyKey : undefined)
  }

  // 计时器一秒一跳，收尾时按真实起止时间再算一次，卡片上不会出现少一秒的用时。
  function settleDeepResearchElapsed() {
    const startedAt = deepResearchStartedAt.current
    if (startedAt === null) return
    setDeepResearchElapsedSeconds(Math.max(1, Math.round((Date.now() - startedAt) / 1000)))
  }

  async function exportResearchReport(kind: 'docx' | 'pdf') {
    const conversation = activeConversation
    if (!conversation || reportExportState !== 'idle') return
    setReportExportState(kind)
    try {
      const report = buildResearchReport({
        conversation,
        elapsedSeconds: deepResearchElapsedSeconds,
        fallbackTitle: deepResearchMockQuestion,
      })
      if (kind === 'pdf') {
        openResearchReportPrintWindow(report)
        return
      }
      const blob = await createResearchReportDocx(report)
      const url = URL.createObjectURL(blob)
      const anchor = globalThis.document.createElement('a')
      anchor.href = url
      anchor.download = researchReportDocxFilename(report)
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '导出研究报告失败，请重试。')
    } finally {
      setReportExportState('idle')
    }
  }

  function resetDeepResearchMock() {
    setDeepResearchMockStage('idle')
    setDeepResearchMockQuestion('')
    setDeepResearchMockOptions([])
    setDeepResearchMockStep(0)
    setDeepResearchResult({})
    setDeepResearchElapsedSeconds(0)
    deepResearchStartedAt.current = null
    deepResearchLifecycleStarted.current = false
  }

  function continueDeepResearch(action: 'clarify' | 'confirm' | 'skip', selection?: string) {
    const attempt = activeTurnAttempt.current
    if (!attempt?.runId) return
    if (action === 'confirm') {
      deepResearchLifecycleStarted.current = true
      deepResearchStartedAt.current = Date.now()
      setDeepResearchElapsedSeconds(0)
      setDeepResearchMockStage('researching')
      setDeepResearchMockStep(0)
    }
    void submitQuestion(attempt.question, attempt.idempotencyKey, { action, selection })
  }

  function retryFailedTurn(question: string) {
    const attempt = failedTurnAttempt.current
    void submitQuestion(question, attempt?.question === question ? attempt.idempotencyKey : undefined)
  }

  function settleInterruptedTurn({ resumable = true }: { resumable?: boolean } = {}) {
    const attempt = activeTurnAttempt.current
    if (attempt && resumable) {
      failedTurnAttempt.current = attempt
      activeTurnAttempt.current = null
      persistPendingTurnAttempt(userId, attempt)
      updateDraft(attempt.question)
    } else if (attempt) {
      failedTurnAttempt.current = null
      activeTurnAttempt.current = null
      persistPendingTurnAttempt(userId, null)
      updateDraft(attempt.question)
    }
    const next = interruptedSteps(pendingToolSteps.current, locale)
    pendingToolSteps.current = next
    setStreamingTurn((current) => {
      if (!current) return current
      const interruptedTurn = { ...current, interrupted: true, toolSteps: next, failure: undefined }
      persistInterruptedTurn(userId, interruptedTurn)
      return interruptedTurn
    })
    setStatus('idle')
  }

  function stopGeneration() {
    const runId = activeRunId.current
    activeRunId.current = null
    if (runId) {
      void stopAgentRun(runId).catch(() => {
        setError(text('停止请求未被服务端确认，请稍后重试。', 'The server did not confirm the stop request. Try again.'))
      })
    }
    streamGeneration.current += 1
    streamAbortController.current?.abort()
    streamAbortController.current = null
    resetDeepResearchMock()
    settleInterruptedTurn({ resumable: false })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitDraft()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submitDraft()
    }
  }

  function choosePrompt(question: string) {
    updateDraft(question)
    globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
  }

  const allToolSteps = useMemo(() => {
    const values = [
      ...turns.flatMap((turn) => toolStepsByTurnId[turn.turn_id] ?? persistedToolSteps(turn.tool_traces)),
      ...(streamingTurn?.toolSteps ?? []),
    ]
    return [...new Map(values.map((step) => [step.id, step])).values()]
  }, [streamingTurn?.toolSteps, toolStepsByTurnId, turns])
  const activities = useMemo(() => allToolSteps.map((step) => toActivity(step, locale)), [allToolSteps, locale])
  const citationContexts = useMemo(() => {
    const conversationReleaseId = activeConversation?.conversation_id
      ? knowledgeReleaseByConversationId[activeConversation.conversation_id] ?? null
      : null
    const values: SelectedCitationContext[] = turns.flatMap((turn) => turn.assistant.citations.map((citation) => ({
      citation,
      knowledgeReleaseId: turn.knowledge_release_id?.trim() || (embedded ? conversationReleaseId : null),
    })))
    values.push(...(streamingTurn?.citations ?? []).map((citation) => ({ citation, knowledgeReleaseId: null })))
    return [...new Map(values.map((context) => [context.citation.citation_id, context])).values()]
  }, [activeConversation?.conversation_id, embedded, knowledgeReleaseByConversationId, streamingTurn?.citations, turns])
  const citations = useMemo(() => citationContexts.map((context) => context.citation), [citationContexts])

  // 深入研究是这段对话的既成事实，重开时要连卡片带输入器模式一起回来；只认最后一轮，
  // 后面接了普通提问就不该再把研究完成卡片挂在末尾。
  useEffect(() => {
    if (streamingTurn) return
    const record = deepResearchRecord(turns.at(-1))
    if (!record) return
    deepResearchLifecycleStarted.current = true
    // 恢复历史报告只改变展示，研究画布仍使用共同的协作模式。
    if (workspace !== 'research' && !researchEntryAbortController.current) setComposerMode('deep-research')
    setDeepResearchMockStage('completed')
    setDeepResearchMockStep(DEEP_RESEARCH_MOCK_STEPS.length)
    setDeepResearchElapsedSeconds(record.elapsedSeconds)
    setDeepResearchResult((current) => ({
      ...current,
      knowledgeCount: record.knowledgeCount,
      webCount: record.webCount,
    }))
  }, [streamingTurn, turns, workspace])

  // 这一轮结束后 streamingTurn 已清空，卡片上"查看工具调用"要改从落库的这一轮里取。
  const lastTurnToolSteps = useMemo(() => {
    const lastTurn = turns.at(-1)
    if (!lastTurn) return []
    return toolStepsByTurnId[lastTurn.turn_id] ?? persistedToolSteps(lastTurn.tool_traces)
  }, [toolStepsByTurnId, turns])

  // 结论优先取深度研究事件带回的正文；普通轮次没有这个事件，就退回最后一轮回答。
  const deepResearchConclusion = useMemo(() => {
    const summary = deepResearchResult.summary ?? turns.at(-1)?.assistant.content ?? ''
    return summary ? conclusionDigest(summary) : ''
  }, [deepResearchResult.summary, turns])

  // research_result 只在确认计划的深度研究里发出，条数缺席时按整段对话的引用现算。
  const reportReferenceCounts = useMemo(() => {
    const references = collectReferences(citations)
    return {
      knowledge: references.filter((reference) => reference.group === 'knowledge').length,
      web: references.filter((reference) => reference.group === 'web').length,
    }
  }, [citations])
  const citationsForRail = useMemo(() => citations.map((citation) => citationToRail(citation, locale)), [citations, locale])
  const selectedCitation = selectedCitationContext?.citation ?? null
  const selectedCitationId = selectedCitation?.citation_id ?? null
  const selectedCitationReleaseId = selectedCitationContext?.knowledgeReleaseId ?? null
  const selectedMaterialCitation = materialCitationFields(selectedCitation)
  const selectedActivity = allToolSteps.find((activity) => activity.id === selectedActivityId)
  // 这轮一旦产生来源或工具活动，右侧研究面板自己展开；独立 Agent 页才这样，
  // 研究工作区里内嵌的窄栏仍然只按用户点击开合。
  useEffect(() => {
    if (embedded || researchPanelDismissed.current) return
    if (!citationsForRail.length && !activities.length) return
    setContextOpen(true)
  }, [activities.length, citationsForRail.length, embedded])

  useEffect(() => {
    if (contextOpen) {
      setRailMounted(true)
      return undefined
    }
    if (!railMounted) return undefined
    const timer = setTimeout(() => setRailMounted(false), RAIL_EXIT_MS)
    return () => clearTimeout(timer)
  }, [contextOpen, railMounted])

  function toggleResearchPanel() {
    if (contextOpen) {
      researchPanelDismissed.current = true
      setContextOpen(false)
      return
    }
    researchPanelDismissed.current = false
    setContextTab('sources')
    setContextOpen(true)
  }

  function closeResearchPanel() {
    researchPanelDismissed.current = true
    setContextOpen(false)
  }

  function backToResearchPanel() {
    setSelectedActivityId(null)
    setSelectedCitationContext(null)
    setContextTab('sources')
  }

  function openCitation(citation: AgentCitation, knowledgeReleaseId: string | null) {
    const conversationReleaseId = activeConversation?.conversation_id
      ? knowledgeReleaseByConversationId[activeConversation.conversation_id] ?? null
      : null
    setSelectedActivityId(null)
    setSelectedCitationContext({ citation, knowledgeReleaseId: knowledgeReleaseId?.trim() || (embedded ? conversationReleaseId : null) })
    setContextTab('sources')
    setContextOpen(true)
  }

  function handleMaterialDeleted(materialId: string) {
    locallyDeletedMaterialIds.current.add(materialId)
    if (streamingTurn?.citations.some((citation) => materialCitationFields(citation).materialId === materialId)) {
      redactedStreamingMaterialIds.current.add(materialId)
    }
    setActiveConversation((current) => current ? tombstoneConversationMaterial(current, materialId) : current)
    setStreamingTurn((current) => {
      if (!current) return current
      const citations = current.citations.map((citation) => tombstoneMaterialCitation(citation, materialId))
      if (!citations.some((citation, index) => citation !== current.citations[index])) return current
      const next = { ...current, answer: DELETED_MATERIAL_ANSWER, citations }
      if (next.interrupted) persistInterruptedTurn(userId, next)
      return next
    })
    setSelectedCitationContext((current) => current
      ? { ...current, citation: tombstoneMaterialCitation(current.citation, materialId) }
      : current)
  }

  function knowledgeEntryHref(citation: AgentCitation, releaseId: string | null) {
    if (!citation.knowledge_id || !releaseId) return null
    const conversationId = activeConversation?.conversation_id ?? ''
    const returnParams = new URLSearchParams({ conversation_id: conversationId, knowledge_release_id: releaseId })
    const query = new URLSearchParams({
      knowledge_release_id: releaseId,
      return_to: `${location.pathname}?${returnParams.toString()}`,
    })
    return `/knowledge/${encodeURIComponent(citation.knowledge_id)}?${query.toString()}`
  }

  function knowledgeGraphHref(citation: AgentCitation, releaseId: string | null) {
    if (!citation.knowledge_id || !releaseId) return null
    const query = new URLSearchParams({
      knowledge_release_id: releaseId,
      center: citation.knowledge_id,
      query: citation.label,
    })
    return `/knowledge/graph?${query.toString()}`
  }

  function webSourceHref(citation: AgentCitation) {
    if (citation.source_kind !== 'web' || !citation.source_id) return null
    try {
      const url = new URL(citation.source_id)
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : null
    } catch {
      return null
    }
  }

  const selectedKnowledgeEntryHref = selectedCitation
    ? knowledgeEntryHref(selectedCitation, selectedCitationReleaseId)
    : null
  const selectedKnowledgeGraphHref = selectedCitation
    ? knowledgeGraphHref(selectedCitation, selectedCitationReleaseId)
    : null
  const selectedWebSourceHref = selectedCitation ? webSourceHref(selectedCitation) : null

  const basisContent = selectedActivity ? (
    <div className="new-research__basis">
      <span>{text('当前活动', 'Current activity')} · {selectedActivity.status === 'running' ? text('进行中', 'In progress') : selectedActivity.status === 'failed' ? text('失败', 'Failed') : text('已完成', 'Completed')}</span>
      <strong>{localizedToolLabel(selectedActivity.tool, locale, selectedActivity.label)}</strong>
      {selectedActivity.input ? <p>{formatToolPayload(selectedActivity.input)}</p> : null}
      {selectedActivity.detail ? <ToolDetailDisclosure detail={localizedToolDetail(selectedActivity.detail, locale)} /> : <p>{text('本步骤没有返回额外说明。', 'This step returned no additional details.')}</p>}
      {resultItemsFromOutput(selectedActivity.output).map((item) => <p key={item.id}><b>{item.title}</b>{item.excerpt ? ` · ${item.excerpt}` : ''}</p>)}
    </div>
  ) : selectedCitation ? (
    <div className="new-research__basis">
      <span>{text('当前证据', 'Current evidence')} · {citationKindLabel(selectedCitation.kind, locale)}</span>
      <strong>{selectedCitation.label}</strong>
      <p>{selectedCitation.deleted
        ? text('这份研究材料已删除，原文不再可访问。', 'This research material was deleted and its source text is no longer available.')
        : selectedCitation.excerpt || text('本轮 Agent 没有返回可展开的证据摘录。', 'The Agent returned no expandable evidence excerpt for this turn.')}</p>
      {selectedMaterialCitation.locator
        ? <p className="new-research__basis-locator">{formatMaterialLocator(selectedMaterialCitation.locator)}</p>
        : null}
      {(typeof selectedCitation.locator?.task_id === 'string' || taskId || uploadTaskId.current) && selectedMaterialCitation.materialId && !selectedCitation.deleted
        ? <div className="research-agent-basis-actions">
            <button
              type="button"
              onClick={() => {
                setMaterialLocatorTarget({
                  taskId: typeof selectedCitation.locator?.task_id === 'string' ? selectedCitation.locator.task_id : taskId ?? uploadTaskId.current ?? undefined,
                  materialId: selectedMaterialCitation.materialId as string,
                  parseId: selectedMaterialCitation.parseId,
                  segmentId: selectedMaterialCitation.segmentId,
                })
                setContextOpen(false)
                openMaterials()
              }}
            >
              {text('打开原文位置', 'Open source location')} <ArrowUpIcon size={13} />
            </button>
          </div>
        : null}
      {selectedKnowledgeEntryHref
        ? <div className="research-agent-basis-actions">
            <a href={selectedKnowledgeEntryHref}>{text('打开知识条目', 'Open knowledge entry')} <ArrowUpIcon size={13} /></a>
            {selectedKnowledgeGraphHref
              ? <a className="is-graph" href={selectedKnowledgeGraphHref}>{text('在知识图谱中查看', 'View in knowledge graph')} <TreeStructureIcon size={13} /></a>
              : null}
          </div>
        : selectedCitation.knowledge_id
          ? <span className="new-research__basis-note">{text('当前回合的知识版本尚未确认，暂不提供跳转。', 'The knowledge release for this turn is not confirmed, so navigation is unavailable.')}</span>
          : null}
      {selectedWebSourceHref
        ? <div className="research-agent-basis-actions">
            <a href={selectedWebSourceHref} target="_blank" rel="noreferrer">{text('打开网页', 'Open web page')} <ArrowUpIcon size={13} /></a>
          </div>
        : null}
    </div>
  ) : undefined

  const conversationSurface = (
        <section
          className={`research-agent-page new-research research-agent-conversation${embedded ? ' research-agent-conversation--embedded new-research__agent-panel is-agent-synced' : ''} ${isEmpty ? 'is-empty' : 'is-conversation'}${landingBackdropPhase === 'leaving' ? ' is-transitioning' : ''}${!embedded && railMounted ? ' is-rail-mounted' : ''}${!embedded && contextOpen ? ' is-rail-open' : ''}`}
          aria-label={embedded ? text('研究 Agent 对话栏', 'Research Agent conversation panel') : text('社会学 Agent 对话', 'Sociology Agent conversation')}
          role={embedded ? 'complementary' : undefined}
          data-runtime-mode={runtimeMode ?? 'unknown'}
        >
          {!embedded && showConversationManagement ? (
            <button type="button" className="mobile-only mobile-agent-history" aria-label={text('打开研究记录', 'Open research history')} onClick={() => setHistoryOpen(true)}><ListIcon size={18} />{text('研究记录', 'History')}</button>
          ) : null}
          {!embedded && landingBackdropPhase !== 'hidden' ? (
            <div className={`research-agent-conversation__landing-backdrop is-${landingBackdropPhase}`}>
              <ResearchAgentShader />
            </div>
          ) : null}
          {isEmpty && !embedded ? <div aria-hidden="true" className="research-agent-page__heading-placeholder" /> : (
            <header className="research-agent-page__conversation-heading new-research__agent-header" aria-label={text('对话操作', 'Conversation actions')}>
              <div className="new-research__agent-actions">
                {workspace === 'research' ? (
                  <button
                    type="button"
                    aria-label={text('研究材料', 'Research materials')}
                    aria-pressed={materialsOpen}
                    title={text('研究材料', 'Research materials')}
                    onClick={() => {
                      if (!taskId) {
                        navigate('/research/materials')
                        return
                      }
                      setMaterialLocatorTarget(null)
                      openMaterials()
                    }}
                  >
                    <FileTextIcon size={16} />
                  </button>
                ) : null}
                {embedded ? (
                  <>
                    <button type="button" aria-label={text('查看活动', 'View activity')} aria-pressed={contextOpen && contextTab === 'activity'} title={text('查看活动', 'View activity')} onClick={() => { setContextTab('activity'); setContextOpen(true) }}><CircleNotchIcon size={16} />{activities.length ? <i>{activities.length}</i> : null}</button>
                    <button type="button" aria-label={text('查看来源', 'View sources')} aria-pressed={contextOpen && contextTab === 'sources'} title={text('查看来源', 'View sources')} onClick={() => { setContextTab('sources'); setContextOpen(true) }}><ArticleIcon size={16} />{citations.length ? <i>{citations.length}</i> : null}</button>
                    {showConversationManagement ? <button type="button" aria-label={text('打开研究记录', 'Open research history')} aria-pressed={historyOpen} title={text('打开研究记录', 'Open research history')} onClick={() => setHistoryOpen(true)}><ListIcon size={16} /></button> : null}
                  </>
                ) : (
                  <button type="button" aria-label={text('研究面板', 'Research panel')} aria-pressed={contextOpen} title={text('研究面板', 'Research panel')} onClick={toggleResearchPanel}><SidebarSimpleIcon size={16} />{citations.length ? <i>{citations.length}</i> : null}</button>
                )}
              </div>
            </header>
          )}

          <main className="research-agent-page__scroll-region new-research__conversation" aria-label={text('对话内容', 'Conversation content')} role="log">
            {isEmpty ? (
              <div className="research-agent-page__empty-state">
                <div className="research-agent-page__empty-copy">
                  <ResearchAgentBot />
                  <ResearchPromptCarousel onSelect={choosePrompt} />
                </div>
              </div>
            ) : (
              <div className="research-agent-page__transcript new-research__transcript">
                {turns.map((turn) => (
                  <AssistantTurn
                    key={turn.turn_id}
                    question={turn.user.content}
                    answer={turn.assistant.content}
                    citations={turn.assistant.citations}
                  toolSteps={toolStepsByTurnId[turn.turn_id] ?? persistedToolSteps(turn.tool_traces)}
                  conversationId={activeConversation?.conversation_id ?? null}
                  knowledgeReleaseId={turn.knowledge_release_id?.trim() || null}
                  embedded={embedded}
                  showResearchHandoff={!embedded}
                  onContinueResearch={() => { void continueResearch() }}
                  researchEntryBusy={researchEntryBusy || isBusy || materialUploading || attachedMaterials.some((material) => material.status !== 'ready')}
                    onOpenActivity={() => { setContextTab('activity'); setContextOpen(true) }}
                    onSelectCitation={openCitation}
                    onRegenerate={() => { void submitQuestion(turn.user.content) }}
                  />
                ))}
                {streamingTurn && deepResearchMockStage === 'researching' ? (
                  <DeepResearchMockFlow
                    stage={deepResearchMockStage}
                    question={deepResearchMockQuestion}
                    stepIndex={deepResearchMockStep}
                    options={deepResearchMockOptions}
                    knowledgeCount={deepResearchResult.knowledgeCount}
                    webCount={deepResearchResult.webCount}
                    toolSteps={streamingTurn.toolSteps}
                    elapsedSeconds={deepResearchElapsedSeconds}
                    onChooseIntent={(intent) => continueDeepResearch('clarify', intent)}
                    onSkip={() => continueDeepResearch('skip')}
                    onConfirmPlan={() => continueDeepResearch('confirm')}
                    onEdit={() => {
                      resetDeepResearchMock()
                      globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
                    }}
                  />
                ) : null}
                {streamingTurn ? (
                  <AssistantTurn
                    question={streamingTurn.question}
                    answer={streamingTurn.answer}
                    citations={streamingTurn.citations}
                    toolSteps={streamingTurn.toolSteps}
                    conversationId={activeConversation?.conversation_id ?? pendingConversationId.current}
                    knowledgeReleaseId={null}
                    interrupted={streamingTurn.interrupted}
                    failure={streamingTurn.failure}
                    streaming={canStopGeneration && !streamingTurn.interrupted && !streamingTurn.failure}
                    streamingStatus={status}
                    progressEnd={streamingTurn.progressEnd}
                    embedded={embedded}
                    onOpenActivity={() => { setContextTab('activity'); setContextOpen(true) }}
                    onSelectCitation={openCitation}
                    onRegenerate={() => retryFailedTurn(streamingTurn.question)}
                  />
                ) : null}
                {hasDeepResearchMockConversation && deepResearchMockStage !== 'researching' ? (
                  <DeepResearchMockFlow
                    stage={deepResearchMockStage}
                    question={deepResearchMockQuestion}
                    stepIndex={deepResearchMockStep}
                    options={deepResearchMockOptions}
                    knowledgeCount={deepResearchResult.knowledgeCount ?? reportReferenceCounts.knowledge}
                    webCount={deepResearchResult.webCount ?? reportReferenceCounts.web}
                    toolSteps={streamingTurn?.toolSteps ?? lastTurnToolSteps}
                    elapsedSeconds={deepResearchElapsedSeconds}
                    conclusion={deepResearchConclusion}
                    exportState={reportExportState}
                    onExport={activeConversation ? (kind) => { void exportResearchReport(kind) } : undefined}
                    onContinueResearch={() => { void continueResearch() }}
                    researchEntryBusy={researchEntryBusy || isBusy || materialUploading || attachedMaterials.some((material) => material.status !== 'ready')}
                    onChooseIntent={(intent) => continueDeepResearch('clarify', intent)}
                    onSkip={() => continueDeepResearch('skip')}
                    onConfirmPlan={() => continueDeepResearch('confirm')}
                    onEdit={() => {
                      resetDeepResearchMock()
                      globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
                    }}
                  />
                ) : null}
                {conversationTail}
                <div ref={transcriptEndRef} />
              </div>
            )}
          </main>

          <footer className="research-agent-page__composer-dock new-research__composer-dock">
            {error ? (
              <div className="qx-notice-surface new-research__error" role="alert">
                <WarningCircleIcon size={16} /><span>{error}</span>
                <button type="button" aria-label={text('关闭错误提示', 'Close error message')} onClick={() => setError(null)}><XIcon size={14} /></button>
              </div>
            ) : null}
            {composerMode === 'deep-research' && deepResearchMockStage === 'clarifying' && !streamingTurn ? (
              <DeepResearchMockFlow
                stage={deepResearchMockStage}
                question={deepResearchMockQuestion}
                stepIndex={deepResearchMockStep}
                options={deepResearchMockOptions}
                knowledgeCount={deepResearchResult.knowledgeCount}
                webCount={deepResearchResult.webCount}
                toolSteps={streamingTurn?.toolSteps ?? []}
                onChooseIntent={(intent) => continueDeepResearch('clarify', intent)}
                onSkip={() => continueDeepResearch('skip')}
                onConfirmPlan={() => continueDeepResearch('confirm')}
                onEdit={() => {
                  resetDeepResearchMock()
                  globalThis.requestAnimationFrame?.(() => composerInputRef.current?.focus())
                }}
              />
            ) : null}
            <form onSubmit={handleSubmit} className="new-research__composer-form">
              <div className={`new-research__composer research-agent-composer${composerPrefix ? ' has-prefix' : ''}${attachedMaterials.length || materialUploading ? ' has-attachments' : ''}${composerMode === 'deep-research' ? ' is-deep-research' : ''}${composerMode === 'deep-research' && isEmpty ? ' is-awaiting-first-message' : ''}`}>
                {materialPickerOpen ? (
                  <AgentMaterialAttachmentPicker
                    inline
                    loading={materialPickerLoading}
                    materials={materialPickerLoading ? [] : availableMaterials}
                    selectedIds={new Set(attachedMaterials.map((item) => item.materialId))}
                    locale={locale}
                    onToggle={toggleAttachedMaterial}
                    onClose={() => setMaterialPickerOpen(false)}
                  />
                ) : null}
                {composerPrefix}
                {attachedMaterials.length || materialUploading ? (
                  <div className="research-agent-composer__attachments" aria-label={text('本轮附件', 'Attachments for this turn')}>
                    {attachedMaterials.map((material) => (
                      <span className={`research-agent-composer__attachment is-${material.status}`} key={material.materialId}>
                        <FileTextIcon size={14} aria-hidden="true" />
                        <span title={material.filename}>{material.filename}</span>
                        <small>{material.status === 'ready' ? text('已添加', 'Added') : attachmentStatusLabel(material, locale)}</small>
                        <button
                          type="button"
                          disabled={isBusy}
                          aria-label={text(`移除附件 ${material.filename}`, `Remove attachment ${material.filename}`)}
                          onClick={() => setAttachedMaterials((current) => current.filter((item) => item.materialId !== material.materialId))}
                        ><XIcon size={12} /></button>
                      </span>
                    ))}
                    {materialUploading ? <span className="research-agent-composer__uploading" role="status"><CircleNotchIcon size={14} className="spin" />{text('正在上传…', 'Uploading…')}</span> : null}
                  </div>
                ) : null}
                <textarea
                  ref={composerInputRef}
                  aria-label={composerAriaLabel ?? text('问社会学 Agent', 'Ask the Sociology Agent')}
                  disabled={isBusy}
                  maxLength={MAX_AGENT_MESSAGE_LENGTH}
                  value={draft}
                  onChange={(event) => updateDraft(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={text('问一个问题，或描述你正在理解的现象', 'Ask a question or describe a phenomenon you are trying to understand')}
                  rows={1}
                />
                <input
                  ref={materialFileInputRef}
                  className="research-agent-composer__file-input"
                  type="file"
                  multiple
                  accept={RESEARCH_MATERIAL_ACCEPT}
                  tabIndex={-1}
                  aria-hidden="true"
                  onChange={(event) => { void uploadComposerMaterials([...event.currentTarget.files ?? []]) }}
                />
                <div className="research-agent-composer__controls">
                  <div className="research-agent-composer__material-entry" ref={materialMenuRef}>
                    <button
                      ref={materialMenuButtonRef}
                      type="button"
                      className="research-agent-composer__add"
                      aria-label={text('添加研究材料', 'Add research material')}
                      aria-expanded={materialMenuOpen}
                      aria-controls="research-agent-material-menu"
                      disabled={isBusy || materialUploading}
                      onClick={() => {
                        setModeMenuOpen(false)
                        setMaterialMenuOpen((open) => !open)
                      }}
                    >
                      <PlusIcon size={18} />
                    </button>
                    {materialMenuOpen ? (
                      <div
                        id="research-agent-material-menu"
                        className="research-agent-composer__material-menu"
                        role="menu"
                        aria-label={text('添加研究材料', 'Add research material')}
                      >
                        <button type="button" role="menuitem" onClick={() => {
                          setMaterialMenuOpen(false)
                          materialFileInputRef.current?.click()
                        }}>
                          <FilePlusIcon size={18} /><span>{text('上传文件', 'Upload a file')}</span>
                        </button>
                        <button type="button" role="menuitem" onClick={() => { void openMaterialAttachmentPicker() }}>
                          <FolderOpenIcon size={18} /><span>{text('从研究材料添加', 'Add from research materials')}</span>
                        </button>
                        <button type="button" role="menuitem" onClick={openResearchMaterials}>
                          <LinkSimpleIcon size={18} /><span>{text('查看材料库', 'Open material library')}</span>
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className={`research-agent-composer__web-search${webSearchEnabled ? ' is-active' : ''}`}
                    aria-label={text('联网搜索', 'Web search')}
                    aria-pressed={webSearchEnabled}
                    disabled={isBusy}
                    onClick={() => setWebSearchEnabled((enabled) => !enabled)}
                  >
                    <GlobeHemisphereWestIcon size={16} />
                    <span>{webSearchEnabled ? text('联网已开启', 'Web on') : text('联网搜索', 'Web search')}</span>
                  </button>
                  <ProjectScopeMenu projects={projects} taskId={taskId} disabled={isBusy || materialUploading} onChange={switchComposerProject} />
                </div>
                <div className="research-agent-composer__mode-entry" ref={modeMenuRef}>
                  {deepResearchIntroVisible ? (
                    <aside className="deep-research-intro" role="dialog" aria-label={text('深入研究介绍', 'Deep research introduction')}>
                      <button
                        className="deep-research-intro__close"
                        type="button"
                        aria-label={text('关闭深入研究介绍', 'Close deep research introduction')}
                        onClick={() => setDeepResearchIntroVisible(false)}
                      >
                        <XIcon size={16} weight="bold" />
                      </button>
                      <img src={deepResearchGuidance} alt="" />
                      <div className="deep-research-intro__body">
                        <p className="deep-research-intro__eyebrow">{text('新功能', 'New feature')}</p>
                        <h2>{text('深入研究', 'Deep research')}</h2>
                        <p>{text('让 Agent 多轮检索知识库与网页，整理出一份带证据的研究结果。', 'Ask the Agent to search your knowledge base and the web, then shape the evidence into a research result.')}</p>
                        <div className="deep-research-intro__actions">
                          <button type="button" className="deep-research-intro__dismiss" onClick={() => setDeepResearchIntroVisible(false)}>
                            {text('稍后再说', 'Maybe later')}
                          </button>
                          <button type="button" className="deep-research-intro__try" onClick={() => {
                            setComposerMode('deep-research')
                            setDeepResearchIntroVisible(false)
                          }}>
                            {text('试试看', 'Try it')}
                          </button>
                        </div>
                      </div>
                    </aside>
                  ) : null}
                  <button
                    ref={modeMenuButtonRef}
                    type="button"
                    className={`research-agent-composer__mode-button${composerMode === 'deep-research' ? ' is-deep-research' : ''}`}
                    aria-label={text('选择 Agent 模式', 'Choose Agent mode')}
                    aria-expanded={modeMenuOpen}
                    aria-controls="research-agent-mode-menu"
                    disabled={isBusy}
                    onClick={() => {
                      setMaterialMenuOpen(false)
                      setModeMenuOpen((open) => !open)
                    }}
                  >
                    <span className="research-agent-composer__mode-label">{composerMode === 'deep-research' ? text('深入研究', 'Deep research') : text('标准', 'Standard')}</span>
                    <CaretDownIcon size={13} weight="bold" />
                  </button>
                  {modeMenuOpen ? (
                    <div
                      id="research-agent-mode-menu"
                      className="research-agent-composer__material-menu research-agent-composer__mode-menu"
                      role="menu"
                      aria-label={text('选择 Agent 模式', 'Choose Agent mode')}
                    >
                      <button
                        type="button"
                        role="menuitemradio"
                        aria-checked={composerMode === 'standard'}
                        onClick={() => {
                          setComposerMode('standard')
                          setModeMenuOpen(false)
                        }}
                      >
                        <span className="research-agent-composer__mode-copy">
                          <strong>{text('标准模式', 'Standard mode')}</strong>
                          <small>{text('知识库优先，按需补充联网资料', 'Knowledge first, with web sources as needed')}</small>
                        </span>
                        {composerMode === 'standard' ? <CheckIcon size={14} weight="bold" /> : null}
                      </button>
                      <button
                        type="button"
                        role="menuitemradio"
                        aria-checked={composerMode === 'deep-research'}
                        onClick={() => {
                          setComposerMode('deep-research')
                          setDeepResearchIntroVisible(false)
                          setModeMenuOpen(false)
                        }}
                      >
                        <span className="research-agent-composer__mode-copy">
                          <strong>{text('深入研究', 'Deep research')}</strong>
                          <small>{text(
                            '最大思考强度，多轮检索知识库与网页，并形成详细研究计划',
                            'Maximum reasoning with multi-round knowledge and web research',
                          )}</small>
                        </span>
                        {composerMode === 'deep-research' ? <CheckIcon size={14} weight="bold" /> : null}
                      </button>
                    </div>
                  ) : null}
                </div>
                <button
                  type={canStopGeneration ? 'button' : 'submit'}
                  aria-label={canStopGeneration ? text('停止生成', 'Stop generating') : isBusy ? text('Agent 正在加载', 'Agent is loading') : text('发送给社会学 Agent', 'Send to the Sociology Agent')}
                  className={`research-agent-composer__send${canStopGeneration ? ' is-stop' : ''}`}
                  disabled={isBusy ? !canStopGeneration : !canSubmit}
                  onClick={canStopGeneration ? stopGeneration : undefined}
                >
                  {canStopGeneration ? <StopIcon size={15} weight="fill" /> : <ArrowUpIcon size={18} />}
                </button>
              </div>
            </form>
          </footer>

          {showConversationManagement && historyOpen ? (
            <ConversationHistory
              projects={projects}
              setProjects={setProjects}
              selectedTaskId={taskId}
              onNewConversation={newConversation}
              onRename={renameSavedConversation}
              onDelete={deleteSavedConversation} onDeleteProject={deleteSavedProject}
              conversations={conversations}
              activeConversationId={activeConversation?.conversation_id ?? null}
              loading={historyLoading}
              onOpen={openConversation}
              onClose={closeHistory}
            />
          ) : null}

          {(embedded ? contextOpen : railMounted) ? (
            <ResearchContextRail
              activeTab={contextTab}
              activities={activities}
              citations={citationsForRail}
              selectedCitationId={selectedCitationId}
              variant={embedded ? 'tabs' : 'sections'}
              elapsedSeconds={embedded ? null : deepResearchElapsedSeconds}
              onClose={closeResearchPanel}
              onBack={backToResearchPanel}
              onPanelChange={setContextTab}
              onActivitySelect={(activity) => {
                setSelectedCitationContext(null)
                setSelectedActivityId(activity.id)
                setContextTab('basis')
              }}
              onCitationSelect={(citation) => {
                const context = selectedCitationContext?.citation.citation_id === citation.id
                  ? selectedCitationContext
                  : citationContexts.find((item) => item.citation.citation_id === citation.id)
                if (!context) return
                setSelectedActivityId(null)
                setSelectedCitationContext(context)
                setContextTab('basis')
              }}
              basisContent={basisContent}
            />
          ) : null}

          {materialsOpen && (materialLocatorTarget?.taskId ?? taskId) ? (
            <ResearchMaterialsPanel
              taskId={(materialLocatorTarget?.taskId ?? taskId)!}
              initialMaterialId={materialLocatorTarget?.materialId ?? null}
              initialParseId={materialLocatorTarget?.parseId ?? null}
              initialSegmentId={materialLocatorTarget?.segmentId ?? null}
              onMaterialDeleted={handleMaterialDeleted}
              onClose={() => {
                closeMaterials()
                setMaterialLocatorTarget(null)
              }}
            />
          ) : null}

        </section>
  )

  if (embedded) {
    return (
      <>
        {conversationSurface}
        {showConversationManagement && historyRailTarget ? createPortal(
          <AgentConversationHistoryRail
            projects={projects} setProjects={setProjects} projectListError={projectListError}
            selectedTaskId={taskId}
            activeConversationId={activeConversation?.conversation_id ?? null}
            conversations={conversations}
            loading={historyLoading}
            onDelete={deleteSavedConversation} onDeleteProject={deleteSavedProject}
            onNewConversation={newConversation}
            onOpen={openConversation}
            onRename={renameSavedConversation}
          />,
          historyRailTarget,
        ) : null}
      </>
    )
  }

  return (
    <PageShell
      railContent={(
        <AgentConversationHistoryRail
          projects={projects} setProjects={setProjects} projectListError={projectListError}
          selectedTaskId={taskId}
          activeConversationId={activeConversation?.conversation_id ?? null}
          conversations={conversations}
          loading={historyLoading}
          onDelete={deleteSavedConversation} onDeleteProject={deleteSavedProject}
          onNewConversation={newConversation}
          onOpen={openConversation}
          onRename={renameSavedConversation}
        />
      )}
      wide
    >
      <PageContent>{conversationSurface}</PageContent>
    </PageShell>
  )
}
