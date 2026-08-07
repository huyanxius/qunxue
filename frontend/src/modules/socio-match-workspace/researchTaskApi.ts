import { apiClient } from '../../api/client'
import { ApiRequestError } from '../../api/error'
import {
  createResearchTask as createResearchTaskRequest,
  confirmPhenomenonCandidate,
  extractPhenomenonCandidates,
  getPhenomenonCandidate,
  getResearchTaskNavigation,
  getResearchTask as getResearchTaskRequest,
  listPhenomenonSnapshots,
  submitDirectInput,
  updatePhenomenonCandidate,
  type PhenomenonCandidateResponse,
  type PhenomenonSnapshotResponse,
  type ResearchTaskResponse,
} from '../../api/generated'
import type {
  ResearchTask,
  ResearchTaskAction,
  ResearchTaskEntryType,
  ResearchTaskStatus,
  PhenomenonCandidate,
  PhenomenonSnapshot,
  RestoredPhenomenon,
  StartedPhenomenon,
} from './researchTaskModel'

const entryTypes = {
  direct_input: 'direct_input',
} satisfies Record<ResearchTaskResponse['entry_type'], ResearchTaskEntryType>

const taskStatuses = {
  draft: 'draft',
} satisfies Record<ResearchTaskResponse['status'], ResearchTaskStatus>

const taskActions = {
  submit_phenomenon: 'submit_phenomenon',
} satisfies Record<
  ResearchTaskResponse['allowed_actions'][number],
  ResearchTaskAction
>

function toResearchTask(response: ResearchTaskResponse): ResearchTask {
  return {
    taskId: response.task_id,
    entryType: entryTypes[response.entry_type],
    status: taskStatuses[response.status],
    version: response.version,
    allowedActions: response.allowed_actions.map(
      (action) => taskActions[action],
    ),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function idempotencyKey() {
  return globalThis.crypto.randomUUID()
}

function toCandidate(response: PhenomenonCandidateResponse): PhenomenonCandidate {
  return {
    candidateId: response.candidate_id,
    taskId: response.task_id,
    version: response.version,
    status: response.status,
    phenomenon: response.phenomenon,
    researchIntent: response.research_intent,
    context: response.context,
    evidence: response.evidence_refs.map((item) => ({
      evidenceRefId: item.evidence_ref_id,
      excerpt: item.excerpt,
      sourceDescription: item.source_description,
      useBoundary: item.use_boundary,
    })),
    modelLabel: `演示 AI · ${response.model.provider}`,
  }
}

function toSnapshot(response: PhenomenonSnapshotResponse): PhenomenonSnapshot {
  return {
    phenomenonQueryId: response.phenomenon_query_id,
    phenomenon: response.phenomenon,
    researchIntent: response.research_intent,
    context: response.context,
    confirmedAt: response.confirmed_at,
  }
}

/** SocioMatch 内部的 HTTP 适配器；公共入口不得直接导出本文件。 */
export async function createResearchTaskViaApi(
  idempotencyKey: string,
): Promise<ResearchTask> {
  const { data, response } = await createResearchTaskRequest({
    client: apiClient,
    body: { entry_type: 'direct_input' },
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  if (!data) {
    throw new ApiRequestError('研究任务创建失败。', response?.status)
  }
  return toResearchTask(data)
}

export async function getResearchTaskViaApi(
  taskId: string,
): Promise<ResearchTask> {
  const { data, response } = await getResearchTaskRequest({
    client: apiClient,
    path: { task_id: taskId },
  })
  if (!data) {
    throw new ApiRequestError('研究任务恢复失败。', response?.status)
  }
  return toResearchTask(data)
}

export async function startPhenomenonViaApi(
  phenomenon: string,
): Promise<StartedPhenomenon> {
  const task = await createResearchTaskViaApi(idempotencyKey())
  const direct = await submitDirectInput({
    client: apiClient,
    path: { task_id: task.taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { phenomenon, research_intent: null, context: null },
  })
  if (!direct.data) {
    throw new ApiRequestError('现象输入保存失败。', direct.response?.status)
  }
  const extracted = await extractPhenomenonCandidates({
    client: apiClient,
    path: { task_id: task.taskId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { expected_task_version: task.version, requested_count: 1 },
  })
  const candidate = extracted.data?.candidates[0]
  if (!candidate) {
    throw new ApiRequestError('演示候选生成失败。', extracted.response?.status)
  }
  return { taskId: task.taskId, candidate: toCandidate(candidate) }
}

export async function restorePhenomenonViaApi(
  taskId: string,
): Promise<RestoredPhenomenon> {
  const navigation = await getResearchTaskNavigation({
    client: apiClient,
    path: { task_id: taskId },
  })
  const candidateId = navigation.data?.current_phenomenon_candidate_id
  if (!candidateId) {
    throw new ApiRequestError('这项研究还没有现象候选。', navigation.response?.status)
  }
  const [candidateResult, snapshotsResult] = await Promise.all([
    getPhenomenonCandidate({
      client: apiClient,
      path: { task_id: taskId, candidate_id: candidateId },
    }),
    listPhenomenonSnapshots({ client: apiClient, path: { task_id: taskId } }),
  ])
  if (!candidateResult.data || !snapshotsResult.data) {
    throw new ApiRequestError('现象确认状态恢复失败。')
  }
  return {
    candidate: toCandidate(candidateResult.data),
    snapshot: snapshotsResult.data.snapshots[0]
      ? toSnapshot(snapshotsResult.data.snapshots[0])
      : null,
  }
}

export async function confirmEditedPhenomenonViaApi(
  candidate: PhenomenonCandidate,
  values: { phenomenon: string; researchIntent: string; context: string },
): Promise<PhenomenonSnapshot> {
  const updated = await updatePhenomenonCandidate({
    client: apiClient,
    path: { task_id: candidate.taskId, candidate_id: candidate.candidateId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: {
      expected_version: candidate.version,
      phenomenon: values.phenomenon,
      research_intent: values.researchIntent || null,
      context: values.context || null,
    },
  })
  if (!updated.data) {
    throw new ApiRequestError('候选修改保存失败。', updated.response?.status)
  }
  const confirmed = await confirmPhenomenonCandidate({
    client: apiClient,
    path: { task_id: candidate.taskId, candidate_id: candidate.candidateId },
    headers: { 'Idempotency-Key': idempotencyKey() },
    body: { expected_version: updated.data.version },
  })
  if (!confirmed.data) {
    throw new ApiRequestError('现象确认失败。', confirmed.response?.status)
  }
  return toSnapshot(confirmed.data)
}
