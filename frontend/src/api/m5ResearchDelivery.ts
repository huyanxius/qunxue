import { apiClient } from './client'
import {
  acceptResearchDocumentProposal as acceptProposalRequest,
  confirmResearchDocument as confirmDocumentRequest,
  createResearchDocument as createDocumentRequest,
  exportResearchDocument as exportDocumentRequest,
  getResearchDocumentCompletionGate as getCompletionGateRequest,
  listResearchDocuments as listDocumentsRequest,
  listResearchDocumentVersions as listVersionsRequest,
  listResearchTaskDocumentProposals as listTaskProposalsRequest,
  rejectResearchDocumentProposal as rejectProposalRequest,
  restoreResearchDocument as restoreDocumentRequest,
  updateResearchDocument as updateDocumentRequest,
  type ResearchDocumentCompletionGateResponse,
  type ResearchDocumentExportResponse,
  type ResearchDocumentProposalResponse,
  type ResearchDocumentResponse,
} from './generated'

function withClient<T extends object>(options: T): T & { client: typeof apiClient } {
  return { ...options, client: apiClient }
}

type ApiResult<T> = Readonly<{
  data?: T
  error?: unknown
  response?: Response
}>

function apiErrorMessage(error: unknown, fallback: string) {
  if (typeof error !== 'object' || error === null || !('error' in error)) return fallback
  const detail = error.error
  if (typeof detail !== 'object' || detail === null || !('message' in detail)) return fallback
  return typeof detail.message === 'string' && detail.message.trim() ? detail.message : fallback
}

export class M5ResearchDeliveryError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null = null) {
    super(message)
    this.name = 'M5ResearchDeliveryError'
    this.status = status
  }
}

function requireData<T>(result: ApiResult<T>, fallback: string): T {
  if (result.data !== undefined) return result.data
  throw new M5ResearchDeliveryError(
    apiErrorMessage(result.error, fallback),
    result.response?.status ?? null,
  )
}

export type M5DeliveryPhase =
  | 'awaiting_generation'
  | 'awaiting_review'
  | 'editing'
  | 'ready_to_complete'
  | 'completed'

export type M5SectionStatus =
  | 'draft'
  | 'reviewed'
  | 'evidence_gap'
  | 'needs_user_decision'
  | 'confirmed'

export type M5EvidenceReference = Readonly<{
  evidenceRefId: string
  knowledgeReleaseId: string
  sourceId: string
}>

export type M5ResearchDocumentSection = Readonly<{
  sectionId: string
  key: string
  title: string
  content: string
  status: M5SectionStatus
  evidenceRefs: readonly M5EvidenceReference[]
}>

export type M5ResearchDocument = Readonly<{
  analysisBasis: M5ResearchAnalysisBasis | null
  actor: string
  changeSummary: string
  confirmedAt: string | null
  createdAt: string
  documentId: string
  knowledgeReleaseId: string
  restoredFromVersion: number | null
  revisionId: string
  sections: readonly M5ResearchDocumentSection[]
  status: 'draft' | 'confirmed'
  taskId: string
  theoryPlanId: string
  title: string
  version: number
}>

export type M5ProposalStatus = 'pending' | 'accepted' | 'rejected' | 'aborted'

export type M5ResearchDocumentProposal = Readonly<{
  proposalId: string
  agentRunId: string
  modelProvider: string | null
  modelName: string | null
  baseDocumentVersion: number | null
  conversationId: string
  createdAt: string
  decidedAt: string | null
  decisionReason: string | null
  documentId: string | null
  kind: 'create' | 'revise_section'
  knowledgeReleaseId: string
  proposedSections: readonly M5ResearchDocumentSection[]
  rationale: string
  requiresUserApproval: boolean
  resultDocumentId: string | null
  resultDocumentVersion: number | null
  status: M5ProposalStatus
  targetSectionId: string | null
  taskId: string
  theoryPlanId: string
  title: string
  userId: string
}>

export type M5CompletionCheck = Readonly<{
  code: string
  detail: string
  label: string
  passed: boolean
}>

export type M5CompletionStatus = Readonly<{
  documentId: string | null
  version: number | null
  ready: boolean
  completed: boolean
  pendingProposalCount: number
  blockers: readonly string[]
  checks: readonly M5CompletionCheck[]
}>

export type M5ResearchAnalysisBasis = Readonly<{
  contentHash: string
  codes: readonly Readonly<{ id: string; label: string; definition: string }>[]
  memos: readonly Readonly<{ id: string; title: string; kindLabel: string }>[]
  comparisons: readonly Readonly<{
    id: string
    title: string
    theoryImplication: string
  }>[]
  unavailableAnnotationCount: number
}>

