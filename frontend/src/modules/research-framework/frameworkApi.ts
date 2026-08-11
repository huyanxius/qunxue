import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  confirmFramework,
  createFramework,
  getFramework,
  getResearchTaskNavigation,
  listFrameworkVersions,
  startFrameworkReview,
  submitAuditResolutions,
  updateFramework,
  type FrameworkDraftContract,
  type FrameworkResponse,
} from '../../api/generated'
import type {
  FrameworkResolution,
  ResearchFrameworkView,
} from './ResearchFrameworkWorkspace'


function idempotencyKey() {
  return globalThis.crypto.randomUUID()
}

function theoryPlan(response: FrameworkResponse): string[] {
  const candidateTitles = new Map(
    response.input.theory_plan.decisions.map((decision) => [
      decision.candidate_id,
      decision.reason,
    ]),
  )
  return response.input.theory_plan.use_assignments.map((assignment) => (
    `${assignment.role_code}：${assignment.responsibility}${
      candidateTitles.get(assignment.candidate_id)
        ? ` · ${candidateTitles.get(assignment.candidate_id)}`
        : ''
    }`
  ))
}

export function toFrameworkView(response: FrameworkResponse): ResearchFrameworkView {
  return {
    frameworkId: response.framework_id,
    revisionId: response.revision_id,
    version: response.version,
    status: response.status,
    contentOrigin: response.content_origin,
    revisionReason: response.revision_reason,
    confirmedResearchQuestion: response.input.confirmed_research_question,
    theoryPlan: theoryPlan(response),
    conceptMappings: response.draft.concept_mappings.map((item) => ({
      candidateId: item.candidate_id,
      theoryConcept: item.theory_concept,
      meaningInStudy: item.meaning_in_study,
      empiricalIndicators: item.empirical_indicators,
      unresolvedQuestions: item.unresolved_questions,
    })),
    materialRequirements: response.draft.evidence_requirements.map(
      (item) => item.required_material,
    ),
    evidenceConstraints: response.draft.evidence_requirements.flatMap((item) => [
      `支持：${item.supporting_signal}`,
      `排除：${item.excluding_signal}`,
      ...(item.distinguishing_signal ? [`区分：${item.distinguishing_signal}`] : []),
    ]),
    alternativeExplanations: response.draft.alternative_explanations,
    ethicalBoundaries: response.draft.ethical_boundaries,
    nextActions: response.draft.next_actions,
    scopeAndLimitations: response.draft.scope_and_limitations,
    unresolvedItems: response.draft.unresolved_items,
    audit: response.audit ? {
      auditId: response.audit.audit_id,
      isStale: response.audit.is_stale,
      findings: response.audit.findings.map((item) => ({
        findingId: item.finding_id,
        severity: item.severity,
        summary: item.summary,
        reason: item.reason,
        impact: item.impact,
        recommendation: item.recommendation,
        blocking: item.blocking,
      })),
    } : null,
  }
}

function editableDraft(
  source: FrameworkDraftContract,
  view: ResearchFrameworkView,
): FrameworkDraftContract {
  return {
    ...source,
    alternative_explanations: view.alternativeExplanations,
    ethical_boundaries: view.ethicalBoundaries,
    next_actions: view.nextActions,
    scope_and_limitations: view.scopeAndLimitations,
    unresolved_items: view.unresolvedItems,
  }
}

export async function restoreFrameworkViaApi(taskId: string) {
  const navigation = await getResearchTaskNavigation({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!navigation.data) {
    throw new ApiRequestError('研究进度恢复失败。', navigation.response?.status)
  }
  const frameworkId = navigation.data.current_framework_id
  if (!frameworkId) return null
  const [current, versions] = await Promise.all([
    getFramework({ client: apiClient, path: { framework_id: frameworkId } }),
    listFrameworkVersions({ client: apiClient, path: { framework_id: frameworkId } }),
  ])
  if (!current.data || !versions.data) {
    throw new ApiRequestError('研究框架恢复失败。', current.response?.status ?? versions.response?.status)
  }
  return {
    raw: current.data,
    current: toFrameworkView(current.data),
    versions: versions.data.versions.map(toFrameworkView),
  }
}

export async function createFrameworkViaApi(input: {
  taskId: string
  taskVersion: number
  theoryPlanId: string
  theoryPlanVersion: number
  originalResearchQuestion: string
  confirmedResearchQuestion: string
  researchObject: string
  analysisUnit: string
  context: string
}) {
  const result = await createFramework({
    client: apiClient,
    path: { task_id: input.taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_task_version: input.taskVersion,
      theory_plan_id: input.theoryPlanId,
      theory_plan_version: input.theoryPlanVersion,
      original_research_question: input.originalResearchQuestion,
      confirmed_research_question: input.confirmedResearchQuestion,
      question_adjustment_reason: input.originalResearchQuestion === input.confirmedResearchQuestion
        ? null
        : '用户在生成框架前收窄研究问题',
      research_object: input.researchObject,
      analysis_unit: input.analysisUnit || null,
      context: input.context || null,
      method_intent: {
        method_kind: null,
        constraints: ['仅使用有权处理且去标识化的材料'],
        source: 'user_confirmed',
      },
    },
  })
  if (!result.data) throw new ApiRequestError('框架生成失败。', result.response?.status)
  return toFrameworkView(result.data)
}

export async function saveFrameworkViaApi(
  raw: FrameworkResponse,
  view: ResearchFrameworkView,
  reason: string,
) {
  const result = await updateFramework({
    client: apiClient,
    path: { framework_id: raw.framework_id },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_revision_id: raw.revision_id,
      expected_version: raw.version,
      draft: editableDraft(raw.draft, view),
      revision_reason: reason,
    },
  })
  if (!result.data) throw new ApiRequestError('新版本保存失败。', result.response?.status)
}

export async function reviewFrameworkViaApi(raw: FrameworkResponse) {
  const result = await startFrameworkReview({
    client: apiClient,
    path: { framework_id: raw.framework_id },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_revision_id: raw.revision_id,
      expected_version: raw.version,
    },
  })
  if (!result.data) throw new ApiRequestError('框架审校失败。', result.response?.status)
}

function resolutionBody(item: FrameworkResolution) {
  return {
    finding_id: item.findingId,
    action: item.action,
    reason: item.reason,
  }
}

export async function resolveFrameworkAuditViaApi(
  raw: FrameworkResponse,
  resolutions: FrameworkResolution[],
) {
  if (!raw.audit) throw new ApiRequestError('当前没有可处理的审校意见。')
  const result = await submitAuditResolutions({
    client: apiClient,
    path: { framework_id: raw.framework_id },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_revision_id: raw.revision_id,
      expected_version: raw.version,
      audit_id: raw.audit.audit_id,
      resolutions: resolutions.map(resolutionBody),
    },
  })
  if (!result.data) throw new ApiRequestError('审校处理保存失败。', result.response?.status)
}

export async function confirmFrameworkViaApi(
  raw: FrameworkResponse,
  resolutions: FrameworkResolution[],
) {
  if (!raw.audit) throw new ApiRequestError('确认前必须完成审校。')
  const result = await confirmFramework({
    client: apiClient,
    path: { framework_id: raw.framework_id },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_revision_id: raw.revision_id,
      expected_version: raw.version,
      audit_id: raw.audit.audit_id,
      resolutions: resolutions.map(resolutionBody),
    },
  })
  if (!result.data) throw new ApiRequestError('框架确认失败。', result.response?.status)
}
