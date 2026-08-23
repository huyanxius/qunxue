import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Markdown } from '@tiptap/markdown'
import { CheckCircleIcon, CircleNotchIcon, DownloadSimpleIcon, WarningCircleIcon } from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'

import {
  acceptResearchDocumentProposal,
  acknowledgePartialMatch,
  createTheoryDecisions,
  confirmTheoryPlan,
  confirmResearchDocument,
  createMatchRun,
  exportResearchDocument,
  getMatchRun,
  getResearchTaskNavigation,
  listResearchDocuments,
  listResearchDocumentVersions,
  listResearchTaskDocumentProposals,
  listTheoryDecisions,
  restoreResearchDocument,
  rejectResearchDocumentProposal,
  readResearchTaskNavigationViaApi,
  updateResearchDocument,
} from '../../api/researchWorkspace'
import { ResearchAgentConversationPage } from '../agent/ResearchAgentConversationPage'
import { ResearchMapCanvas } from './ResearchMapCanvas'
import { projectResearchCanvas, type ResearchCanvasProjection } from '../../modules/research-workspace'
import type { AgentConversation } from '../../modules/research-agent'
import { PageContent, PageShell } from '../ui/PageShell'
import { M5ResearchDeliveryController } from './M5ResearchDeliveryController'
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
type ResearchDocumentProposalResponse = NonNullable<Awaited<ReturnType<typeof listResearchTaskDocumentProposals>>['data']>['items'][number]
type ResearchDocumentResponse = NonNullable<Awaited<ReturnType<typeof listResearchDocuments>>['data']>['items'][number]
type ResearchTaskNavigationResponse = NonNullable<Awaited<ReturnType<typeof getResearchTaskNavigation>>['data']>
type MatchRunResponse = NonNullable<Awaited<ReturnType<typeof getMatchRun>>['data']>
type TheoryDecisionSetResponse = NonNullable<Awaited<ReturnType<typeof listTheoryDecisions>>['data']>['decision_sets'][number]
type TheoryDecisionAction = TheoryDecisionSetResponse['decisions'][number]['action']

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

