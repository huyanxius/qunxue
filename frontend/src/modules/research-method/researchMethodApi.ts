import { apiClient } from '../../api/client'
import {
  createMethodPlan as createGenerated,
  getCurrentMethodPlan as getCurrentGenerated,
  updateMethodPlan as updateGenerated,
  reviewMethodPlan as reviewGenerated,
  resolveMethodPlanReview as resolveGenerated,
  confirmMethodPlan as confirmGenerated,
  restoreMethodPlan as restoreGenerated,
  listMethodPlanVersions as listVersionsGenerated,
  getResearchTaskNavigation,
} from '../../api/generated'

export type MethodKind = 'qualitative' | 'quantitative' | 'mixed' | 'undecided'
export type MethodPlanSection = { key: string; title: string; content: string; source: 'system' | 'user' }
export type MethodPlanReview = { review_id: string; note: string; blocking: boolean; created_at: string; resolved_at: string | null }
export type MethodPlanEvidenceRef = {
  evidence_ref_id: string; source_id: string; source_kind: string
  knowledge_release_id: string | null; annotation_id: string | null; material_id: string | null
  parse_id: string | null; segment_id: string | null; locator: string | null
}
export type MethodPlanContextItem = {
  key: string; title: string; content: string; evidence_refs: MethodPlanEvidenceRef[]
}
export type MethodPlan = {
  plan_id: string; task_id: string; framework_id: string; framework_version: number
  theory_plan_id: string; theory_plan_version: number; method_kind: MethodKind
  decision_source: string; rationale: string; research_question: string; theory_summary: string
  material_constraints: string[]; ethical_constraints: string[]; theory_concepts: string[]
  evidence_ref_ids: string[]; knowledge_release_id: string | null; sections: MethodPlanSection[]
  shared_context: MethodPlanContextItem[]
  reviews: MethodPlanReview[]; status: 'draft' | 'under_review' | 'confirmed' | 'stale'
  version: number; revision_id: string; change_summary: string; actor: string; created_at: string
  restored_from_version: number | null; stale_reason: string | null; confirmed_at: string | null
}

type CreateInput = { framework_id: string; theory_plan_id: string; method_kind: MethodKind }
type UpdateInput = { expected_version: number; method_kind: MethodKind; rationale: string; change_summary: string; sections: MethodPlanSection[] }
type Result<T> = { data?: T; error?: unknown; response?: Response }

export async function getMethodPlanPrerequisites(taskId: string): Promise<{
  frameworkId: string
  theoryPlanId: string
}> {
  const value = unwrap(await getResearchTaskNavigation({
    client: apiClient,
    path: { task_id: taskId },
  }))
  if (!value.current_framework_id || !value.current_theory_plan_id) {
    throw new Error('请先确认研究框架与理论方案。')
  }
  return {
    frameworkId: value.current_framework_id,
    theoryPlanId: value.current_theory_plan_id,
  }
}

function key() { return `research-method:${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}:${Math.random()}`}` }
function message(error: unknown) {
  const value = error && typeof error === 'object' ? error as Record<string, unknown> : {}
  const detail = value.error && typeof value.error === 'object' ? value.error as Record<string, unknown> : {}
  return typeof detail.message === 'string' ? detail.message : '方法计划请求失败。'
}
function unwrap<T>(result: Result<T>): T {
  if (result.error) throw new Error(message(result.error))
  if (result.data === undefined) throw new Error('方法计划请求无返回。')
  return result.data
}

export async function getCurrentMethodPlan(taskId: string, signal?: AbortSignal): Promise<MethodPlan | null> {
  const value = unwrap(await getCurrentGenerated({ client: apiClient, path: { task_id: taskId }, signal }))
  return ((value as unknown) === 'null' ? null : value) as MethodPlan | null
}

export async function createMethodPlan(taskId: string, body: CreateInput, signal?: AbortSignal): Promise<MethodPlan> {
  return unwrap(await createGenerated({ client: apiClient, path: { task_id: taskId }, headers: { 'Idempotency-Key': key() }, body, signal })) as MethodPlan
}

export async function updateMethodPlan(planId: string, body: UpdateInput): Promise<MethodPlan> {
  return unwrap(await updateGenerated({ client: apiClient, path: { plan_id: planId }, headers: { 'Idempotency-Key': key() }, body })) as MethodPlan
}
export async function reviewMethodPlan(planId: string, body: { expected_version: number; note: string; blocking: boolean }): Promise<MethodPlan> {
  return unwrap(await reviewGenerated({ client: apiClient, path: { plan_id: planId }, headers: { 'Idempotency-Key': key() }, body })) as MethodPlan
}
export async function resolveMethodPlanReview(planId: string, reviewId: string, body: { expected_version: number; reason: string }): Promise<MethodPlan> {
  return unwrap(await resolveGenerated({ client: apiClient, path: { plan_id: planId, review_id: reviewId }, headers: { 'Idempotency-Key': key() }, body })) as MethodPlan
}
export async function confirmMethodPlan(planId: string, body: { expected_version: number; reason: string }): Promise<MethodPlan> {
  return unwrap(await confirmGenerated({ client: apiClient, path: { plan_id: planId }, headers: { 'Idempotency-Key': key() }, body })) as MethodPlan
}
export async function restoreMethodPlan(planId: string, body: { source_version: number; expected_version: number; reason: string }): Promise<MethodPlan> {
  return unwrap(await restoreGenerated({ client: apiClient, path: { plan_id: planId }, headers: { 'Idempotency-Key': key() }, body })) as MethodPlan
}
export async function listMethodPlanVersions(planId: string): Promise<MethodPlan[]> {
  const value = unwrap(await listVersionsGenerated({ client: apiClient, path: { plan_id: planId } })) as unknown
  if (!value || typeof value !== 'object' || !('items' in value) || !Array.isArray(value.items)) {
    throw new Error('方法计划版本列表无返回。')
  }
  return value.items as MethodPlan[]
}
