import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from '@tiptap/markdown'
import { CheckCircleIcon, CircleNotchIcon, DownloadSimpleIcon, PaperPlaneTiltIcon, WarningCircleIcon } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router'

import {
  acceptResearchDocumentProposal,
  acknowledgePartialMatch,
  createTheoryDecisions,
  confirmTheoryPlan,
  confirmResearchDocument,
  exportResearchDocument,
  getMatchRun,
  getResearchTaskNavigation,
  listResearchDocuments,
  listResearchDocumentVersions,
  listResearchTaskDocumentProposals,
  listTheoryDecisions,
  restoreResearchDocument,
  rejectResearchDocumentProposal,
  updateResearchDocument,
  type ResearchDocumentProposalResponse,
  type ResearchDocumentResponse,
  type ResearchTaskNavigationResponse,
  type MatchRunResponse,
  type TheoryDecisionSetResponse,
  type TheoryDecisionAction,
} from '../../api/generated'
import { apiClient } from '../../api/client'
import { streamAgentTurn, type AgentEvent, type AgentToolStep } from '../../modules/research-agent'
import './research-document-workbench.css'

const M4_SECTIONS = [
  ['research_question', '研究问题'],
  ['core_phenomenon', '核心现象'],
  ['candidate_theories', '候选理论'],
  ['theory_fit', '理论适配与张力'],
  ['evidence', '证据引用'],
  ['theory_decision', '我的理论选择'],
] as const
const M5_SECTIONS = [
  ['research_question', '研究问题'],
  ['research_object_and_field', '研究对象与场域'],
  ['theoretical_perspective', '理论视角'],
  ['core_concepts', '核心概念'],
  ['mechanisms', '作用机制'],
  ['questions_or_hypotheses', '研究假设与质性问题'],
  ['methodology', '研究方法'],
  ['sample_and_sources', '样本与资料来源'],
  ['analysis_steps', '分析步骤'],
  ['ethics', '伦理风险'],
  ['limitations', '局限'],
  ['evidence_gaps', '证据缺口'],
] as const

type SectionKey = string
type AgentState = 'idle' | 'thinking' | 'retrieving' | 'answering' | 'error'

function key() {
  return globalThis.crypto?.randomUUID?.() ?? `m4-m5-${Date.now()}`
}

function sectionFallback(stage: 'match' | 'framework') {
  const items = stage === 'match' ? M4_SECTIONS : M5_SECTIONS
  return items.map(([sectionId, title]) => ({
    section_id: sectionId,
    key: sectionId,
    title,
    content: '',
    status: 'needs_user_decision' as const,
    evidence_refs: [],
  }))
}

function selectCurrentDocument(items: ResearchDocumentResponse[], navigation: ResearchTaskNavigationResponse, mode: 'match' | 'framework') {
  const currentId = mode === 'framework' ? navigation.current_framework_id : navigation.current_theory_plan_id
  return (currentId ? items.find((item) => mode === 'framework' ? item.document_id === currentId : item.theory_plan_id === currentId) : undefined) ?? items[0] ?? null
}