export type M5ResearchDeliveryState = Readonly<{
  taskId: string
  confirmedTheoryPlanId: string
  phase: M5DeliveryPhase
  document: M5ResearchDocument | null
  proposals: readonly M5ResearchDocumentProposal[]
  versions: readonly M5ResearchDocument[]
  completion: M5CompletionStatus
}>

function mapSection(
  section: ResearchDocumentResponse['sections'][number],
): M5ResearchDocumentSection {
  return {
    sectionId: section.section_id,
    key: section.key,
    title: section.title,
    content: section.content,
    status: section.status,
    evidenceRefs: (section.evidence_refs ?? []).map((reference) => ({
      evidenceRefId: reference.evidence_ref_id,
      knowledgeReleaseId: reference.knowledge_release_id,
      sourceId: reference.source_id,
    })),
  }
}

function toSectionContract(section: M5ResearchDocumentSection) {
  return {
    section_id: section.sectionId,
    key: section.key,
    title: section.title,
    content: section.content,
    status: section.status,
    evidence_refs: section.evidenceRefs.map((reference) => ({
      evidence_ref_id: reference.evidenceRefId,
      knowledge_release_id: reference.knowledgeReleaseId,
      source_id: reference.sourceId,
    })),
  }
}

const memoKindLabels: Readonly<Record<string, string>> = {
  descriptive: '描述备忘',
  reflexive: '反思备忘',
  analytic: '分析备忘',
  methodological: '方法备忘',
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function values(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function mapResearchAnalysisBasis(value: unknown): M5ResearchAnalysisBasis | null {
  const handoff = object(value)
  const contentHash = text(handoff.content_hash)
  if (!contentHash) return null
  return {
    contentHash,
    codes: values(handoff.codes).map(object).map((code) => ({
      id: text(code.code_id),
      label: text(code.label),
      definition: text(code.definition),
    })).filter((code) => code.id && code.label),
    memos: values(handoff.memos).map(object).map((memo) => ({
      id: text(memo.memo_id),
      title: text(memo.title),
      kindLabel: memoKindLabels[text(memo.memo_kind)] ?? '分析备忘',
    })).filter((memo) => memo.id && memo.title),
    comparisons: values(handoff.comparisons).map(object).map((comparison) => ({
      id: text(comparison.comparison_id),
      title: text(comparison.title),
      theoryImplication: text(comparison.theory_implication),
    })).filter((comparison) => comparison.id && comparison.title),
    unavailableAnnotationCount: values(handoff.unavailable_annotation_ids).length,
  }
}

function mapDocument(document: ResearchDocumentResponse): M5ResearchDocument {
  return {
    analysisBasis: mapResearchAnalysisBasis(
      document.research_analysis,
    ),
    actor: document.actor,
    changeSummary: document.change_summary,
    confirmedAt: document.confirmed_at,
    createdAt: document.created_at,
    documentId: document.document_id,
    knowledgeReleaseId: document.knowledge_release_id,
    restoredFromVersion: document.restored_from_version,
    revisionId: document.revision_id,
    sections: document.sections.map(mapSection),
    status: document.status,
    taskId: document.task_id,
    theoryPlanId: document.theory_plan_id,
    title: document.title,
    version: document.version,
  }
}

function mapProposal(proposal: ResearchDocumentProposalResponse): M5ResearchDocumentProposal {
  return {
    proposalId: proposal.proposal_id,
    agentRunId: proposal.agent_run_id,
    modelProvider: proposal.model_provider,
    modelName: proposal.model_name,
    baseDocumentVersion: proposal.base_document_version,
    conversationId: proposal.conversation_id,
    createdAt: proposal.created_at,
    decidedAt: proposal.decided_at,
    decisionReason: proposal.decision_reason,
    documentId: proposal.document_id,
    kind: proposal.kind,
    knowledgeReleaseId: proposal.knowledge_release_id,
    proposedSections: proposal.proposed_sections.map(mapSection),
    rationale: proposal.rationale,
    requiresUserApproval: proposal.requires_user_approval,
    resultDocumentId: proposal.result_document_id,
    resultDocumentVersion: proposal.result_document_version,
    status: proposal.status,
    targetSectionId: proposal.target_section_id,
    taskId: proposal.task_id,
    theoryPlanId: proposal.theory_plan_id,
    title: proposal.title,
    userId: proposal.user_id,
  }
}

function mapCompletionCheck(
  check: ResearchDocumentCompletionGateResponse['checks'][number],
): M5CompletionCheck {
  return {
    code: check.code,
    detail: check.detail,
    label: check.label,
    passed: check.passed,
  }
}

function waitingCompletion(
  proposals: readonly M5ResearchDocumentProposal[],
): M5CompletionStatus {
  const pending = proposals.filter((proposal) => proposal.status === 'pending').length
  const interrupted = proposals.some((proposal) => proposal.status === 'aborted')
  return {
    documentId: null,
    version: null,
    ready: false,
    completed: false,
    pendingProposalCount: pending,
    blockers: [
      pending > 0
        ? '请先审批待处理的 Agent 建议。'
        : interrupted
          ? '上一次生成已中断，请重试原生成请求。'
          : '尚未生成 M5 研究框架草稿。',
    ],
    checks: [],
  }
}

export async function loadM5ResearchDelivery(input: {
  taskId: string
  confirmedTheoryPlanId: string
}): Promise<M5ResearchDeliveryState> {
  const [documentsResult, proposalsResult] = await Promise.all([
    listDocumentsRequest(withClient({ path: { task_id: input.taskId } })),
    listTaskProposalsRequest(withClient({ path: { task_id: input.taskId } })),
  ])
  const documents = requireData(documentsResult, '研究文档暂时无法加载。').items
    .filter((document) => document.theory_plan_id === input.confirmedTheoryPlanId)
    .map(mapDocument)
  const proposals = requireData(proposalsResult, 'Agent 建议暂时无法加载。').items
    .filter((proposal) => proposal.theory_plan_id === input.confirmedTheoryPlanId)
    .map(mapProposal)

  if (documents.length > 1) {
    throw new M5ResearchDeliveryError(
      '检测到多份 M5 文档，系统不会任意选择其中一份。',
      409,
    )
  }

  const document = documents[0] ?? null
  if (!document) {
    const completion = waitingCompletion(proposals)
    return {
      taskId: input.taskId,
      confirmedTheoryPlanId: input.confirmedTheoryPlanId,
      phase: completion.pendingProposalCount > 0 ? 'awaiting_review' : 'awaiting_generation',
      document: null,
      proposals,
      versions: [],
      completion,
    }
  }

  const [versionsResult, gateResult] = await Promise.all([
    listVersionsRequest(withClient({ path: { document_id: document.documentId } })),
    getCompletionGateRequest(withClient({ path: { document_id: document.documentId } })),
  ])
  const versions = requireData(versionsResult, '版本历史暂时无法加载。').items.map(mapDocument)
  const gate = requireData(gateResult, '完成门禁暂时无法检查。')
  const completed = document.status === 'confirmed'
  const pendingProposalCount = proposals.filter((proposal) => proposal.status === 'pending').length
  const phase: M5DeliveryPhase = completed
    ? 'completed'
    : pendingProposalCount > 0
      ? 'awaiting_review'
      : gate.ready
        ? 'ready_to_complete'
        : 'editing'

  return {
    taskId: input.taskId,
    confirmedTheoryPlanId: input.confirmedTheoryPlanId,
    phase,
    document,
    proposals,
    versions,
    completion: {
      documentId: gate.document_id,
      version: gate.version,
      ready: gate.ready,
      completed,
      pendingProposalCount: gate.pending_proposal_count,
      blockers: gate.blockers,
      checks: gate.checks.map(mapCompletionCheck),
    },
  }
}

export async function createM5ResearchDocument(input: {
  taskId: string
  confirmedTheoryPlanId: string
  title: string
  sections: readonly M5ResearchDocumentSection[]
  idempotencyKey: string
}) {
  const result = await createDocumentRequest(withClient({
    path: { task_id: input.taskId },
    headers: { 'Idempotency-Key': input.idempotencyKey },
    body: {
      theory_plan_id: input.confirmedTheoryPlanId,
      title: input.title,
      sections: input.sections.map(toSectionContract),
    },
  }))
  return mapDocument(requireData(result, '创建 M5 研究文档失败。'))
}

export async function saveM5ResearchDocument(input: {
  documentId: string
  expectedVersion: number
  idempotencyKey: string
  sections: readonly M5ResearchDocumentSection[]
  changeSummary: string
}) {
  const result = await updateDocumentRequest(withClient({
    path: { document_id: input.documentId },
    headers: { 'Idempotency-Key': input.idempotencyKey },
    body: {
      expected_version: input.expectedVersion,
      sections: input.sections.map(toSectionContract),
      change_summary: input.changeSummary,
      source: 'user_edit',
    },
  }))
  return mapDocument(requireData(result, '保存研究文档失败，本地修改会保留。'))
}

export async function acceptM5Proposal(input: {
  proposalId: string
  expectedDocumentVersion: number | null
  idempotencyKey: string
}) {
  const result = await acceptProposalRequest(withClient({
    path: { proposal_id: input.proposalId },
    headers: { 'Idempotency-Key': input.idempotencyKey },
    body: { expected_document_version: input.expectedDocumentVersion },
  }))
  const accepted = requireData(result, '接受 Agent 建议失败。')
  return { document: mapDocument(accepted.document), proposal: mapProposal(accepted.proposal) }
}

export async function rejectM5Proposal(input: {
  proposalId: string
  reason: string
  idempotencyKey: string
}) {
  const result = await rejectProposalRequest(withClient({
    path: { proposal_id: input.proposalId },
    headers: { 'Idempotency-Key': input.idempotencyKey },
    body: { reason: input.reason },
  }))
  return mapProposal(requireData(result, '拒绝 Agent 建议失败。'))
}

export async function restoreM5ResearchDocument(input: {
  documentId: string
  expectedVersion: number
  sourceVersion: number
  reason: string
  idempotencyKey: string
}) {
  const result = await restoreDocumentRequest(withClient({
    path: { document_id: input.documentId },
    headers: { 'Idempotency-Key': input.idempotencyKey },
    body: {
      expected_version: input.expectedVersion,
      source_version: input.sourceVersion,
      reason: input.reason,
    },
  }))
  return mapDocument(requireData(result, '恢复历史版本失败。'))
}

export async function confirmM5ResearchDocument(input: {
  documentId: string
  expectedVersion: number
  idempotencyKey: string
}) {
  const result = await confirmDocumentRequest(withClient({
    path: { document_id: input.documentId },
    headers: { 'Idempotency-Key': input.idempotencyKey },
    body: { expected_version: input.expectedVersion },
  }))
  return mapDocument(requireData(result, '完成研究失败，请根据门禁提示检查。'))
}

export async function exportM5ResearchDocument(input: {
  documentId: string
  version?: number
}) {
  const result = await exportDocumentRequest(withClient({
    path: { document_id: input.documentId },
    query: { version: input.version },
  }))
  return mapExport(requireData(result, '完整研究成果包导出失败。'))
}

export type M5ExportFormat = 'markdown' | 'json'

export type M5SerializedExport = Readonly<{
  filename: string
  mediaType: string
  content: string
}>

/** Stable public shape of the versioned audit package returned by M5 export. */
export type M5ResearchExportManifest = Readonly<{
  agent_proposals: readonly Readonly<Record<string, unknown>>[]
  document_versions: readonly Readonly<Record<string, unknown>>[]
  evidence: readonly Readonly<Record<string, unknown>>[]
  formal_document: Readonly<Record<string, unknown>>
  knowledge_release: Readonly<Record<string, unknown>>
  model: Readonly<Record<string, unknown>> | null
  phenomenon: Readonly<Record<string, unknown>>
  research_analysis: unknown | null
  schema_version: 'research-delivery-v2'
  theory_assignments: readonly Readonly<Record<string, unknown>>[]
  theory_candidates: readonly Readonly<Record<string, unknown>>[]
  theory_decisions: readonly Readonly<Record<string, unknown>>[]
  theory_relations: readonly Readonly<Record<string, unknown>>[]
}>

export type M5ResearchExport = Readonly<{
  documentId: string
  filename: string
  knowledgeReleaseId: string
  manifest: M5ResearchExportManifest
  markdown: string
  taskId: string
  theoryPlanId: string
  version: number
}>

function mapExport(exported: ResearchDocumentExportResponse): M5ResearchExport {
  return {
    documentId: exported.document_id,
    filename: exported.filename,
    knowledgeReleaseId: exported.knowledge_release_id,
    manifest: exported.manifest,
    markdown: exported.markdown,
    taskId: exported.task_id,
    theoryPlanId: exported.theory_plan_id,
    version: exported.version,
  }
}

export function serializeM5ResearchExport(
  exported: Readonly<{ filename: string; markdown: string; manifest: unknown }>,
  format: M5ExportFormat,
): M5SerializedExport {
  if (format === 'markdown') {
    return {
      filename: exported.filename,
      mediaType: 'text/markdown;charset=utf-8',
      content: exported.markdown,
    }
  }
  return {
    filename: exported.filename.replace(/\.md$/i, '') + '.json',
    mediaType: 'application/json;charset=utf-8',
    content: JSON.stringify(exported.manifest, null, 2),
  }
}