export function ResearchDocumentWorkbench({ userId = null }: { userId?: string | null }) {
  const { task_id: taskId, stage: stageParam } = useParams<{ task_id: string; stage?: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const stage = stageParam ?? (location.pathname.endsWith('/framework') ? 'framework' : 'match')
  const mode = stage === 'framework' ? 'framework' : 'match'
  const [navigation, setNavigation] = useState<ResearchTaskNavigationResponse | null>(null)
  const [document, setDocument] = useState<ResearchDocumentResponse | null>(null)
  const [proposals, setProposals] = useState<ResearchDocumentProposalResponse[]>([])
  const [versions, setVersions] = useState<ResearchDocumentResponse[]>([])
  const [activeSectionId, setActiveSectionId] = useState<SectionKey>(mode === 'match' ? M4_SECTIONS[0][0] : M5_SECTIONS[0][0])
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)
  const [matchRun, setMatchRun] = useState<MatchRunResponse | null>(null)
  const [matchingActionState, setMatchingActionState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [matchingActionError, setMatchingActionError] = useState<string | null>(null)
  const [pendingTheoryDecisions, setPendingTheoryDecisions] = useState<Record<string, { candidate_version: number; action: TheoryDecisionAction }>>({})
  const [decisionSet, setDecisionSet] = useState<TheoryDecisionSetResponse | null>(null)
  const [relationDraft, setRelationDraft] = useState({ explanation: '', premise: '', supporting: '', excluding: '', distinguishing: '' })
  const [saveState, setSaveState] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  const [agentConversation, setAgentConversation] = useState<AgentConversation | null>(null)
  const sectionNodePrefix = `research-section:${taskId ?? 'unknown'}:${mode}:`
  const [selectedMapNodeId, setSelectedMapNodeId] = useState<string | null>(null)
  const matchingAttemptKeyRef = useRef<string | null>(null)
  const matchingInFlightRef = useRef(false)
  const saveInFlightRef = useRef<Promise<ResearchDocumentResponse | null> | null>(null)

  const sections = useMemo(() => document?.sections.length ? document.sections : sectionFallback(mode), [document?.sections, mode])
  const activeSection = sections.find((section) => section.section_id === activeSectionId) ?? sections[0]
  const activeContent = activeSection?.content ?? ''
  const selectedTheoryIds = Object.entries(pendingTheoryDecisions).filter(([, value]) => value.action === 'adopt' || value.action === 'combine').map(([candidateId]) => candidateId)
  const multiTheoryRelationReady = selectedTheoryIds.length < 2 || Object.values(relationDraft).every((value) => value.trim())
  const mapProjection = useMemo<ResearchCanvasProjection>(() => {
    const projected = projectResearchCanvas({ conversation: agentConversation })
    const questionNode = projected.nodes.find((node) => node.kind === 'question')
    const fallbackQuestionId = `research-question:${taskId ?? 'unknown'}`
    const phenomenonId = `research-phenomenon:${taskId ?? 'unknown'}`
    const nodes: ResearchCanvasProjection['nodes'] = questionNode ? [...projected.nodes] : [
      ...projected.nodes,
      {
        id: fallbackQuestionId,
        kind: 'question',
        title: navigation?.phenomenon_summary?.phenomenon ?? '当前研究问题',
        summary: navigation?.phenomenon_summary?.research_intent ?? '从已经确认的研究起点继续推进。',
        excerpt: navigation?.phenomenon_summary?.research_intent ?? null,
        status: 'grounded',
        provenance: 'user',
        citationIds: [],
      },
    ]
    if (navigation?.phenomenon_summary) nodes.push({
      id: phenomenonId,
      kind: 'phenomenon',
      title: navigation.phenomenon_summary.phenomenon,
      summary: navigation.phenomenon_summary.research_intent ?? '已经确认并固定到当前研究任务的核心现象。',
      excerpt: navigation.phenomenon_summary.research_intent ?? null,
      status: 'grounded',
      provenance: 'user',
      citationIds: [],
    })
    const candidateTheoryNodes = matchRun?.candidate_page.candidates.map((candidate) => ({
      id: `research-theory:${candidate.candidate_id}`,
      kind: 'theory' as const,
      title: candidate.title,
      summary: candidate.applicability_rationale,
      excerpt: candidate.problem_focus || candidate.applicability_rationale,
      status: pendingTheoryDecisions[candidate.candidate_id]?.action === 'adopt' || pendingTheoryDecisions[candidate.candidate_id]?.action === 'combine' ? 'grounded' as const : 'developing' as const,
      provenance: 'knowledge' as const,
      citationIds: candidate.source_ids ?? [],
    })) ?? []
    nodes.push(...candidateTheoryNodes)
    const evidenceById = new Map<string, ResearchCanvasProjection['nodes'][number]>()
    for (const candidate of matchRun?.candidate_page.candidates ?? []) {
      for (const evidence of [...(candidate.supporting_evidence ?? []), ...(candidate.conflicting_evidence ?? [])]) {
        const evidenceId = `research-evidence:${evidence.evidence_ref_id}`
        evidenceById.set(evidenceId, {
          id: evidenceId,
          kind: 'evidence',
          title: evidence.claim,
          summary: evidence.excerpt ?? evidence.locator ?? '来自固定知识发布的证据。',
          excerpt: evidence.excerpt,
          status: 'verified',
          provenance: 'knowledge',
          citationIds: evidence.source_id ? [evidence.source_id] : [],
        })
      }
    }
    nodes.push(...evidenceById.values())
    const sectionNodes = sections.map((section) => ({
      id: `${sectionNodePrefix}${section.section_id}`,
      kind: 'document' as const,
      title: section.title,
      summary: section.content.trim().replace(/[#*_`>\n]+/g, ' ').replace(/\s+/g, ' ').slice(0, 92),
      excerpt: section.content || null,
      status: section.status === 'confirmed' || section.status === 'reviewed' ? 'complete' as const : 'developing' as const,
      provenance: 'user' as const,
      citationIds: section.evidence_refs.map((reference) => reference.source_id),
    }))
    nodes.push(...sectionNodes)
    const source = navigation?.phenomenon_summary ? phenomenonId : questionNode?.id ?? fallbackQuestionId
    const stageEdges: ResearchCanvasProjection['edges'] = []
    if (navigation?.phenomenon_summary) stageEdges.push({
      id: `research-phenomenon-edge:${taskId ?? 'unknown'}`,
      source: questionNode?.id ?? fallbackQuestionId,
      target: phenomenonId,
      relation: 'refines',
      label: '确认现象',
    })
    for (const candidate of matchRun?.candidate_page.candidates ?? []) {
      const theoryId = `research-theory:${candidate.candidate_id}`
      stageEdges.push({ id: `research-theory-edge:${candidate.candidate_id}`, source, target: theoryId, relation: 'explains', label: '候选解释' })
      for (const evidence of candidate.supporting_evidence ?? []) stageEdges.push({ id: `research-support:${candidate.candidate_id}:${evidence.evidence_ref_id}`, source: `research-evidence:${evidence.evidence_ref_id}`, target: theoryId, relation: 'supports', label: '支持' })
      for (const evidence of candidate.conflicting_evidence ?? []) stageEdges.push({ id: `research-challenge:${candidate.candidate_id}:${evidence.evidence_ref_id}`, source: `research-evidence:${evidence.evidence_ref_id}`, target: theoryId, relation: 'challenges', label: '质疑' })
    }
    const firstLayerSize = Math.ceil(sectionNodes.length / 2)
    const sectionEdges = sectionNodes.map((node, index) => ({
      id: `research-section-edge:${index}:${node.id}`,
      source: index < firstLayerSize ? source : sectionNodes[index - firstLayerSize].id,
      target: node.id,
      relation: 'refines' as const,
      label: '',
    }))
    return {
      ...projected,
      status: 'ready',
      question: navigation?.phenomenon_summary?.phenomenon ?? document?.title ?? projected.question,
      nodes,
      edges: [...projected.edges, ...stageEdges, ...sectionEdges],
    }
  }, [agentConversation, document?.title, matchRun, navigation?.phenomenon_summary, pendingTheoryDecisions, sectionNodePrefix, sections, taskId])
  const editor = useEditor({
    extensions: [StarterKit, Markdown],
    content: activeContent || '在这里写下你的研究判断。每次用户编辑都会形成可恢复的文档版本。',
    contentType: 'markdown',
    immediatelyRender: false,
    editorProps: { attributes: { 'aria-labelledby': 'research-document-heading' } },
    onUpdate: () => setSaveState('unsaved'),
  })

  useEffect(() => {
    if (!editor || !activeSection) return
    editor.commands.setContent(activeSection.content || '在这里写下你的研究判断。每次用户编辑都会形成可恢复的文档版本。', { contentType: 'markdown' })
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
      Promise.resolve().then(() => getResearchTaskNavigation({ path: { task_id: taskId } })),
      Promise.resolve().then(() => listResearchDocuments({ path: { task_id: taskId } })),
    ]).then(async ([nav, docs]) => {
      if (disposed) return
      if (!nav.data || !docs.data) throw new Error('研究工作区暂时无法加载。')
      setNavigation(nav.data)
      if (mode === 'match' && (nav.data.allowed_actions?.includes('start_matching') || nav.data.current_match_run_id)) {
        setActiveSectionId('candidate_theories')
      }
      if (mode === 'match' && nav.data.current_match_run_id) {
        const match = await getMatchRun({ path: { match_run_id: nav.data.current_match_run_id } })
        if (match.data) setMatchRun(match.data)
        const decisions = await listTheoryDecisions({ path: { match_run_id: nav.data.current_match_run_id } })
        if (decisions.data?.decision_sets.length) {
          const restoredDecisionSet = decisions.data.decision_sets[0]
          setDecisionSet(restoredDecisionSet)
          setPendingTheoryDecisions(Object.fromEntries(restoredDecisionSet.decisions.map((decision) => [decision.candidate_id, { candidate_version: decision.candidate_version, action: decision.action }])))
        }
      }
      const current = selectCurrentDocument(docs.data.items, nav.data, mode)
      setDocument(current)
      setLoadState('ready')
      const taskProposals = await listResearchTaskDocumentProposals({ path: { task_id: taskId } })
      if (taskProposals.data) setProposals(taskProposals.data.items)
      if (current) {
        listResearchDocumentVersions({ path: { document_id: current.document_id } })
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
      getResearchTaskNavigation({ path: { task_id: taskId } }),
      listResearchDocuments({ path: { task_id: taskId } }),
    ])
    if (navigationResult.data) setNavigation(navigationResult.data)
    if (!result.data) return
    const latestNavigation = navigationResult.data ?? navigation
    const currentId = mode === 'framework' ? latestNavigation?.current_framework_id : latestNavigation?.current_theory_plan_id
    const current = (currentId ? result.data.items.find((item) => mode === 'framework' ? item.document_id === currentId : item.theory_plan_id === currentId) : undefined) ?? result.data.items[0] ?? null
    setDocument(current)
    const taskProposals = await listResearchTaskDocumentProposals({ path: { task_id: taskId } })
    if (taskProposals.data) setProposals(taskProposals.data.items)
    if (current) {
      const versionsResult = await listResearchDocumentVersions({ path: { document_id: current.document_id } })
      if (versionsResult.data) setVersions(versionsResult.data.items)
    }
  }, [mode, navigation, taskId])

  const resumeFromServer = useCallback(async () => {
    if (!taskId) return
    const latest = await readResearchTaskNavigationViaApi(taskId)
    setNavigation(latest)
    if (latest.resume_path !== location.pathname) {
      navigate(latest.resume_path, { replace: true })
    }
  }, [location.pathname, navigate, taskId])

  const saveSection = useCallback((): Promise<ResearchDocumentResponse | null> => {
    if (!editor || !document || !activeSection) return Promise.resolve(document)
    if (saveInFlightRef.current) return saveInFlightRef.current
    const content = editor.getMarkdown()
    if (content === activeSection.content) {
      setSaveState('saved')
      return Promise.resolve(document)
    }
    setSaveState('saving')
    const nextSections = document.sections.map((section) => section.section_id === activeSection.section_id
      ? { ...section, content }
      : section)
    let request: Promise<ResearchDocumentResponse | null>
    request = (async () => {
      try {
        const result = await updateResearchDocument({
          path: { document_id: document.document_id },
          headers: { 'Idempotency-Key': key() },
          body: { expected_version: document.version, sections: nextSections, change_summary: '用户直接编辑正文', source: 'user_edit' },
        })
        if (!result.data) throw new Error('自动保存失败，请重试。')
        setDocument(result.data)
        setSaveState('saved')
        return result.data
      } finally {
        if (saveInFlightRef.current === request) saveInFlightRef.current = null
      }
    })()
    saveInFlightRef.current = request
    return request
  }, [activeSection, document, editor])

  useEffect(() => {
    if (saveState !== 'unsaved') return
    const timer = window.setTimeout(() => { void saveSection().catch((reason: unknown) => { setSaveState('unsaved'); setError(reason instanceof Error ? reason.message : '自动保存失败。') }) }, 900)
    return () => window.clearTimeout(timer)
  }, [saveSection, saveState])

  async function startMatching() {
    const phenomenon = navigation?.phenomenon_summary
    if (
      !taskId
      || mode !== 'match'
      || matchingInFlightRef.current
      || !navigation?.allowed_actions?.includes('start_matching')
      || !phenomenon
      || !navigation.knowledge_release_id
    ) return
    const idempotencyKey = matchingAttemptKeyRef.current ?? key()
    matchingAttemptKeyRef.current = idempotencyKey
    matchingInFlightRef.current = true
    setMatchingActionState('loading')
    setMatchingActionError(null)
    try {
      const result = await createMatchRun({
        path: { task_id: taskId },
        headers: { 'Idempotency-Key': idempotencyKey },
        body: {
          expected_task_version: navigation.version,
          phenomenon_query_id: phenomenon.phenomenon_query_id,
          phenomenon_version: phenomenon.version,
          knowledge_release_id: navigation.knowledge_release_id,
        },
      })
      if (!result.data) throw new Error('理论匹配暂时未能启动。')
      matchingAttemptKeyRef.current = null
      setMatchRun(result.data)
      setNavigation((current) => current
        ? {
            ...current,
            version: current.version === navigation.version ? current.version + 1 : current.version,
            current_match_run_id: result.data!.match_run_id,
          }
        : current)
      const latest = await getResearchTaskNavigation({ path: { task_id: taskId } })
      if (latest.data) {
        setNavigation(latest.data)
        setMatchingActionState('idle')
      } else {
        setMatchingActionState('error')
        setMatchingActionError('匹配结果已保存，但进度刷新失败。刷新页面即可从服务端恢复。')
      }
    } catch (reason: unknown) {
      setMatchingActionState('error')
      setMatchingActionError(
        reason instanceof Error
          ? reason.message
          : '理论匹配暂时未能启动，研究状态和固定知识发布均已保留。',
      )
    } finally {
      matchingInFlightRef.current = false
    }
  }

  async function acceptProposal(proposal: ResearchDocumentProposalResponse) {
    if (proposal.status !== 'pending') return
    if (proposal.kind !== 'create' && !document) return
    const result = await acceptResearchDocumentProposal({
      path: { proposal_id: proposal.proposal_id },
      headers: { 'Idempotency-Key': key() },
      body: { expected_document_version: proposal.kind === 'create' ? null : document!.version },
    })
    if (result.data) {
      setDocument(result.data.document)
      setProposals((current) => current.map((item) => item.proposal_id === proposal.proposal_id ? result.data!.proposal : item))
      await refreshDocumentState()
      await resumeFromServer()
    }
  }

  async function rejectProposal(proposal: ResearchDocumentProposalResponse) {
    if (proposal.status !== 'pending') return
    const result = await rejectResearchDocumentProposal({
      path: { proposal_id: proposal.proposal_id },
      headers: { 'Idempotency-Key': key() },
      body: { reason: '用户拒绝本次局部修改建议。' },
    })
    if (result.data) setProposals((current) => current.map((item) => item.proposal_id === proposal.proposal_id ? result.data! : item))
  }

  async function confirmDocument() {
    if (!document) return
    const latestDocument = await saveSection() ?? document
    const result = await confirmResearchDocument({ path: { document_id: latestDocument.document_id }, headers: { 'Idempotency-Key': key() }, body: { expected_version: latestDocument.version } })
    if (result.data) {
      setDocument(result.data)
      await resumeFromServer()
    }
  }

  async function restoreVersion(version: number) {
    if (!document || version === document.version) return
    const result = await restoreResearchDocument({
      path: { document_id: document.document_id },
      headers: { 'Idempotency-Key': key() },
      body: { source_version: version, expected_version: document.version, reason: `恢复到第 ${version} 版` },
    })
    if (result.data) {
      setDocument(result.data)
      setVersions((current) => [result.data!, ...current.filter((item) => item.version !== result.data!.version)])
    }
  }

  function openSectionNode(nodeId: string) {
    setSelectedMapNodeId(nodeId)
    if (nodeId.startsWith(sectionNodePrefix)) setActiveSectionId(nodeId.slice(sectionNodePrefix.length))
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
      const refreshed = await getMatchRun({ path: { match_run_id: matchRun.match_run_id } })
      if (refreshed.data) setMatchRun(refreshed.data)
      await resumeFromServer()
    }
  }

  async function confirmTheoryPlanChoice() {
    if (!decisionSet) return
    const result = await confirmTheoryPlan({
      path: { decision_set_id: decisionSet.decision_set_id },
      headers: { 'Idempotency-Key': key() },
      body: { expected_decision_set_version: decisionSet.version },
    })
    if (result.data) {
      setDecisionSet(null)
      await resumeFromServer()
    }
  }

  async function downloadDocument() {
    if (!document) return
    const result = await exportResearchDocument({ path: { document_id: document.document_id }, query: { version: document.version } })
    if (!result.data) return
    const blob = new Blob([result.data.markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const anchor = globalThis.document.createElement('a')
    anchor.href = url
    anchor.download = result.data.filename
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const runtimeBoundary = loadState === 'error'
  const statusText = saveState === 'saving' ? '正在保存…' : saveState === 'unsaved' ? '有未保存更改' : null
  const documentNodeContent = (
    <section className="research-document-node" aria-label="研究文档节点">
      <div className="research-document-node__topbar">
        <span className="research-document-node__chapter-status">
          {activeSection?.status === 'confirmed' || activeSection?.status === 'reviewed' ? <><CheckCircleIcon /> 已审阅</> : null}
        </span>
        <div className="research-document-node__actions">
          {statusText ? <span className={`document-save-status document-save-status--${saveState}`} role="status">{statusText}</span> : null}
          <button type="button" onClick={() => void downloadDocument()} disabled={!document} aria-label="导出研究文档"><DownloadSimpleIcon /> 导出</button>
          <button type="button" onClick={() => void confirmDocument()} disabled={!document || document.status === 'confirmed'}>{document?.status === 'confirmed' ? '已确认' : '确认版本'}</button>
          <button type="button" className="research-document-node__collapse" onClick={(event) => { event.stopPropagation(); setSelectedMapNodeId(null) }}>收起</button>
        </div>
      </div>

      <div className="research-document-node__body">
        {mode === 'framework' && taskId && navigation?.current_theory_plan_id ? (
          <div className="research-document-workbench__delivery">
            <M5ResearchDeliveryController
              taskId={taskId}
              theoryPlanId={navigation.current_theory_plan_id}
              conversationId={navigation.conversation_id}
              saveState={saveState}
              onChanged={() => { void refreshDocumentState() }}
            />
          </div>
        ) : null}
        {proposals.some((proposal) => proposal.status === 'pending') ? (
          <section className="document-proposals" aria-label="Agent 修订建议">
            <header><span>Agent 修订建议</span><small>修改只会在你确认后写入正文</small></header>
            {proposals.filter((proposal) => proposal.status === 'pending').map((proposal) => (
              <article className="proposal-card" key={proposal.proposal_id}>
                <p>{proposal.rationale}</p>
                <div>
                  <button type="button" onClick={() => void acceptProposal(proposal)}>接受局部修改</button>
                  <button type="button" onClick={() => void rejectProposal(proposal)}>拒绝建议</button>
                </div>
              </article>
            ))}
          </section>
        ) : null}

        {loadState === 'loading' ? <div className="document-loading"><CircleNotchIcon className="spin" /> 正在恢复文档版本…</div> : (
          <>
            <h2 id="research-document-heading" aria-label="研究文档正文">{activeSection?.title ?? '研究文档正文'}</h2>
            {runtimeBoundary && <div className="document-boundary"><WarningCircleIcon /> {error ?? '当前 Agent 运行环境未连接；不会把静态示例当作真实研究结果。'}</div>}
            {mode === 'match' && activeSection?.section_id === 'candidate_theories' && navigation?.allowed_actions?.includes('start_matching') && (!matchRun || matchRun.status === 'no_reliable_candidate') ? (
              <section className="document-boundary document-boundary--action" aria-label="理论匹配操作" aria-busy={matchingActionState === 'loading'}>
                <WarningCircleIcon />
                <div>
                  <strong>{navigation.blocker?.message ?? '现象已确认，可以开始理论匹配。'}</strong>
                  {matchingActionError ? <p role="alert">{matchingActionError}</p> : null}
                  <button type="button" disabled={matchingActionState === 'loading'} onClick={() => void startMatching()}>
                    {matchingActionState === 'loading' ? <><CircleNotchIcon className="spin" /> 正在匹配…</> : navigation.retry?.label ?? (matchRun?.status === 'no_reliable_candidate' ? '重新匹配' : '开始理论匹配')}
                  </button>
                </div>
              </section>
            ) : null}
            {mode === 'match' && activeSection?.section_id === 'candidate_theories' && matchRun && matchRun.status !== 'no_reliable_candidate' ? <section className="theory-candidates" aria-label="候选理论">
              <div className="theory-candidates__heading"><span>候选理论</span><small>{matchRun.candidate_page.candidates.length} 个候选</small></div>
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
                {activeSection?.evidence_refs?.length ? activeSection.evidence_refs.map((ref) => <code key={ref.evidence_ref_id}>{ref.source_id}</code>) : <em>本节尚未引用来源</em>}
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
            </> : <div className="document-empty" role="status">{activeSection?.section_id === 'candidate_theories' ? '在这个节点开始理论匹配，候选会直接回到画布。' : '这一部分会随着研究推进形成可编辑内容。'}</div>}
          </>
        )}
      </div>

    </section>
  )

  return (
    <PageShell workspace wide>
      <PageContent>
        <main className="research-document-workbench" data-stage={mode}>
          <h1 className="research-document-workbench__title">
            {mode === 'framework' ? '研究框架文档' : '理论判断文档'}
          </h1>
          <div className="research-document-workbench__workspace">
            <ResearchMapCanvas
              projection={mapProjection}
              selectedNodeId={selectedMapNodeId}
              onSelectNode={(node) => openSectionNode(node.id)}
              onClearSelection={() => setSelectedMapNodeId(null)}
              onContinueNode={(node) => openSectionNode(node.id)}
              expandedNodeContent={selectedMapNodeId?.startsWith(sectionNodePrefix) ? { [selectedMapNodeId]: documentNodeContent } : {}}
            />

            <ResearchAgentConversationPage
              embedded
              userId={userId}
              conversationId={navigation?.conversation_id ?? null}
              knowledgeReleaseId={navigation?.knowledge_release_id ?? document?.knowledge_release_id ?? null}
              workspace="research"
              taskId={taskId ?? null}
              documentId={document?.document_id ?? null}
              sectionId={activeSection?.section_id ?? null}
              documentVersion={document?.version ?? null}
              theoryPlanId={navigation?.current_theory_plan_id ?? null}
              onConversationChange={setAgentConversation}
              onTurnCompleted={() => { void refreshDocumentState() }}
            />
          </div>
        </main>
      </PageContent>
    </PageShell>
  )
}