export function ResearchDocumentWorkbench() {
  const { task_id: taskId, stage: stageParam } = useParams<{ task_id: string; stage?: string }>()
  const location = useLocation()
  const stage = stageParam ?? (location.pathname.endsWith('/framework') ? 'framework' : 'match')
  const mode = stage === 'framework' ? 'framework' : 'match'
  const [navigation, setNavigation] = useState<ResearchTaskNavigationResponse | null>(null)
  const [document, setDocument] = useState<ResearchDocumentResponse | null>(null)
  const [proposals, setProposals] = useState<ResearchDocumentProposalResponse[]>([])
  const [versions, setVersions] = useState<ResearchDocumentResponse[]>([])
  const [activeSectionId, setActiveSectionId] = useState<SectionKey>(mode === 'match' ? M4_SECTIONS[0][0] : M5_SECTIONS[0][0])
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [agentState, setAgentState] = useState<AgentState>('idle')
  const [agentDraft, setAgentDraft] = useState('')
  const [agentAnswer, setAgentAnswer] = useState('')
  const [agentError, setAgentError] = useState<string | null>(null)
  const [toolSteps, setToolSteps] = useState<AgentToolStep[]>([])
  const [citations, setCitations] = useState<Array<{ citation_id: string; label: string; source_id?: string | null; knowledge_id?: string | null }>>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [runtimeMode, setRuntimeMode] = useState<'mock' | 'base' | 'sft' | null>(null)
  const [matchRun, setMatchRun] = useState<MatchRunResponse | null>(null)
  const [pendingTheoryDecisions, setPendingTheoryDecisions] = useState<Record<string, { candidate_version: number; action: TheoryDecisionAction }>>({})
  const [decisionSet, setDecisionSet] = useState<TheoryDecisionSetResponse | null>(null)
  const [relationDraft, setRelationDraft] = useState({ explanation: '', premise: '', supporting: '', excluding: '', distinguishing: '' })
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  const abortRef = useRef<AbortController | null>(null)

  const sections = document?.sections.length ? document.sections : sectionFallback(mode)
  const activeSection = sections.find((section) => section.section_id === activeSectionId) ?? sections[0]
  const activeContent = activeSection?.content ?? ''
  const selectedTheoryIds = Object.entries(pendingTheoryDecisions).filter(([, value]) => value.action === 'adopt' || value.action === 'combine').map(([candidateId]) => candidateId)
  const multiTheoryRelationReady = selectedTheoryIds.length < 2 || Object.values(relationDraft).every((value) => value.trim())
  const editor = useEditor({
    extensions: [StarterKit, Markdown],
    content: activeContent || '<p>在这里写下你的研究判断。每次用户编辑都会形成可恢复的文档版本。</p>',
    immediatelyRender: false,
    editorProps: { attributes: { 'aria-labelledby': 'research-document-heading' } },
    onUpdate: () => setSaveState('unsaved'),
  })

  useEffect(() => {
    if (!editor || !activeSection) return
    editor.commands.setContent(activeSection.content || '<p>在这里写下你的研究判断。每次用户编辑都会形成可恢复的文档版本。</p>')
    setSaveState('saved')
  }, [activeSectionId, document?.revision_id, editor])

  useEffect(() => {
    if (!taskId) {
      setLoadState('error')
      setError('研究任务地址无效。')
      return
    }
    let disposed = false
    setLoadState('loading')
    Promise.all([
      Promise.resolve().then(() => getResearchTaskNavigation({ client: apiClient, path: { task_id: taskId } })),
      Promise.resolve().then(() => listResearchDocuments({ client: apiClient, path: { task_id: taskId } })),
    ]).then(async ([nav, docs]) => {
      if (disposed) return
      if (!nav.data || !docs.data) throw new Error('研究工作区暂时无法加载。')
      setNavigation(nav.data)
      if (mode === 'match' && nav.data.current_match_run_id) {
        const match = await getMatchRun({ client: apiClient, path: { match_run_id: nav.data.current_match_run_id } })
        if (match.data) setMatchRun(match.data)
        const decisions = await listTheoryDecisions({ client: apiClient, path: { match_run_id: nav.data.current_match_run_id } })
        if (decisions.data?.decision_sets.length) {
          const restoredDecisionSet = decisions.data.decision_sets[0]
          setDecisionSet(restoredDecisionSet)
          setPendingTheoryDecisions(Object.fromEntries(restoredDecisionSet.decisions.map((decision) => [decision.candidate_id, { candidate_version: decision.candidate_version, action: decision.action }])))
        }
      }
      const current = selectCurrentDocument(docs.data.items, nav.data, mode)
      setDocument(current)
      setLoadState('ready')
      const taskProposals = await listResearchTaskDocumentProposals({ client: apiClient, path: { task_id: taskId } })
      if (taskProposals.data) setProposals(taskProposals.data.items)
      if (current) {
        listResearchDocumentVersions({ client: apiClient, path: { document_id: current.document_id } })
          .then((result) => result.data && setVersions(result.data.items))
          .catch(() => undefined)
      }
    }).catch(() => {
      if (!disposed) {
        setLoadState('error')
        setError('当前 Agent 运行环境未连接；不会把静态示例当作真实研究结果。')
      }
    })
    return () => { disposed = true }
  }, [taskId])

  const refreshDocumentState = useCallback(async () => {
    if (!taskId) return
    const [navigationResult, result] = await Promise.all([
      getResearchTaskNavigation({ client: apiClient, path: { task_id: taskId } }),
      listResearchDocuments({ client: apiClient, path: { task_id: taskId } }),
    ])
    if (navigationResult.data) setNavigation(navigationResult.data)
    if (!result.data) return
    const currentId = mode === 'framework' ? navigation?.current_framework_id : navigation?.current_theory_plan_id
    const current = (currentId ? result.data.items.find((item) => mode === 'framework' ? item.document_id === currentId : item.theory_plan_id === currentId) : undefined) ?? result.data.items[0] ?? null
    setDocument(current)
    const taskProposals = await listResearchTaskDocumentProposals({ client: apiClient, path: { task_id: taskId } })
    if (taskProposals.data) setProposals(taskProposals.data.items)
    if (current) {
      const versionsResult = await listResearchDocumentVersions({ client: apiClient, path: { document_id: current.document_id } })
      if (versionsResult.data) setVersions(versionsResult.data.items)
    }
  }, [mode, navigation, taskId])

  const saveSection = useCallback(async () => {
    if (!editor || !document || !activeSection) return
    setSaveState('saving')
    const content = editor.getText()
    const nextSections = document.sections.map((section) => section.section_id === activeSection.section_id
      ? { ...section, content }
      : section)
    const result = await updateResearchDocument({
      client: apiClient,
      path: { document_id: document.document_id },
      headers: { 'Idempotency-Key': key() },
      body: { expected_version: document.version, sections: nextSections, change_summary: '用户直接编辑正文', source: 'user_edit' },
    })
    if (!result.data) throw new Error('自动保存失败，请重试。')
    setDocument(result.data)
    setSaveState('saved')
  }, [activeSection, document, editor])

  useEffect(() => {
    if (saveState !== 'unsaved') return
    const timer = window.setTimeout(() => { void saveSection().catch((reason: unknown) => { setSaveState('unsaved'); setError(reason instanceof Error ? reason.message : '自动保存失败。') }) }, 900)
    return () => window.clearTimeout(timer)
  }, [saveSection, saveState])

  async function askAgent() {
    const message = agentDraft.trim()
    if (!message || agentState === 'thinking' || agentState === 'retrieving') return
    abortRef.current?.abort()
    const abort = new AbortController()
    abortRef.current = abort
    setAgentDraft('')
    setAgentAnswer('')
    setAgentError(null)
    setToolSteps([])
    setCitations([])
    setAgentState('thinking')
    let terminalError = false
    try {
      await streamAgentTurn({ conversation_id: conversationId, message, workspace: 'research', task_id: taskId, document_id: document?.document_id ?? null, section_id: activeSection?.section_id ?? null, document_version: document?.version ?? null, theory_plan_id: navigation?.current_theory_plan_id ?? null, idempotencyKey: key() }, (event: AgentEvent) => {
        if (event.type === 'turn_started') {
          setConversationId(event.conversation_id)
          setRuntimeMode(event.runtime_mode ?? null)
        }
        if (event.type === 'agent_status') setAgentState(event.status === 'answering' ? 'answering' : 'thinking')
        if (event.type === 'tool_started') {
          setAgentState('retrieving')
          setToolSteps((current) => [...current, { id: event.call_id ?? `${event.tool}-${Date.now()}`, tool: event.tool, label: event.tool, detail: event.detail, input: event.input, status: 'running' }])
        }
        if (event.type === 'tool_finished' || event.type === 'tool_failed') {
          setAgentState('thinking')
          setToolSteps((current) => current.map((step) => step.id === event.call_id || step.tool === event.tool ? { ...step, detail: event.detail, output: event.type === 'tool_finished' ? event.output : event.message, status: event.type === 'tool_failed' ? 'failed' : 'completed' } : step))
        }
        if (event.type === 'assistant_delta') { setAgentState('answering'); setAgentAnswer((current) => current + event.delta) }
        if (event.type === 'citation_added') setCitations((current) => [...current, event.citation])
        if (event.type === 'turn_completed') { void refreshDocumentState() }
        if (event.type === 'turn_interrupted') { terminalError = true; setAgentState('error'); setAgentError(event.message) }
        if (event.type === 'turn_failed') { terminalError = true; setAgentState('error'); setAgentError(event.message) }
      }, abort.signal)
      if (!terminalError) setAgentState('answering')
    } catch (reason: unknown) {
      if (abort.signal.aborted) setAgentError('已中断本次 Agent 请求，可继续重试。')
      else setAgentError(reason instanceof Error ? reason.message : 'Agent 暂时无法连接。')
      setAgentState('error')
    }
  }

  async function acceptProposal(proposal: ResearchDocumentProposalResponse) {
    if (proposal.status !== 'pending') return
    if (proposal.kind !== 'create' && !document) return
    const result = await acceptResearchDocumentProposal({
      client: apiClient,
      path: { proposal_id: proposal.proposal_id },
      headers: { 'Idempotency-Key': key() },
      body: { expected_document_version: proposal.kind === 'create' ? null : document!.version },
    })
    if (result.data) {
      setDocument(result.data.document)
      setProposals((current) => current.map((item) => item.proposal_id === proposal.proposal_id ? result.data!.proposal : item))
      await refreshDocumentState()
    }
  }

  async function rejectProposal(proposal: ResearchDocumentProposalResponse) {
    if (proposal.status !== 'pending') return
    const result = await rejectResearchDocumentProposal({
      client: apiClient,
      path: { proposal_id: proposal.proposal_id },
      headers: { 'Idempotency-Key': key() },
      body: { reason: '用户拒绝本次局部修改建议。' },
    })
    if (result.data) setProposals((current) => current.map((item) => item.proposal_id === proposal.proposal_id ? result.data! : item))
  }

  async function confirmDocument() {
    if (!document) return
    const result = await confirmResearchDocument({ client: apiClient, path: { document_id: document.document_id }, headers: { 'Idempotency-Key': key() }, body: { expected_version: document.version } })
    if (result.data) setDocument(result.data)
  }

  async function restoreVersion(version: number) {
    if (!document || version === document.version) return
    const result = await restoreResearchDocument({
      client: apiClient,
      path: { document_id: document.document_id },
      headers: { 'Idempotency-Key': key() },
      body: { source_version: version, expected_version: document.version, reason: `恢复到第 ${version} 版` },
    })
    if (result.data) {
      setDocument(result.data)
      setVersions((current) => [result.data!, ...current.filter((item) => item.version !== result.data!.version)])
    }
  }

  function recordTheoryDecision(candidateId: string, candidateVersion: number, action: TheoryDecisionAction) {
    setPendingTheoryDecisions((current) => ({ ...current, [candidateId]: { candidate_version: candidateVersion, action } }))
  }

  async function submitTheoryDecisions() {
    if (!matchRun) return
    const candidates = matchRun.candidate_page.candidates
    if (candidates.some((candidate) => !pendingTheoryDecisions[candidate.candidate_id])) return
    const adoptedCandidateIds = candidates.filter((candidate) => ['adopt', 'combine'].includes(pendingTheoryDecisions[candidate.candidate_id].action)).map((candidate) => candidate.candidate_id)
    if (adoptedCandidateIds.length > 1 && !multiTheoryRelationReady) return
    let expectedMatchVersion = matchRun.version
    if (matchRun.failed_candidate_ids.length && !matchRun.partial_completion_acknowledged) {
      const acknowledged = await acknowledgePartialMatch({
        client: apiClient,
        path: { match_run_id: matchRun.match_run_id },
        headers: { 'Idempotency-Key': key() },
        body: {
          expected_version: matchRun.version,
          failed_candidate_ids: matchRun.failed_candidate_ids,
          acknowledged_candidate_ids: candidates.map((candidate) => candidate.candidate_id),
          reason: '用户确认以当前可用候选继续理论判断。',
        },
      })
      if (!acknowledged.data) return
      setMatchRun(acknowledged.data)
      expectedMatchVersion = acknowledged.data.version
    }
    const result = await createTheoryDecisions({
      client: apiClient,
      path: { match_run_id: matchRun.match_run_id },
      headers: { 'Idempotency-Key': key() },
      body: {
        expected_match_run_version: expectedMatchVersion,
        completion_basis: matchRun.failed_candidate_ids.length ? 'partial_with_user_ack' : 'complete',
        decisions: candidates.map((candidate) => ({ candidate_id: candidate.candidate_id, candidate_version: pendingTheoryDecisions[candidate.candidate_id].candidate_version, action: pendingTheoryDecisions[candidate.candidate_id].action, reason: '用户在理论判断工作台确认。', related_candidate_ids: pendingTheoryDecisions[candidate.candidate_id].action === 'combine' ? adoptedCandidateIds.filter((id) => id !== candidate.candidate_id) : [], related_source_ids: [] })),
        relations: adoptedCandidateIds.length > 1 ? [{ candidate_ids: adoptedCandidateIds, relation_kind: 'complementary', explanation: relationDraft.explanation.trim(), premise_compatibility: relationDraft.premise.trim(), supporting_evidence: [relationDraft.supporting.trim()], excluding_evidence: [relationDraft.excluding.trim()], distinguishing_evidence: [relationDraft.distinguishing.trim()] }] : [],
        use_assignments: candidates.filter((candidate) => ['adopt', 'retain', 'combine'].includes(pendingTheoryDecisions[candidate.candidate_id].action)).map((candidate) => ({ candidate_id: candidate.candidate_id, role_code: pendingTheoryDecisions[candidate.candidate_id].action === 'adopt' ? 'primary' : 'secondary', responsibility: pendingTheoryDecisions[candidate.candidate_id].action === 'adopt' ? '核心解释视角' : '补充解释视角' })),
      },
    })
    if (result.data) {
      setDecisionSet(result.data)
      setPendingTheoryDecisions(Object.fromEntries(result.data.decisions.map((decision) => [decision.candidate_id, { candidate_version: decision.candidate_version, action: decision.action }])))
      const refreshed = await getMatchRun({ client: apiClient, path: { match_run_id: matchRun.match_run_id } })
      if (refreshed.data) setMatchRun(refreshed.data)
    }
  }

  async function confirmTheoryPlanChoice() {
    if (!decisionSet) return
    const result = await confirmTheoryPlan({
      client: apiClient,
      path: { decision_set_id: decisionSet.decision_set_id },
      headers: { 'Idempotency-Key': key() },
      body: { expected_decision_set_version: decisionSet.version },
    })
    if (result.data) setDecisionSet(null)
  }

  async function downloadDocument() {
    if (!document) return
    const result = await exportResearchDocument({ client: apiClient, path: { document_id: document.document_id }, query: { version: document.version } })
    if (!result.data) return
    const blob = new Blob([result.data.markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const anchor = globalThis.document.createElement('a')
    anchor.href = url
    anchor.download = result.data.filename
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const stageTitle = mode === 'match' ? '理论判断文档' : '研究框架文档'
  const runtimeBoundary = loadState === 'error' || agentError
  const statusText = !document ? '尚未生成文档' : saveState === 'saving' ? '正在保存…' : saveState === 'unsaved' ? '有未保存更改' : document.status === 'confirmed' ? '已确认版本' : '已保存'

  return (
    <main className="research-document-workbench" data-stage={mode}>
      <header className="research-document-workbench__header">
        <div>
          <span className="research-document-workbench__eyebrow">群学致知 · M{mode === 'match' ? '4' : '5'}</span>
          <h1>{stageTitle}</h1>
          <p>{navigation?.phenomenon_summary?.phenomenon ?? '从真实研究任务中持续整理、审阅和确认你的判断。'}</p>
        </div>
        <div className="research-document-workbench__actions">
          <span className={`document-save-status document-save-status--${saveState}`} role="status">{statusText}</span>
          <button type="button" onClick={() => void downloadDocument()} disabled={!document} aria-label="导出研究文档"><DownloadSimpleIcon /> 导出</button>
          <button type="button" onClick={() => void confirmDocument()} disabled={!document || document.status === 'confirmed'}>确认正式版本</button>
        </div>
      </header>

      <div className="research-document-workbench__grid">
        <nav className="research-document-workbench__chapters" aria-label="研究章节">
          <div className="rail-heading"><span>章节</span><span className="rail-count">{sections.length}</span></div>
          <ol>
            {sections.map((section) => (
              <li key={section.section_id}>
                <button type="button" className={section.section_id === activeSectionId ? 'is-active' : ''} onClick={() => setActiveSectionId(section.section_id)}>
                  <span>{section.title}</span>
                  {section.status === 'confirmed' || section.status === 'reviewed' ? <CheckCircleIcon aria-label="已审阅" /> : <span className="chapter-dot" aria-label="待审阅" />}
                </button>
              </li>
            ))}
          </ol>
          <div className="chapter-footer">
            <span>知识发布</span>
            <code>{document?.knowledge_release_id ?? '未绑定'}</code>
          </div>
        </nav>

        <section className="research-document-workbench__editor" aria-label="研究文档编辑区">
          <div className="document-paper">
            <div className="document-paper__meta"><span>{mode === 'match' ? '理论判断' : '研究设计'}</span><span>v{document?.version ?? '—'}</span></div>
            {loadState === 'loading' ? <div className="document-loading"><CircleNotchIcon className="spin" /> 正在恢复文档版本…</div> : (
              <>
                <h2 id="research-document-heading" aria-label="研究文档正文">{activeSection?.title ?? '研究文档正文'}</h2>
                {runtimeBoundary && <div className="document-boundary"><WarningCircleIcon /> {error ?? '当前 Agent 运行环境未连接；不会把静态示例当作真实研究结果。'}</div>}
                {mode === 'match' && matchRun ? <section className="theory-candidates" aria-label="候选理论">
                  <div className="theory-candidates__heading"><span>候选理论</span><small>{matchRun.candidate_page.candidates.length} 个候选 · release {matchRun.knowledge_release_id}</small></div>
                  {matchRun.candidate_page.candidates.map((candidate) => <article key={candidate.candidate_id} className="theory-candidate">
                    <div><h3>{candidate.title}</h3><p>{candidate.applicability_rationale}</p></div>
                    <div className="theory-candidate__actions"><button type="button" aria-pressed={pendingTheoryDecisions[candidate.candidate_id]?.action === 'adopt'} onClick={() => recordTheoryDecision(candidate.candidate_id, candidate.version, 'adopt')}>采用</button><button type="button" aria-pressed={pendingTheoryDecisions[candidate.candidate_id]?.action === 'combine'} onClick={() => recordTheoryDecision(candidate.candidate_id, candidate.version, 'combine')}>组合</button><button type="button" aria-pressed={pendingTheoryDecisions[candidate.candidate_id]?.action === 'retain'} onClick={() => recordTheoryDecision(candidate.candidate_id, candidate.version, 'retain')}>保留</button><button type="button" aria-pressed={pendingTheoryDecisions[candidate.candidate_id]?.action === 'exclude'} onClick={() => recordTheoryDecision(candidate.candidate_id, candidate.version, 'exclude')}>排除</button></div>
                  </article>)}
                  {selectedTheoryIds.length > 1 ? <fieldset className="theory-relation-editor"><legend>说明组合理论的关系</legend><textarea aria-label="组合关系说明" value={relationDraft.explanation} onChange={(event) => setRelationDraft((current) => ({ ...current, explanation: event.target.value }))} placeholder="两个理论如何共同解释研究问题" /><textarea aria-label="前提兼容性" value={relationDraft.premise} onChange={(event) => setRelationDraft((current) => ({ ...current, premise: event.target.value }))} placeholder="两者前提在哪些条件下兼容" /><textarea aria-label="支持证据要求" value={relationDraft.supporting} onChange={(event) => setRelationDraft((current) => ({ ...current, supporting: event.target.value }))} placeholder="什么证据支持组合解释" /><textarea aria-label="排除证据要求" value={relationDraft.excluding} onChange={(event) => setRelationDraft((current) => ({ ...current, excluding: event.target.value }))} placeholder="什么证据会排除组合解释" /><textarea aria-label="区分证据要求" value={relationDraft.distinguishing} onChange={(event) => setRelationDraft((current) => ({ ...current, distinguishing: event.target.value }))} placeholder="什么证据能区分各理论贡献" /></fieldset> : null}
                  <button type="button" disabled={Object.keys(pendingTheoryDecisions).length !== matchRun.candidate_page.candidates.length || !multiTheoryRelationReady} onClick={() => void submitTheoryDecisions()}>保存完整理论决定</button>
                  {decisionSet ? <button type="button" disabled={!decisionSet.allowed_actions.includes('confirm_theory_plan')} onClick={() => void confirmTheoryPlanChoice()}>确认理论方案，进入 M5</button> : null}
                </section> : null}
                {document ? <>
                  <EditorContent editor={editor} className="research-document-editor" aria-label="研究文档正文" />
                  <div className="document-evidence">
                    <span>证据边注</span>
                    {activeSection?.evidence_refs?.length ? activeSection.evidence_refs.map((ref) => <code key={ref.evidence_ref_id}>{ref.source_id} · {ref.knowledge_release_id}</code>) : <em>本节尚未绑定真实来源；Agent 不会猜测引用。</em>}
                  </div>
                  <details className="document-versions">
                    <summary>版本与恢复（{versions.length || document.version}）</summary>
                    <ol>
                      {(versions.length ? versions : [document]).map((version) => <li key={version.version}>
                        <span>v{version.version} · {version.actor}</span>
                        <button type="button" disabled={version.version === document.version} onClick={() => void restoreVersion(version.version)}>{version.version === document.version ? '当前版本' : '恢复'}</button>
                      </li>)}
                    </ol>
                  </details>
                </> : <div className="document-empty" role="status">尚未生成可编辑研究文档。请让研究 Agent 先生成草案，或完成前置理论决定。</div>}
              </>
            )}
          </div>
        </section>

        <aside className="research-document-workbench__agent" aria-label="研究 Agent">
          <div className="agent-panel__heading"><div><span className="agent-kicker">协作者</span><h2>{runtimeMode === 'mock' ? '预览 Agent' : runtimeMode === null ? 'Agent（待确认运行时）' : '研究 Agent'}</h2></div><span className={`agent-status agent-status--${agentState}`}><i />{agentState === 'retrieving' ? '检索中' : agentState === 'thinking' ? '思考中' : agentState === 'answering' ? '已回应' : agentState === 'error' ? '需重试' : '待命'}</span></div>
          <div className="agent-panel__context"><span>当前选中</span><strong>{activeSection?.title}</strong><small>{runtimeMode === 'mock' ? '当前为预览运行时；不会把模拟结果当作真实研究结论。' : '请求使用研究 Agent 会话；证据与知识发布以服务返回为准。'}</small></div>
          <div className="agent-panel__stream" aria-live="polite">
            {toolSteps.map((step) => <div className={`tool-trace tool-trace--${step.status}`} key={step.id}><span>{step.status === 'running' ? '↻' : step.status === 'failed' ? '!' : '✓'}</span><span>{step.label}</span><small>{step.status}</small></div>)}
            {agentAnswer && <p className="agent-answer">{agentAnswer}</p>}
            {citations.length ? <div className="agent-citations" aria-label="Agent 引用"><span>本轮引用</span>{citations.map((citation) => <code key={citation.citation_id}>{citation.label} · {citation.source_id ?? citation.knowledge_id ?? '来源 ID 未返回'}</code>)}</div> : null}
            {agentError && <p className="agent-error">{agentError}</p>}
            {!agentAnswer && !agentError && !toolSteps.length && <p className="agent-empty">选中一段正文后，可以让 Agent 补反例、换理论视角或检查研究设计一致性。</p>}
          </div>
          {proposals.filter((proposal) => proposal.status === 'pending').map((proposal) => <div className="proposal-card" key={proposal.proposal_id}><span>待审批建议</span><p>{proposal.rationale}</p><div><button type="button" onClick={() => void acceptProposal(proposal)}>接受局部修改</button><button type="button" onClick={() => void rejectProposal(proposal)}>拒绝建议</button></div></div>)}
          <form className="agent-composer" onSubmit={(event) => { event.preventDefault(); void askAgent() }}>
            <textarea aria-label="给研究 Agent 的请求" value={agentDraft} onChange={(event) => setAgentDraft(event.target.value)} placeholder="例如：补一个反例，并让这段判断更谨慎" rows={3} />
            <button type="submit" disabled={!agentDraft.trim() || agentState === 'thinking' || agentState === 'retrieving'}><PaperPlaneTiltIcon /> 发送</button>
          </form>
          {agentState === 'thinking' || agentState === 'retrieving' ? <button type="button" className="agent-stop" onClick={() => abortRef.current?.abort()}>中断本次请求</button> : null}
        </aside>
      </div>
    </main>
  )
}
